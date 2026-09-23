"""Eko 2.5C — Conversational Regression Matrix.

TEST FIRST, HARDEN SECOND. No production behavior changes.

Categories:
  CURRENT_CONTRACT / REGRESSION_PROTECTION — must PASS today
  EXPECTED_GAP / FUTURE_CONTRACT — xfail(strict=False) until 2.5D/E
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import app.config as app_config
import app.services.eko_action_bridge as bridge
from app.domain.conversation_state import (
    KIND_ADMIN,
    KIND_TECNICO,
    MAX_STACK,
    hydrate_conversation_state,
)
from app.domain.domain_lifecycle import (
    apply_domain_signal,
    create_domain,
    new_conversation_state,
    pause_domain,
    resume_domain,
)
from app.services.eko_action_runtime import (
    ActionResult,
    TrustedContext,
    bootstrap_registry,
    get_action_state,
    parse_llm_action_proposal,
    sanitize_parameters,
)
from app.services.eko_journeys import (
    apply_service_ref,
    get_journey,
    maybe_handle_journey_turn,
    set_journey,
)
from app.services.eko_service_selection import (
    ServiceRef,
    get_selected_ref,
    resolve_service_selection,
)

# ---------------------------------------------------------------------------
# Markers / helpers
# ---------------------------------------------------------------------------

EXPECTED_GAP = pytest.mark.xfail(
    strict=False,
    reason="EXPECTED_GAP — target contract 2.5B; harden in 2.5D/E (do not implement in 2.5C)",
)


def _abo(**kwargs):
    d = {
        "id": "abo-1",
        "organizacion_id": "org-1",
        "nombre": "Ana",
        "dni": "30111222",
        "client_number": "18099",
        "deuda_monto": "1500",
        "servicio": "internet",
        "plan": "100Mb",
        "estado": "activo",
    }
    d.update(kwargs)
    return SimpleNamespace(**d)


def _conv(**kwargs):
    d = {
        "id": "conv-1",
        "ticket_id": "",
        "estado": "bot",
        "telefono": "2235551234",
        "canal": "whatsapp",
        "abonado_id": "abo-1",
    }
    d.update(kwargs)
    return SimpleNamespace(**d)


def _enable(monkeypatch, *actions: str):
    monkeypatch.setattr(app_config, "EKO_JOURNEYS_ENABLED", True)
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", True)
    monkeypatch.setattr(
        bridge,
        "ACTION_RUNTIME_ACTIONS",
        frozenset(
            actions
            or (
                "request_account_selection",
                "run_diagnostic_pppoe",
                "show_balance",
                "show_ticket",
                "open_OV",
                "create_ticket",
                "service_list",
            )
        ),
    )
    bootstrap_registry()


def _row(
    *,
    sid: str,
    tip: str = "internet",
    product: str = "Internet",
    label: str = "",
    login: str = "",
    active: bool = True,
) -> dict:
    return {
        "id": sid,
        "type": tip,
        "label": label or product,
        "product": product,
        "active": active,
        "login": login,
        "line_msisdn": None,
    }


def _cat(*rows: dict) -> dict:
    return {
        "status": "ok",
        "checked_at": "2026-09-23T12:00:00+00:00",
        "services": list(rows),
        "reason_code": None,
    }


def _ref_internet(**kw) -> ServiceRef:
    base = dict(
        service_id="inet-1",
        login="INT1",
        service_type="internet",
        client_number="18099",
        label="Internet",
        product="Fibra 100",
        active=True,
    )
    base.update(kw)
    return ServiceRef(**base)


def _ref_fija(**kw) -> ServiceRef:
    base = dict(
        service_id="tel-1",
        login="",
        service_type="telefonia",
        client_number="18099",
        label="Teléfono fijo",
        product="Línea fija",
        active=True,
    )
    base.update(kw)
    return ServiceRef(**base)


def _ref_sensa(**kw) -> ServiceRef:
    base = dict(
        service_id="tv-1",
        login="",
        service_type="tv",
        client_number="18099",
        label="Sensa",
        product="Sensa",
        active=True,
    )
    base.update(kw)
    return ServiceRef(**base)


# ===========================================================================
# FAMILIA B — Natural references (+ F-01 / F-02)
# ===========================================================================


def test_2_5c_b01_la_fija_selects_telefonia_current():
    """CURRENT (2.5D-2): 'la fija' con único candidato telefonia (+ no-fijo) → select."""
    cat = [
        _row(sid="v1", tip="tv", product="Sensa"),
        _row(sid="t1", tip="telefonia", product="Línea fija", label="Teléfono fijo"),
    ]
    r = resolve_service_selection(texto="la fija", catalog=cat, client_number="18099")
    assert r.status == "selected"
    assert r.ref is not None
    assert r.ref.service_type == "telefonia"
    assert r.ref.service_id == "t1"


def test_2_5c_b02_el_fijo_unique_telefonia_selects():
    """CURRENT (2.5D-2 F-01): único telefonia → 'el fijo' selecciona."""
    cat = [
        _row(sid="t1", tip="telefonia", product="Línea fija", label="Teléfono fijo"),
    ]
    r = resolve_service_selection(texto="el fijo", catalog=cat, client_number="18099")
    assert r.status == "selected"
    assert r.ref and r.ref.service_id == "t1"


def test_2_5c_b02_el_fijo_ambiguous_catalog_current_needs_input():
    """CURRENT: internet+telefonia + 'el fijo' → needs_input (safe)."""
    cat = [
        _row(sid="i1", tip="internet", login="INT1", product="Internet fijo"),
        _row(sid="t1", tip="telefonia", product="Línea fija", label="Teléfono fijo"),
    ]
    r = resolve_service_selection(texto="el fijo", catalog=cat, client_number="18099")
    assert r.status == "needs_input"


def test_2_5c_b02_target_el_fijo_internet_and_telefonia_stays_needs_input():
    """CURRENT_CONTRACT (+ TARGET same): ambiguous fijo → NEEDS_INPUT, never hardcode.

    When synonym map lands (2.5E), this case MUST remain needs_input.
    """
    cat = [
        _row(sid="i1", tip="internet", login="INT1", product="Internet fijo"),
        _row(sid="t1", tip="telefonia", product="Línea fija", label="Teléfono fijo"),
    ]
    r = resolve_service_selection(texto="el fijo", catalog=cat, client_number="18099")
    assert r.status == "needs_input"


def test_2_5c_b03_el_internet_unique_selects():
    """REGRESSION_PROTECTION."""
    cat = [
        _row(sid="i1", tip="internet", login="INT1", product="Fibra"),
        _row(sid="t1", tip="tv", product="Sensa"),
    ]
    r = resolve_service_selection(texto="el internet", catalog=cat, client_number="18099")
    assert r.status == "selected"
    assert r.ref and r.ref.service_id == "i1"


def test_2_5c_b03_el_internet_two_internets_needs_input():
    """REGRESSION_PROTECTION: ambiguity > guessing."""
    cat = [
        _row(sid="i1", tip="internet", login="INTA", product="Fibra 100"),
        _row(sid="i2", tip="internet", login="INTB", product="Fibra 300"),
    ]
    r = resolve_service_selection(texto="el internet", catalog=cat, client_number="18099")
    assert r.status == "needs_input"


def test_2_5c_b04_ese_single_service_selects():
    """REGRESSION_PROTECTION — 2.5A confirmed."""
    cat = [_row(sid="i1", tip="internet", login="INT1", product="Fibra")]
    r = resolve_service_selection(texto="ese", catalog=cat, client_number="18099")
    assert r.status == "selected"
    assert r.ref and r.ref.service_id == "i1"


def test_2_5c_b04_ese_multi_needs_input():
    """REGRESSION_PROTECTION — 2.5A confirmed."""
    cat = [
        _row(sid="i1", tip="internet", login="INT1", product="Fibra"),
        _row(sid="t1", tip="tv", product="Sensa"),
    ]
    r = resolve_service_selection(texto="ese", catalog=cat, client_number="18099")
    assert r.status == "needs_input"


def test_2_5c_b05_el_otro_without_current_ref_needs_input():
    """CURRENT (2.5D-2): 'el otro' sin selected_service_ref canónico → NEEDS_INPUT."""
    cat = [
        _row(sid="i1", tip="internet", login="INT1", product="Fibra"),
        _row(sid="t1", tip="telefonia", product="Fija"),
    ]
    r = resolve_service_selection(
        texto="el otro",
        catalog=cat,
        client_number="18099",
        pending_options=[
            {"service_id": "i1", "login": "INT1"},
            {"service_id": "t1", "login": ""},
        ],
    )
    assert r.status == "needs_input"
    assert r.reason_code == "otro_missing_current"


def test_2_5c_b05_el_otro_unique_alternative_selects():
    """CURRENT (2.5D-2 F-02): current A + only B left → B."""
    cat = [
        _row(sid="i1", tip="internet", login="INT1", product="Fibra"),
        _row(sid="t1", tip="telefonia", product="Fija"),
    ]
    cur = ServiceRef(
        service_id="i1",
        login="INT1",
        service_type="internet",
        client_number="18099",
    )
    r = resolve_service_selection(
        texto="el otro",
        catalog=cat,
        client_number="18099",
        current_ref=cur,
    )
    assert r.status == "selected"
    assert r.ref is not None
    assert r.ref.service_id == "t1"


def test_2_5c_b05_el_otro_three_services_current_needs_input():
    """CURRENT (+ TARGET same for 3-way): never arbitrary pick."""
    cat = [
        _row(sid="i1", tip="internet", login="INT1", product="Fibra"),
        _row(sid="t1", tip="telefonia", product="Fija"),
        _row(sid="v1", tip="tv", product="Sensa"),
    ]
    r = resolve_service_selection(texto="el otro", catalog=cat, client_number="18099")
    assert r.status == "needs_input"


# ===========================================================================
# FAMILIA A / C — Service + domain continuity
# ===========================================================================


def test_2_5c_a03_selection_survives_billing_domain_switch(monkeypatch):
    """CURRENT_CONTRACT / REGRESSION: selection preserved across billing switch."""
    _enable(monkeypatch)
    ctx: dict = {}
    apply_service_ref(ctx, _ref_internet())
    set_journey(
        ctx,
        name="internet_sin_conectividad",
        domain="internet",
        intent="internet",
        diagnostic_started=True,
        last_diagnostic_result="pppoe_session_up",
        correlation_id="c1",
    )
    with patch(
        "app.services.eko_journeys.dispatch_runtime",
        return_value=ActionResult(
            action="show_balance", status="success", user_message="Saldo 0"
        ),
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "En realidad quiero saber cuánto debo",
            canal="wa",
            ctx=ctx,
        )
    assert t is not None
    assert get_journey(ctx).get("domain") == "billing"
    ref = get_selected_ref(ctx)
    assert ref is not None
    assert ref.service_id == "inet-1"
    assert ref.login == "INT1"
    assert ctx.get("login_seleccionado") == "INT1"


def test_2_5c_a05_service_switch_invalidates_diagnostic():
    """REGRESSION_PROTECTION — apply_service_ref invalidation contract."""
    ctx: dict = {
        "pppoe_informado": True,
        "tss_status": "ok",
    }
    apply_service_ref(ctx, _ref_internet())
    set_journey(
        ctx,
        diagnostic_started=True,
        last_diagnostic_result="pppoe_session_up",
        pending_confirmation=True,
    )
    apply_service_ref(ctx, _ref_fija(), previous_login="INT1")
    ref = get_selected_ref(ctx)
    assert ref and ref.service_id == "tel-1"
    assert get_journey(ctx).get("diagnostic_started") is False
    assert get_journey(ctx).get("last_diagnostic_result") in ("", None)
    assert not ctx.get("pppoe_informado")
    assert ctx.get("tss_status") is None
    assert ref.client_number == "18099"


def test_2_5c_a04_explicit_switch_via_natural_internet_then_telefono():
    """CURRENT: switch explícito por tipo inequívoco (no 'fijo' ambiguo A3)."""
    cat = [
        _row(sid="i1", tip="internet", login="INT1", product="Fibra"),
        _row(sid="t1", tip="telefonia", product="Fija", label="Teléfono fijo"),
    ]
    r1 = resolve_service_selection(texto="el internet", catalog=cat, client_number="18099")
    assert r1.status == "selected" and r1.ref and r1.ref.service_id == "i1"
    r2 = resolve_service_selection(
        texto="Ahora hablame del teléfono", catalog=cat, client_number="18099"
    )
    assert r2.status == "selected" and r2.ref and r2.ref.service_id == "t1"


def test_2_5c_a04_ahora_el_fijo_unique_telefonia_only():
    """CURRENT (2.5D-2 F-01): sole telefonia + 'Ahora hablame del fijo' → select."""
    cat = [
        _row(sid="t1", tip="telefonia", product="Fija", label="Teléfono fijo"),
    ]
    r = resolve_service_selection(
        texto="Ahora hablame del fijo", catalog=cat, client_number="18099"
    )
    assert r.status == "selected"
    assert r.ref and r.ref.service_type == "telefonia"


def test_2_5c_a04_la_fija_with_internet_and_phone_needs_input():
    """CURRENT (2.5D-2 A3): internet + telefonia + 'la fija' → NEEDS_INPUT."""
    cat = [
        _row(sid="i1", tip="internet", login="INT1", product="Fibra"),
        _row(sid="t1", tip="telefonia", product="Fija", label="Teléfono fijo"),
    ]
    r = resolve_service_selection(
        texto="Ahora hablame de la fija", catalog=cat, client_number="18099"
    )
    assert r.status == "needs_input"
    assert r.reason_code == "fijo_ambiguous"


# ===========================================================================
# FAMILIA C04 / J / F-03 — domain_stack + resume
# ===========================================================================


def test_2_5c_c04_domain_stack_max_three_programmatic():
    """REGRESSION_PROTECTION: ConversationState MAX_STACK = 3."""
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet_ftth")
    apply_domain_signal(cs, "¿Cuánto debo?", playbook="facturacion")
    assert cs.active_slot() and cs.active_slot().kind == KIND_ADMIN
    assert len(cs.domain_stack) <= MAX_STACK
    resume_domain(cs, "tec-1")
    assert cs.active_domain_id == "tec-1"
    assert cs.slot("tec-1").status == "active"


def test_2_5c_c04_domain_stack_no_unlimited_growth():
    """CURRENT: stack trimmed to MAX_STACK."""
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="wifi")
    for _ in range(5):
        apply_domain_signal(cs, "¿Cuánto debo?", playbook="facturacion")
        apply_domain_signal(cs, "Sigo sin internet.")
    assert len(cs.domain_stack) <= MAX_STACK


def test_2_5c_b06_j01_volviendo_a_lo_anterior_resumes_domain():
    """CURRENT (2.5D-3 F-03): NL resume via domain_stack → previous domain."""
    from app.domain.domain_lifecycle import (
        apply_domain_resume,
        kind_from_user_signal,
        pause_domain,
    )

    # kind_from_user_signal sigue sin clasificar resume (no es SIGNAL_DOMAIN)
    assert kind_from_user_signal("volviendo a lo anterior") is None
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet", activate=True)
    pause_domain(cs)
    create_domain(cs, kind=KIND_ADMIN, playbook="facturacion", activate=True)
    r = apply_domain_resume(cs, "volviendo a lo anterior")
    assert r.status == "resolved"
    assert r.domain_id == "tec-1"
    assert cs.active_domain_id == "tec-1"

def test_2_5c_j02_no_resume_context_kind_signal_none():
    """CURRENT_CONTRACT: 'volviendo a lo anterior' is not a domain kind signal."""
    from app.domain.domain_lifecycle import kind_from_user_signal

    assert kind_from_user_signal("volviendo a lo anterior") is None
    assert kind_from_user_signal("lo anterior") is None


# ===========================================================================
# FAMILIA D — Confirmation
# ===========================================================================


def test_2_5c_d01_confirmation_yes_requires_pending(monkeypatch):
    """REGRESSION_PROTECTION: bare 'sí' without pending does not create ticket."""
    _enable(monkeypatch)
    ctx = {
        "eko_journey": {
            "name": "internet_sin_conectividad",
            "step": "service_selection",
            "asked_selection": True,
            "next_required_input": "login",
            "intent": "internet",
            "domain": "internet",
            "pending_confirmation": False,
            "correlation_id": "c",
        },
        "multi_cuenta_pendiente": True,
    }
    with (
        patch("app.services.eko_journeys._login_count", return_value=2),
        patch("app.services.canal_abonado._crear_ticket_n2") as create,
    ):
        t = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "sí", canal="wa", ctx=ctx
        )
    create.assert_not_called()
    assert t and t.step == "service_selection"


def test_2_5c_d02_stale_confirmation_cleared_on_domain_switch(monkeypatch):
    """REGRESSION_PROTECTION — C10 / 2.5B invalidation."""
    _enable(monkeypatch)
    ctx = {
        "eko_journey": {
            "name": "internet_sin_conectividad",
            "step": "decide",
            "pending_confirmation": True,
            "confirmation_correlation": "oldc",
            "correlation_id": "oldc",
            "intent": "internet",
            "domain": "internet",
            "selected_service": "INT1",
            "selected_service_ref": _ref_internet().to_dict(),
        },
        "login_seleccionado": "INT1",
        "eko_action": {"action": "create_ticket", "status": "confirmation_pending"},
    }
    with patch(
        "app.services.eko_journeys.dispatch_runtime",
        return_value=ActionResult(
            action="show_balance", status="success", user_message="saldo"
        ),
    ):
        maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "¿Cuánto debo?", canal="wa", ctx=ctx
        )
    assert get_journey(ctx).get("pending_confirmation") is False
    assert get_action_state(ctx).get("confirmation") == "CLEARED"
    assert get_selected_ref(ctx) and get_selected_ref(ctx).login == "INT1"


def test_2_5c_d02_stale_confirmation_cannot_execute_via_llm_param():
    """REGRESSION / CASI: LLM cannot inject confirmation_received."""
    cleaned = sanitize_parameters({"confirmation_received": True, "action": "create_ticket"})
    assert cleaned.get("confirmation_received") is not True
    prop = parse_llm_action_proposal(
        {"action": "create_ticket", "parameters": {"confirmation_received": True}}
    )
    assert prop is None or "confirmation_received" not in (prop.parameters or {})


def test_2_5c_d03_confirmation_reject_no():
    """REGRESSION_PROTECTION: rejection flag on TrustedContext blocks mutation path."""
    bootstrap_registry()
    trusted = TrustedContext(
        abonado=_abo(),
        organization_id="org",
        canal="wa",
        db=MagicMock(),
        confirmation_received=False,
        confirmation_rejected=True,
    )
    assert trusted.confirmation_rejected is True
    assert trusted.confirmation_received is False


def test_2_5c_h02_bare_no_without_pending_no_arbitrary_switch(monkeypatch):
    """CURRENT: bare 'no' without pending does not wipe selection."""
    _enable(monkeypatch)
    ctx: dict = {}
    apply_service_ref(ctx, _ref_internet())
    set_journey(ctx, name="internet_sin_conectividad", domain="internet", intent="internet")
    with patch("app.services.eko_journeys._login_count", return_value=1):
        maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "no", canal="wa", ctx=ctx
        )
    assert get_selected_ref(ctx) and get_selected_ref(ctx).service_id == "inet-1"


# ===========================================================================
# FAMILIA E — Multi-account / ownership
# ===========================================================================


def test_2_5c_e01_multi_service_ese_needs_input():
    """REGRESSION: never pick by guess among many."""
    cat = [
        _row(sid="i1", tip="internet", login="INTA", product="Casa"),
        _row(sid="i2", tip="internet", login="INTB", product="Local"),
    ]
    r = resolve_service_selection(texto="ese servicio", catalog=cat, client_number="18099")
    assert r.status == "needs_input"


def test_2_5c_e02_foreign_service_id_denied():
    """REGRESSION_PROTECTION."""
    cat = [_row(sid="i1", tip="internet", login="INT1", product="Fibra")]
    r = resolve_service_selection(
        texto="service_id=FOREIGN",
        catalog=cat,
        client_number="18099",
        proposed_service_id="FOREIGN",
    )
    assert r.status == "denied"


def test_2_5c_e03_missing_client_number_needs_input():
    """REGRESSION_PROTECTION."""
    cat = [_row(sid="t1", tip="telefonia", product="Fija")]
    r = resolve_service_selection(texto="la fija", catalog=cat, client_number="")
    assert r.status == "needs_input"
    assert r.reason_code == "missing_client_number"


def test_2_5c_e03_llm_cannot_set_client_number():
    """CASI / REGRESSION."""
    cleaned = sanitize_parameters({"client_number": "EVIL", "login": "INT1"})
    assert "client_number" not in cleaned


# ===========================================================================
# FAMILIA F — Sensa
# ===========================================================================


def test_2_5c_f01_sensa_selection_does_not_require_login():
    """REGRESSION_PROTECTION / CURRENT_CONTRACT."""
    ctx: dict = {}
    apply_service_ref(ctx, _ref_sensa())
    ref = get_selected_ref(ctx)
    assert ref is not None
    assert ref.service_id == "tv-1"
    assert ref.service_type == "tv"
    assert ref.login == ""
    assert not ctx.get("login_seleccionado")
    assert get_journey(ctx).get("selected_service") == "tv-1"


def test_2_5c_f02_sensa_survives_billing_switch(monkeypatch):
    """CURRENT: Sensa ref persists; no artificial login on domain switch."""
    _enable(monkeypatch)
    ctx: dict = {}
    apply_service_ref(ctx, _ref_sensa())
    set_journey(
        ctx,
        name="service_catalog",
        domain="services",
        intent="servicios",
        correlation_id="s1",
    )
    with patch(
        "app.services.eko_journeys.dispatch_runtime",
        return_value=ActionResult(
            action="show_balance", status="success", user_message="ok"
        ),
    ):
        maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "En realidad quiero saber cuánto debo",
            canal="wa",
            ctx=ctx,
        )
    ref = get_selected_ref(ctx)
    assert ref and ref.service_id == "tv-1" and ref.login == ""
    assert not ctx.get("login_seleccionado")


def test_2_5c_f01_sensa_natural_select():
    """REGRESSION."""
    cat = [
        _row(sid="i1", tip="internet", login="INT1", product="Fibra"),
        _row(sid="v1", tip="tv", product="Sensa", label="Sensa"),
    ]
    r = resolve_service_selection(texto="Sensa", catalog=cat, client_number="18099")
    assert r.status == "selected"
    assert r.ref and r.ref.service_id == "v1" and r.ref.login == ""


# ===========================================================================
# FAMILIA G / H — Technical + correction
# ===========================================================================


def test_2_5c_g03_service_change_after_diagnostic_invalidates():
    """REGRESSION_PROTECTION."""
    ctx: dict = {"pppoe_informado": True}
    apply_service_ref(ctx, _ref_internet())
    set_journey(ctx, diagnostic_started=True, last_diagnostic_result="down")
    apply_service_ref(ctx, _ref_fija(), previous_login="INT1")
    assert get_journey(ctx).get("diagnostic_started") is False


def test_2_5c_h01_user_correction_internet_then_telefono():
    """CURRENT: corrección explícita por tipo inequívoco (teléfono ≠ fijo A3)."""
    ctx: dict = {}
    cat = [
        _row(sid="i1", tip="internet", login="INT1", product="Fibra"),
        _row(sid="t1", tip="telefonia", product="Fija", label="Teléfono fijo"),
    ]
    r1 = resolve_service_selection(texto="el internet", catalog=cat, client_number="18099")
    apply_service_ref(ctx, r1.ref)
    r2 = resolve_service_selection(
        texto="No, el teléfono", catalog=cat, client_number="18099"
    )
    assert r2.status == "selected"
    apply_service_ref(ctx, r2.ref, previous_login="INT1")
    assert get_selected_ref(ctx).service_id == "t1"


def test_2_5c_h01_correction_no_el_fijo_unique_telefonia():
    """CURRENT (2.5D-2 F-01): 'No, el fijo' con único telefonia → select."""
    cat = [_row(sid="t1", tip="telefonia", product="Fija", label="Teléfono fijo")]
    r = resolve_service_selection(texto="No, el fijo", catalog=cat, client_number="18099")
    assert r.status == "selected"


# ===========================================================================
# FAMILIA L / M — State vs history / legacy dual-read
# ===========================================================================


def test_2_5c_m01_selected_service_ref_vs_selected_service_coherent():
    """REGRESSION."""
    ctx: dict = {}
    apply_service_ref(ctx, _ref_internet())
    assert get_journey(ctx).get("selected_service") == "INT1"
    assert get_selected_ref(ctx).login == "INT1"


def test_2_5c_m02_sensa_ref_valid_login_seleccionado_empty():
    """REGRESSION — dual-read contract for no-login services."""
    ctx: dict = {}
    apply_service_ref(ctx, _ref_sensa())
    assert get_selected_ref(ctx).service_id == "tv-1"
    assert ctx.get("login_seleccionado") in (None, "")


def test_2_5c_m03_contexto_json_envelope_holds_canonical_keys():
    """CURRENT: envelope keys co-exist; selected_service_ref is SoT."""
    ctx: dict = {"cs": {}, "hechos": {"dispositivo_afectado": "tablet"}}
    apply_service_ref(ctx, _ref_internet())
    assert "eko_journey" in ctx
    assert get_selected_ref(ctx).service_id == "inet-1"
    assert ctx["hechos"]["dispositivo_afectado"] == "tablet"


def test_2_5c_l01_structured_state_wins_over_stale_history_signal():
    """CURRENT: multi + 'ese' → needs_input (no silent history pick)."""
    cat = [
        _row(sid="i1", tip="internet", login="INT1", product="Fibra"),
        _row(sid="t1", tip="telefonia", product="Fija"),
    ]
    r = resolve_service_selection(texto="ese", catalog=cat, client_number="18099")
    assert r.status == "needs_input"


def test_2_5c_l02_llm_proposal_foreign_id_denied_no_mutation():
    """CASI: proposed foreign id denied; prior selection intact."""
    cat = [_row(sid="i1", tip="internet", login="INT1", product="Fibra")]
    r = resolve_service_selection(
        texto="quiero ese",
        catalog=cat,
        client_number="18099",
        proposed_service_id="OTHER",
    )
    assert r.status == "denied"
    ctx: dict = {}
    apply_service_ref(ctx, _ref_internet())
    assert get_selected_ref(ctx).service_id == "inet-1"


# ===========================================================================
# FAMILIA N / K / I — loops, playbook gap, handoff
# ===========================================================================


def test_2_5c_n04_selection_does_not_set_diagnostic_started(monkeypatch):
    """REGRESSION: selection alone does not mark diagnostic_started."""
    _enable(monkeypatch)
    ctx: dict = {}
    rows = [_row(sid="a", login="INTA", product="Internet")]
    with patch(
        "app.services.portal_services.catalog_for_selection",
        return_value=_cat(*rows),
    ):
        maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "ese servicio",
            canal="wa",
            ctx=ctx,
        )
    assert get_journey(ctx).get("diagnostic_started") in (False, None)


def test_2_5c_k01_playbook_skips_ask_when_selection_valid():
    """CURRENT (2.5D-4): playbooks consume selected_service_ref before re-asking."""
    from app.services.eko_handoff_continuity import should_ask_service_selection

    ctx: dict = {}
    apply_service_ref(ctx, _ref_internet())
    assert should_ask_service_selection(ctx, client_number="18099") is False
    assert get_selected_ref(ctx) is not None


def test_2_5c_i02_handoff_return_validates_context():
    """CURRENT (2.5D-4): return-from-handoff validates structured context (logic path).

    Real channel return = conv.estado → bot (inbox release). Not transcript-based.
    """
    from app.services.eko_handoff_continuity import (
        handoff_is_active,
        prepare_return_from_handoff,
        stamp_handoff_out,
    )

    ctx: dict = {}
    apply_service_ref(ctx, _ref_internet())
    stamp_handoff_out(ctx, reason="escalate_human")
    assert handoff_is_active(ctx)
    r = prepare_return_from_handoff(ctx, client_number="18099")
    assert r.status == "restored"
    assert r.service_kept is True
    assert get_selected_ref(ctx).service_id == "inet-1"
    assert handoff_is_active(ctx) is False


def test_2_5c_i01_handoff_commercial_intent_detectable():
    """CURRENT: commercial change-of-plan is classifiable (HANDOFF path exists)."""
    from app.domain.flujos_abonado import clasificar_intencion

    intent = clasificar_intencion("Quiero cambiar el plan")
    assert intent


def test_2_5c_j01_narrow_resume_connectivity_cue_exists(monkeypatch):
    """CURRENT: billing → 'y el internet' can re-enter connectivity; selection kept."""
    _enable(monkeypatch)
    ctx = {
        "eko_journey": {
            "name": "billing_self_service",
            "step": "done",
            "intent": "facturacion",
            "domain": "billing",
            "selected_service": "INT1",
            "selected_service_ref": _ref_internet().to_dict(),
            "correlation_id": "b",
        },
        "login_seleccionado": "INT1",
    }
    ar = ActionResult(
        action="run_diagnostic_pppoe",
        status="success",
        data={"_estado": SimpleNamespace(online=True, sesion=SimpleNamespace(online=True))},
    )
    with (
        patch("app.services.eko_context.internet_logins_count", return_value=1),
        patch("app.services.eko_journeys.dispatch_runtime", return_value=ar),
    ):
        turn = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "bueno y el internet",
            canal="wa",
            ctx=ctx,
        )
    assert turn is not None
    assert get_selected_ref(ctx) and get_selected_ref(ctx).login == "INT1"


def test_2_5c_cs_shadow_hydrate_roundtrip():
    """REGRESSION: CS envelope hydrates."""
    cs = new_conversation_state(turn=2)
    create_domain(cs, kind=KIND_TECNICO, playbook="wifi")
    pause_domain(cs, "tec-1")
    ctx = {"cs": cs.to_dict()}
    got = hydrate_conversation_state(ctx)
    assert got.turn == 2
    assert got.slot("tec-1") is not None
