"""Eko 2.5D-4 — Playbook + handoff continuity.

LOGIC tests for continuity contract. Real return signal = conv.estado → bot
(inbox release / portal); not reconstructed from transcript.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.domain.conversation_state import (
    KIND_ADMIN,
    KIND_TECNICO,
    MAX_STACK,
    hydrate_conversation_state,
)
from app.domain.domain_lifecycle import (
    apply_domain_resume,
    create_domain,
    new_conversation_state,
    pause_domain,
)
from app.services.eko_action_runtime import (
    ActionRequest,
    TrustedContext,
    _exec_escalate_human,
    parse_llm_action_proposal,
    sanitize_parameters,
)
from app.services.eko_handoff_continuity import (
    HANDOFF_KEY,
    get_handoff_meta,
    handoff_is_active,
    playbook_selected_service,
    prepare_return_from_handoff,
    should_ask_service_selection,
    stamp_handoff_out,
    validate_selected_ref_for_return,
)
from app.services.eko_journeys import apply_service_ref, get_journey, set_journey
from app.services.eko_service_selection import (
    ServiceRef,
    get_selected_ref,
    resolve_service_selection,
)


def _ref_internet(**kw) -> ServiceRef:
    base = dict(
        service_id="inet-1",
        login="INT1",
        service_type="internet",
        client_number="18099",
        label="Fibra",
        product="Fibra",
        active=True,
    )
    base.update(kw)
    return ServiceRef(**base)


def _ref_foreign() -> ServiceRef:
    return _ref_internet(service_id="EVIL", login="X", client_number="99999")


# ---------------------------------------------------------------------------
# A) Playbook resume / canonical consume
# ---------------------------------------------------------------------------


def test_2_5d4_resume_tecnico_keeps_selected_service_ref():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet", activate=True)
    pause_domain(cs)
    create_domain(cs, kind=KIND_ADMIN, playbook="facturacion", activate=True)
    ctx: dict = {"cs": cs.to_dict()}
    apply_service_ref(ctx, _ref_internet())
    apply_domain_resume(cs, "volvamos a lo de internet")
    ctx["cs"] = cs.to_dict()
    assert get_selected_ref(ctx).service_id == "inet-1"
    assert cs.active_domain_id == "tec-1"


def test_2_5d4_resume_admin_keeps_selected_service_ref():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_ADMIN, playbook="facturacion", activate=True)
    pause_domain(cs)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet", activate=True)
    ctx: dict = {"cs": cs.to_dict()}
    apply_service_ref(ctx, _ref_internet())
    apply_domain_resume(cs, "retomemos lo de la factura")
    ctx["cs"] = cs.to_dict()
    assert get_selected_ref(ctx).service_id == "inet-1"


def test_2_5d4_playbook_consumes_get_selected_ref_not_legacy():
    ctx: dict = {
        "login_seleccionado": "SHADOW",
        "eko_journey": {"selected_service": "SHADOW"},
    }
    apply_service_ref(ctx, _ref_internet())
    assert playbook_selected_service(ctx).login == "INT1"
    assert playbook_selected_service(ctx).service_id == "inet-1"
    # SoT is ref, not shadow
    assert get_selected_ref(ctx).login != "SHADOW" or get_selected_ref(ctx).login == "INT1"


def test_2_5d4_should_not_ask_when_ref_valid():
    ctx: dict = {}
    apply_service_ref(ctx, _ref_internet())
    assert should_ask_service_selection(ctx, client_number="18099") is False


def test_2_5d4_should_ask_when_no_ref():
    assert should_ask_service_selection({}, client_number="18099") is True


def test_2_5d4_should_ask_when_foreign_ref():
    ctx: dict = {}
    apply_service_ref(ctx, _ref_foreign())
    assert should_ask_service_selection(ctx, client_number="18099") is True


def test_2_5d4_resume_does_not_fabricate_login():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet", activate=True)
    pause_domain(cs)
    create_domain(cs, kind=KIND_ADMIN, playbook="facturacion", activate=True)
    ctx: dict = {}
    apply_domain_resume(cs, "volvamos a lo de internet")
    assert get_selected_ref(ctx) is None
    assert not ctx.get("login_seleccionado")


# ---------------------------------------------------------------------------
# B / C / D) Handoff out + return validation
# ---------------------------------------------------------------------------


def test_2_5d4_stamp_handoff_out_preserves_ref_clears_confirmation():
    ctx: dict = {}
    apply_service_ref(ctx, _ref_internet())
    set_journey(
        ctx,
        name="internet_sin_conectividad",
        pending_confirmation=True,
        step="confirm_action",
        confirmation_correlation="c",
        correlation_id="c",
    )
    from app.services.eko_action_runtime import set_action_state

    set_action_state(
        ctx, action="create_ticket", status="confirmation_pending", confirmation="PENDING"
    )
    meta = stamp_handoff_out(ctx, reason="escalate_human")
    assert meta["active"] is True
    assert meta.get("transcript") is None
    assert meta["selected_service_identity"]["service_id"] == "inet-1"
    assert get_selected_ref(ctx).service_id == "inet-1"
    assert get_journey(ctx).get("pending_confirmation") is False
    assert "handoff" not in (hydrate_conversation_state(ctx).domain_stack)


def test_2_5d4_stamp_does_not_write_client_number_arbitrarily():
    ctx: dict = {"client_number": "18099"}
    apply_service_ref(ctx, _ref_internet())
    stamp_handoff_out(ctx)
    assert ctx.get("client_number") == "18099"
    # identity may mirror ref.cn for validation — not a TrustedContext write
    assert get_handoff_meta(ctx)["is_authority"] is False


def test_2_5d4_escalate_human_stamps_continuity():
    ctx: dict = {}
    apply_service_ref(ctx, _ref_internet())
    conv = SimpleNamespace(estado="bot", id="c1", ticket_id="")
    db = MagicMock()
    trusted = TrustedContext(
        organization_id="org",
        canal="wa",
        db=db,
        conv=conv,
        abonado=None,
        ctx=ctx,
    )
    ar = _exec_escalate_human(ActionRequest(action="escalate_human"), trusted)
    assert ar.status == "success"
    assert handoff_is_active(ctx)
    assert conv.estado == "espera_agente"


def test_2_5d4_return_keeps_valid_selection():
    ctx: dict = {}
    apply_service_ref(ctx, _ref_internet())
    stamp_handoff_out(ctx)
    r = prepare_return_from_handoff(ctx, client_number="18099")
    assert r.status == "restored"
    assert r.service_kept is True
    assert get_selected_ref(ctx).service_id == "inet-1"
    assert handoff_is_active(ctx) is False


def test_2_5d4_return_rejects_foreign_identity():
    ctx: dict = {}
    apply_service_ref(ctx, _ref_internet(client_number="99999"))
    stamp_handoff_out(ctx)
    # Trusted CN differs from selection
    r = prepare_return_from_handoff(ctx, client_number="18099")
    assert r.status in ("needs_input", "rejected")
    assert get_selected_ref(ctx) is None


def test_2_5d4_return_rejects_catalog_miss():
    ctx: dict = {}
    apply_service_ref(ctx, _ref_internet())
    stamp_handoff_out(ctx)
    cat = [{"id": "other", "type": "internet", "login": "INT9"}]
    ok, reason = validate_selected_ref_for_return(
        ctx, client_number="18099", catalog=cat
    )
    assert ok is False
    assert "catalog" in reason
    prepare_return_from_handoff(ctx, client_number="18099", catalog=cat)
    assert get_selected_ref(ctx) is None


def test_2_5d4_return_no_transcript_reconstruction():
    ctx: dict = {HANDOFF_KEY: {"active": True, "transcript": "USER SAID STUFF"}}
    stamp_handoff_out(ctx)  # overwrites with transcript=None
    assert get_handoff_meta(ctx).get("transcript") is None


def test_2_5d4_handoff_not_a_domain():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet", activate=True)
    ctx: dict = {"cs": cs.to_dict()}
    apply_service_ref(ctx, _ref_internet())
    stamp_handoff_out(ctx)
    stack = hydrate_conversation_state(ctx).domain_stack
    assert all(x in ("tec-1", "adm-1", "com-1") for x in stack)
    assert len(stack) <= MAX_STACK


def test_2_5d4_si_after_handoff_confirmation_cleared():
    ctx: dict = {}
    apply_service_ref(ctx, _ref_internet())
    set_journey(
        ctx,
        name="internet_sin_conectividad",
        pending_confirmation=True,
        step="confirm_action",
        confirmation_correlation="c",
        correlation_id="c",
    )
    stamp_handoff_out(ctx)
    prepare_return_from_handoff(ctx, client_number="18099")
    assert get_journey(ctx).get("pending_confirmation") is False


def test_2_5d4_llm_cannot_inject_handoff_or_stack():
    cleaned = sanitize_parameters(
        {
            "eko_handoff": {"active": True, "selected_service_identity": {"service_id": "X"}},
            "domain_stack": ["hack"],
            "selected_service_ref": {"service_id": "X"},
            "client_number": "999",
            "foo": "bar",
        }
    )
    assert "eko_handoff" not in cleaned
    assert "domain_stack" not in cleaned
    assert "selected_service_ref" not in cleaned
    assert "client_number" not in cleaned
    assert cleaned.get("foo") == "bar"
    assert parse_llm_action_proposal(
        {"action": "escalate_human", "eko_handoff": {"active": True}}
    )


# ---------------------------------------------------------------------------
# G) Service reference regressions
# ---------------------------------------------------------------------------


def test_2_5d4_regression_el_fijo():
    cat = [
        {
            "id": "t1",
            "type": "telefonia",
            "product": "Fija",
            "label": "Tel",
            "login": "",
            "active": True,
        }
    ]
    r = resolve_service_selection(texto="el fijo", catalog=cat, client_number="18099")
    assert r.status == "selected"


def test_2_5d4_regression_el_otro():
    cat = [
        {
            "id": "i1",
            "type": "internet",
            "product": "Fibra",
            "login": "INT1",
            "active": True,
        },
        {
            "id": "t1",
            "type": "telefonia",
            "product": "Fija",
            "login": "",
            "active": True,
        },
    ]
    cur = ServiceRef(
        service_id="i1", login="INT1", service_type="internet", client_number="18099"
    )
    r = resolve_service_selection(
        texto="el otro", catalog=cat, client_number="18099", current_ref=cur
    )
    assert r.status == "selected" and r.ref.service_id == "t1"


def test_2_5d4_regression_ese_multi():
    cat = [
        {
            "id": "i1",
            "type": "internet",
            "product": "Fibra",
            "login": "INT1",
            "active": True,
        },
        {
            "id": "v1",
            "type": "tv",
            "product": "Sensa",
            "login": "",
            "active": True,
        },
    ]
    r = resolve_service_selection(texto="ese", catalog=cat, client_number="18099")
    assert r.status == "needs_input"
