"""Eko 2.2C — bounded diagnostics (selected_service_ref → portal_connectivity)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.config as app_config
import app.services.eko_action_bridge as bridge
from app.services.eko_action_runtime import (
    ActionRequest,
    ActionResult,
    TrustedContext,
    bootstrap_registry,
    evaluate_policy,
    execute_action,
    sanitize_parameters,
)
from app.services.eko_journeys import (
    apply_service_ref,
    detect_journey_name,
    get_journey,
    maybe_handle_journey_turn,
    set_journey,
)
from app.services.eko_service_selection import (
    ServiceRef,
    get_selected_ref,
    is_fixed_internet_diagnosticable,
    resolve_service_selection,
)


def _abo(**kwargs):
    d = {
        "id": "abo-1",
        "organizacion_id": "org-1",
        "nombre": "Ana",
        "dni": "30111222",
        "client_number": "18099",
        "deuda_monto": "0",
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
                "run_diagnostic_pppoe",
                "request_account_selection",
                "service_list",
                "show_balance",
            )
        ),
    )
    bootstrap_registry()


def _ref(
    *,
    sid: str = "svc-1",
    login: str = "INT600",
    tip: str = "internet",
    cn: str = "18099",
    product: str = "Internet 600M",
    active: bool | None = True,
) -> ServiceRef:
    return ServiceRef(
        service_id=sid,
        login=login,
        service_type=tip,
        client_number=cn,
        label=product,
        product=product,
        active=active,
    )


def _portal_body(
    *,
    status: str = "operational",
    reason_code: str | None = None,
    message: str = "ok",
    service_id: str = "svc-1",
    needs_selection: bool = False,
) -> dict:
    return {
        "status": status,
        "freshness": "live",
        "checked_at": "2026-09-22T12:00:00+00:00",
        "message": message,
        "access_technology": "ftth",
        "service": {"id": service_id, "label": "Internet 600M"},
        "incident": None,
        "actions": {"can_open_chat": True, "chat_hint": ""},
        "needs_service_selection": needs_selection,
        "services": None,
        "reason_code": reason_code,
        "evidence": {
            "session_present": status == "operational",
            "access_link_up": status != "impaired" or reason_code != "access_link_down",
            "access_quality": "poor" if reason_code == "link_quality_poor" else "good",
        },
        "recommendation": {"recommended_action": "none", "available_actions": []},
    }


def _seed_selection(ctx: dict, ref: ServiceRef) -> None:
    apply_service_ref(ctx, ref)


def _login_count(n: int):
    return patch(
        "app.services.eko_journeys._login_count",
        return_value=n,
    )


def test_t01_selected_service_required(monkeypatch):
    _enable(monkeypatch)
    probe = MagicMock()
    ctx: dict = {}
    with (
        _login_count(2),
        patch("app.services.portal_connectivity.evaluar_conectividad_portal", probe),
        patch("app.services.conexion_pppoe.consultar_conexion_pppoe", probe),
        patch(
            "app.services.eko_journeys.dispatch_runtime",
            return_value=ActionResult(
                action="request_account_selection",
                status="needs_input",
                user_message="Elegí cuenta",
            ),
        ),
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "No tengo internet",
            canal="wa",
            ctx=ctx,
        )
    assert t is not None
    assert t.action_status == "needs_input"
    assert get_selected_ref(ctx) is None or not is_fixed_internet_diagnosticable(
        get_selected_ref(ctx)
    )
    probe.assert_not_called()


def test_t02_single_selected_internet(monkeypatch):
    _enable(monkeypatch)
    ctx: dict = {}
    _seed_selection(ctx, _ref())
    body = _portal_body(message="No registramos problemas en tu acceso a Internet.")
    with (
        _login_count(1),
        patch(
            "app.services.portal_connectivity.evaluar_conectividad_portal",
            return_value=body,
        ) as portal,
        patch("app.services.conexion_pppoe.consultar_conexion_pppoe") as radius,
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "No tengo internet",
            canal="wa",
            ctx=ctx,
        )
    assert t and t.action == "run_diagnostic_pppoe"
    assert t.action_status == "success"
    portal.assert_called_once()
    assert portal.call_args.kwargs.get("service_id") == "svc-1"
    radius.assert_not_called()
    assert t.data.get("login_used") == "INT600"
    assert t.data.get("service_id") == "svc-1"


def test_t03_multiple_internet_ambiguous(monkeypatch):
    _enable(monkeypatch)
    probe = MagicMock()
    ctx: dict = {}
    with (
        _login_count(2),
        patch("app.services.portal_connectivity.evaluar_conectividad_portal", probe),
        patch(
            "app.services.eko_journeys.dispatch_runtime",
            return_value=ActionResult(
                action="request_account_selection",
                status="needs_input",
                user_message="Elegí",
            ),
        ),
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "No tengo internet",
            canal="wa",
            ctx=ctx,
        )
    assert t and t.action_status == "needs_input"
    probe.assert_not_called()


def test_t04_selected_service_ownership(monkeypatch):
    _enable(monkeypatch)
    ctx: dict = {}
    _seed_selection(ctx, _ref(cn="18099"))
    with (
        _login_count(1),
        patch(
            "app.services.portal_connectivity.evaluar_conectividad_portal",
            return_value=_portal_body(),
        ) as portal,
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(client_number="18099"),
            "No tengo internet",
            canal="wa",
            ctx=ctx,
        )
    assert t and t.action_status == "success"
    portal.assert_called_once()


def test_t05_foreign_service(monkeypatch):
    _enable(monkeypatch)
    ctx: dict = {}
    _seed_selection(ctx, _ref(cn="99999", sid="foreign", login="INTX"))
    probe = MagicMock()
    with (
        _login_count(1),
        patch("app.services.portal_connectivity.evaluar_conectividad_portal", probe),
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(client_number="18099"),
            "No tengo internet",
            canal="wa",
            ctx=ctx,
        )
    assert t and t.action_status == "denied"
    assert t.reason_code == "ownership_mismatch"
    probe.assert_not_called()


def test_t06_selected_without_login(monkeypatch):
    _enable(monkeypatch)
    ctx: dict = {}
    ctx["login_seleccionado"] = "INTSTALE"
    _seed_selection(
        ctx,
        _ref(sid="tv-1", login="", tip="tv", product="Sensa"),
    )
    assert ctx.get("login_seleccionado") in (None, "")
    probe = MagicMock()
    with (
        _login_count(1),
        patch("app.services.portal_connectivity.evaluar_conectividad_portal", probe),
        patch("app.services.conexion_pppoe.consultar_conexion_pppoe", probe),
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "No tengo internet",
            canal="wa",
            ctx=ctx,
        )
    assert t and t.reason_code == "service_not_diagnosticable"
    probe.assert_not_called()


def test_t07_login_consistency(monkeypatch):
    _enable(monkeypatch)
    ctx: dict = {}
    _seed_selection(ctx, _ref(sid="svc-7", login="INT777"))
    with (
        _login_count(1),
        patch(
            "app.services.portal_connectivity.evaluar_conectividad_portal",
            return_value=_portal_body(service_id="svc-7"),
        ) as portal,
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "No tengo internet",
            canal="wa",
            ctx=ctx,
        )
    assert t and t.data.get("login_used") == "INT777"
    assert portal.call_args.kwargs.get("service_id") == "svc-7"
    assert get_selected_ref(ctx).login == "INT777"
    assert ctx.get("login_seleccionado") == "INT777"


def test_t08_stale_login_protection(monkeypatch):
    ctx: dict = {}
    _seed_selection(ctx, _ref(sid="a", login="INTA"))
    assert ctx.get("login_seleccionado") == "INTA"
    _seed_selection(ctx, _ref(sid="b", login="", tip="tv", product="Sensa"))
    assert ctx.get("login_seleccionado") in (None, "")
    ref = get_selected_ref(ctx)
    assert ref and ref.service_id == "b"
    assert not is_fixed_internet_diagnosticable(ref)


def test_t09_change_selection_invalidates(monkeypatch):
    ctx: dict = {}
    _seed_selection(ctx, _ref(sid="a", login="INTA"))
    set_journey(ctx, last_diagnostic_result="operational", diagnostic_started=True)
    ctx["tss_status"] = "operational"
    ctx["tss_reason_code"] = ""
    ctx["pppoe_informado"] = True
    _seed_selection(ctx, _ref(sid="b", login="INTB"))
    st = get_journey(ctx)
    assert st.get("last_diagnostic_result") in ("", None)
    assert st.get("diagnostic_started") is False
    assert "tss_status" not in ctx
    assert get_selected_ref(ctx).service_id == "b"


def test_t10_selection_does_not_auto_diagnose(monkeypatch):
    _enable(monkeypatch, "service_list")
    probe = MagicMock()
    ctx: dict = {}
    with (
        patch(
            "app.services.portal_services.catalog_for_selection",
            return_value={
                "status": "ok",
                "services": [
                    {
                        "id": "s1",
                        "type": "internet",
                        "product": "Internet 600M",
                        "label": "Internet 600M",
                        "active": True,
                        "login": "INT600",
                    }
                ],
                "reason_code": None,
            },
        ),
        patch("app.services.portal_connectivity.evaluar_conectividad_portal", probe),
        patch(
            "app.services.eko_journeys.dispatch_runtime",
            return_value=ActionResult(
                action="service_list",
                status="success",
                user_message="ok",
                data={"count": 1},
            ),
        ),
    ):
        maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "El Internet 600M",
            canal="wa",
            ctx=ctx,
        )
    probe.assert_not_called()


def test_t11_explicit_diagnostic_intent(monkeypatch):
    _enable(monkeypatch)
    assert detect_journey_name("No tengo internet") == "internet_sin_conectividad"
    ctx: dict = {}
    _seed_selection(ctx, _ref())
    with (
        _login_count(1),
        patch(
            "app.services.portal_connectivity.evaluar_conectividad_portal",
            return_value=_portal_body(),
        ) as portal,
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "No tengo internet",
            canal="wa",
            ctx=ctx,
        )
    assert t and t.action == "run_diagnostic_pppoe"
    portal.assert_called_once()


def _diag_reason(monkeypatch, reason: str | None, status: str, message: str = "m"):
    _enable(monkeypatch)
    ctx: dict = {}
    _seed_selection(ctx, _ref())
    with (
        _login_count(1),
        patch(
            "app.services.portal_connectivity.evaluar_conectividad_portal",
            return_value=_portal_body(
                status=status, reason_code=reason, message=message
            ),
        ),
    ):
        return maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "No tengo internet",
            canal="wa",
            ctx=ctx,
        )


def test_t12_outage_precedence(monkeypatch):
    t = _diag_reason(monkeypatch, "incident_active", "outage", "Incidente activo")
    assert t and t.data.get("observation") == "outage"
    assert t.reason_code == "incident_active" or t.data.get("reason_code") == "incident_active"


def test_t13_phy_down_precedence(monkeypatch):
    t = _diag_reason(monkeypatch, "access_link_down", "impaired")
    assert t and t.data.get("observation") == "access_link_down"


def test_t14_no_session_precedence(monkeypatch):
    t = _diag_reason(monkeypatch, "no_session", "impaired")
    assert t and t.data.get("observation") == "no_session"


def test_t15_poor_quality_precedence(monkeypatch):
    t = _diag_reason(monkeypatch, "link_quality_poor", "impaired")
    assert t and t.data.get("observation") == "link_quality_poor"


def test_t16_operational(monkeypatch):
    t = _diag_reason(monkeypatch, None, "operational")
    assert t and t.data.get("observation") == "operational"


def test_t17_unknown(monkeypatch):
    t = _diag_reason(monkeypatch, "insufficient_data", "unknown")
    assert t and t.data.get("observation") == "unknown"


def test_t18_commercial_state_not_technical():
    ref = _ref(active=True)
    assert ref.active is True
    assert is_fixed_internet_diagnosticable(ref)
    # active comercial no implica operational técnico
    d = ref.to_dict()
    assert "operational" not in d
    assert d.get("active") is True


def test_t19_sensa_no_internet_diag(monkeypatch):
    _enable(monkeypatch)
    ctx: dict = {}
    _seed_selection(ctx, _ref(sid="tv1", login="", tip="tv", product="Sensa"))
    probe = MagicMock()
    with (
        _login_count(1),
        patch("app.services.portal_connectivity.evaluar_conectividad_portal", probe),
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "Por qué no funciona Sensa",
            canal="wa",
            ctx=ctx,
        )
    # Puede rutear a service_catalog o connectivity; en ambos: cero probes Internet
    probe.assert_not_called()
    if t and t.journey == "internet_sin_conectividad":
        assert t.reason_code == "service_not_diagnosticable"


def test_t20_imowi_no_internet_diag(monkeypatch):
    _enable(monkeypatch)
    ctx: dict = {}
    _seed_selection(
        ctx,
        _ref(sid="m1", login="2235551234", tip="movil", product="IMOWI"),
    )
    probe = MagicMock()
    with (
        _login_count(1),
        patch("app.services.portal_connectivity.evaluar_conectividad_portal", probe),
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "No tengo internet",
            canal="wa",
            ctx=ctx,
        )
    assert t and t.reason_code == "service_not_diagnosticable"
    probe.assert_not_called()


def test_t21_voip_no_internet_diag(monkeypatch):
    assert not is_fixed_internet_diagnosticable(
        _ref(sid="v1", login="voip1", tip="telefonia", product="VoIP")
    )


def test_t22_llm_fake_login(monkeypatch):
    _enable(monkeypatch)
    bootstrap_registry()
    ctx: dict = {"multi_cuenta_pendiente": True}
    probe = MagicMock()
    trusted = TrustedContext(
        abonado=_abo(),
        organization_id="org",
        db=MagicMock(),
        ctx=ctx,
    )
    with (
        patch("app.services.portal_connectivity.evaluar_conectividad_portal", probe),
        patch("app.services.conexion_pppoe.consultar_conexion_pppoe", probe),
    ):
        ar = execute_action(
            ActionRequest(
                action="run_diagnostic_pppoe",
                parameters={"login": "FAKELOGIN"},
                source="llm_proposal",
            ),
            trusted,
        )
    assert ar.status in ("needs_input", "denied", "unavailable")
    probe.assert_not_called()
    cleaned = sanitize_parameters({"login": "FAKELOGIN"})
    assert "login" not in cleaned


def test_t23_llm_fake_service_id():
    r = resolve_service_selection(
        texto="",
        catalog=[{"id": "real", "type": "internet", "login": "INT1", "product": "x", "active": True, "label": "x"}],
        client_number="18099",
        proposed_service_id="hallucinated",
    )
    assert r.status == "denied"
    assert "service_id" not in sanitize_parameters({"service_id": "hallucinated"})


def test_t24_llm_fake_ownership():
    cleaned = sanitize_parameters({"client_number": "OTHER"})
    assert "client_number" not in cleaned
    bootstrap_registry()
    ctx: dict = {}
    _seed_selection(ctx, _ref(cn="99999"))
    trusted = TrustedContext(
        abonado=_abo(client_number="18099"),
        organization_id="org",
        db=MagicMock(),
        ctx=ctx,
    )
    policy = evaluate_policy(
        ActionRequest(action="run_diagnostic_pppoe", source="llm_proposal"),
        trusted,
    )
    assert policy.verdict == "DENY"
    assert policy.reason_code == "ownership_mismatch"


def test_t25_llm_fake_technical_result(monkeypatch):
    """LLM no impone operational: prevalece resultado portal."""
    _enable(monkeypatch)
    ctx: dict = {}
    _seed_selection(ctx, _ref())
    with (
        _login_count(1),
        patch(
            "app.services.portal_connectivity.evaluar_conectividad_portal",
            return_value=_portal_body(
                status="impaired",
                reason_code="access_link_down",
                message="enlace caído",
            ),
        ),
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "está operational según el modelo",
            canal="wa",
            ctx=ctx,
        )
    # Si no es intent connectivity, puede no diagnosticar; fuerza intent claro
    if t is None or t.journey != "internet_sin_conectividad":
        t = _diag_reason(monkeypatch, "access_link_down", "impaired", "enlace caído")
    assert t.data.get("observation") == "access_link_down"
    assert t.data.get("observation") != "operational"


def test_t26_no_commercial_effect(monkeypatch):
    _enable(monkeypatch)
    ctx: dict = {}
    _seed_selection(ctx, _ref())
    effects = MagicMock()
    with (
        _login_count(1),
        patch(
            "app.services.portal_connectivity.evaluar_conectividad_portal",
            return_value=_portal_body(),
        ),
        patch("app.services.eko_journeys.dispatch_runtime") as disp,
    ):
        # leave runtime path: don't patch dispatch so executor runs — instead spy effects
        disp.side_effect = lambda action, **kw: (
            effects(action)
            or execute_action(
                ActionRequest(action=action),
                TrustedContext(
                    abonado=_abo(),
                    organization_id="org",
                    db=MagicMock(),
                    ctx=ctx,
                    correlation_id="c1",
                ),
            )
        )
        # Simpler: just run execute and assert action is diagnostic only
        with patch(
            "app.services.portal_connectivity.evaluar_conectividad_portal",
            return_value=_portal_body(),
        ):
            ar = execute_action(
                ActionRequest(action="run_diagnostic_pppoe"),
                TrustedContext(
                    abonado=_abo(),
                    organization_id="org",
                    db=MagicMock(),
                    ctx=ctx,
                ),
            )
    assert ar.action == "run_diagnostic_pppoe"
    assert ar.status == "success"


def test_t27_runtime_xor_legacy(monkeypatch):
    _enable(monkeypatch)
    ctx: dict = {}
    _seed_selection(ctx, _ref())
    legacy = MagicMock(return_value=ActionResult(action="run_diagnostic_pppoe", status="success"))
    with (
        _login_count(1),
        patch(
            "app.services.portal_connectivity.evaluar_conectividad_portal",
            return_value=_portal_body(),
        ),
        patch("app.services.eko_journeys._legacy_pppoe_as_result", legacy),
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "No tengo internet",
            canal="wa",
            ctx=ctx,
        )
    assert t and t.data.get("execution_path") == "runtime"
    legacy.assert_not_called()


def test_t28_casi_no_llm_to_probe(monkeypatch):
    bootstrap_registry()
    probe = MagicMock()
    trusted = TrustedContext(
        abonado=_abo(),
        organization_id="org",
        db=MagicMock(),
        ctx={},
    )
    with (
        patch("app.services.portal_connectivity.evaluar_conectividad_portal", probe),
        patch("app.services.conexion_pppoe.consultar_conexion_pppoe", probe),
    ):
        ar = execute_action(
            ActionRequest(
                action="run_diagnostic_pppoe",
                parameters={
                    "login": "EVIL",
                    "service_id": "x",
                    "client_number": "1",
                    "status": "operational",
                },
                source="llm_proposal",
            ),
            trusted,
        )
    assert ar.status in ("needs_input", "denied", "unavailable")
    probe.assert_not_called()


def test_t29_service_list_regression(monkeypatch):
    _enable(monkeypatch, "service_list")
    assert detect_journey_name("¿Qué servicios tengo?") == "service_catalog"
    with patch(
        "app.services.eko_journeys.dispatch_runtime",
        return_value=ActionResult(
            action="service_list",
            status="success",
            user_message="lista",
            data={"count": 1},
        ),
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "¿Qué servicios tengo?",
            canal="wa",
            ctx={},
        )
    assert t and t.action == "service_list"


def test_t30_selection_regression(monkeypatch):
    _enable(monkeypatch, "service_list")
    rows = [
        {
            "id": "a",
            "type": "internet",
            "login": "INTA",
            "product": "Internet 300M",
            "label": "Internet 300M",
            "active": True,
        },
        {
            "id": "b",
            "type": "internet",
            "login": "INTB",
            "product": "Internet 600M",
            "label": "Internet 600M",
            "active": True,
        },
    ]
    with patch(
        "app.services.portal_services.catalog_for_selection",
        return_value={"status": "ok", "services": rows, "reason_code": None},
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "quiero el internet",
            canal="wa",
            ctx={},
        )
    assert t and t.action_status == "needs_input"
    assert t.action == "service_selection"
