"""Eko 2.5D-3 — Domain stack / natural-language resume.

Reuses ConversationState.domain_stack (slot ids). Does not mutate ServiceRef
or execute Runtime on resume alone.
"""

from __future__ import annotations

from app.domain.conversation_state import (
    KIND_ADMIN,
    KIND_COMERCIAL,
    KIND_TECNICO,
    MAX_STACK,
    hydrate_conversation_state,
    push_domain_stack,
)
from app.domain.domain_adapter import apply_turn_domain
from app.domain.domain_lifecycle import (
    apply_domain_resume,
    create_domain,
    looks_like_domain_resume,
    new_conversation_state,
    pause_domain,
    previous_domain_from_stack,
    resolve_domain_resume,
    resume_domain,
)
from app.services.eko_journeys import apply_service_ref, get_journey
from app.services.eko_service_selection import (
    ServiceRef,
    get_selected_ref,
    resolve_service_selection,
)


def _stack_three_kinds() -> object:
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet", activate=True)
    pause_domain(cs)
    create_domain(cs, kind=KIND_ADMIN, playbook="facturacion", activate=True)
    pause_domain(cs)
    create_domain(cs, kind=KIND_COMERCIAL, playbook="alta_plan", activate=True)
    return cs


# ---------------------------------------------------------------------------
# A) Stack basics (reuse push_domain_stack)
# ---------------------------------------------------------------------------


def test_2_5d3_stack_first_domain():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet", activate=True)
    assert cs.domain_stack == ["tec-1"]
    assert cs.active_domain_id == "tec-1"


def test_2_5d3_stack_second_domain():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet", activate=True)
    pause_domain(cs)
    create_domain(cs, kind=KIND_ADMIN, playbook="facturacion", activate=True)
    assert cs.active_domain_id == "adm-1"
    assert cs.domain_stack[0] == "adm-1"
    assert "tec-1" in cs.domain_stack
    assert len(cs.domain_stack) == 2


def test_2_5d3_stack_max_three():
    cs = _stack_three_kinds()
    assert len(cs.domain_stack) == 3
    assert len(cs.domain_stack) <= MAX_STACK


def test_2_5d3_stack_fourth_keeps_window_of_three():
    """Solo hay 3 kinds; re-push mueve a frente sin crecer."""
    cs = _stack_three_kinds()
    # Re-activar tecnico (4ª transición lógica)
    resume_domain(cs, "tec-1")
    assert len(cs.domain_stack) <= MAX_STACK
    assert cs.domain_stack[0] == "tec-1"
    assert cs.domain_stack.count("tec-1") == 1


def test_2_5d3_stack_repeat_current_no_dupe():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet", activate=True)
    push_domain_stack(cs, "tec-1")
    push_domain_stack(cs, "tec-1")
    assert cs.domain_stack.count("tec-1") == 1


def test_2_5d3_stack_no_service_ref_fields():
    cs = _stack_three_kinds()
    blob = " ".join(cs.domain_stack)
    assert "login" not in blob
    assert "client" not in blob
    assert all(x in ("tec-1", "adm-1", "com-1") for x in cs.domain_stack)


# ---------------------------------------------------------------------------
# B) Resume explícito
# ---------------------------------------------------------------------------


def test_2_5d3_volvamos_internet_when_tecnico_in_stack():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet", activate=True)
    pause_domain(cs)
    create_domain(cs, kind=KIND_ADMIN, playbook="facturacion", activate=True)
    r = resolve_domain_resume(cs, "volvamos a lo de internet")
    assert r.status == "resolved"
    assert r.kind == KIND_TECNICO
    assert r.domain_id == "tec-1"


def test_2_5d3_retomemos_factura_when_admin_in_stack():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_ADMIN, playbook="facturacion", activate=True)
    pause_domain(cs)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet", activate=True)
    r = resolve_domain_resume(cs, "retomemos lo de la factura")
    assert r.status == "resolved"
    assert r.kind == KIND_ADMIN
    assert r.domain_id == "adm-1"


def test_2_5d3_sigamos_problema_internet():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet", activate=True)
    pause_domain(cs)
    create_domain(cs, kind=KIND_ADMIN, playbook="facturacion", activate=True)
    r = resolve_domain_resume(cs, "sigamos con el problema de internet")
    assert r.status == "resolved"
    assert r.domain_id == "tec-1"


def test_2_5d3_topic_absent_from_stack_needs_input():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_ADMIN, playbook="facturacion", activate=True)
    r = resolve_domain_resume(cs, "volvamos a lo de internet")
    assert r.status == "needs_input"
    assert r.reason_code == "resume_not_in_stack"


def test_2_5d3_unknown_topic_needs_input():
    cs = _stack_three_kinds()
    r = resolve_domain_resume(cs, "volvamos a lo de la nave espacial")
    assert r.status == "needs_input"
    assert r.reason_code == "resume_unknown_topic"


# ---------------------------------------------------------------------------
# C) lo anterior
# ---------------------------------------------------------------------------


def test_2_5d3_lo_anterior_unique_previous():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet", activate=True)
    pause_domain(cs)
    create_domain(cs, kind=KIND_ADMIN, playbook="facturacion", activate=True)
    assert previous_domain_from_stack(cs) == "tec-1"
    r = resolve_domain_resume(cs, "volvamos a lo anterior")
    assert r.status == "resolved"
    assert r.domain_id == "tec-1"


def test_2_5d3_lo_anterior_with_three_picks_immediate_previous():
    cs = _stack_three_kinds()
    # current com-1; immediate previous = stack[1]
    prev = previous_domain_from_stack(cs)
    assert prev == cs.domain_stack[1]
    r = resolve_domain_resume(cs, "retomemos lo anterior")
    assert r.status == "resolved"
    assert r.domain_id == prev


def test_2_5d3_lo_anterior_no_previous_needs_input():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet", activate=True)
    r = resolve_domain_resume(cs, "volvamos a lo anterior")
    assert r.status == "needs_input"
    assert r.reason_code == "resume_no_previous"


def test_2_5d3_lo_anterior_empty_stack_needs_input():
    cs = new_conversation_state(turn=1)
    r = resolve_domain_resume(cs, "sigamos con lo anterior")
    assert r.status == "needs_input"


# ---------------------------------------------------------------------------
# D) Service continuity
# ---------------------------------------------------------------------------


def test_2_5d3_resume_does_not_change_selected_service_ref():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet", activate=True)
    pause_domain(cs)
    create_domain(cs, kind=KIND_ADMIN, playbook="facturacion", activate=True)
    ctx: dict = {"cs": cs.to_dict()}
    ref = ServiceRef(
        service_id="tv-1",
        login="",
        service_type="tv",
        client_number="18099",
        label="Sensa",
        product="Sensa",
        active=True,
    )
    apply_service_ref(ctx, ref)
    before = get_selected_ref(ctx)
    assert before and before.service_id == "tv-1"
    apply_domain_resume(cs, "volvamos a lo de internet")
    ctx["cs"] = cs.to_dict()
    after = get_selected_ref(ctx)
    assert after and after.service_id == "tv-1"
    assert after.client_number == "18099"
    assert get_journey(ctx).get("selected_service_ref", {}).get("service_id") == "tv-1"


def test_2_5d3_resume_does_not_create_service_ref():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet", activate=True)
    pause_domain(cs)
    create_domain(cs, kind=KIND_ADMIN, playbook="facturacion", activate=True)
    ctx: dict = {}
    apply_domain_resume(cs, "volvamos a lo de internet")
    assert get_selected_ref(ctx) is None


def test_2_5d3_resume_does_not_start_diagnostic():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet", activate=True)
    pause_domain(cs)
    create_domain(cs, kind=KIND_ADMIN, playbook="facturacion", activate=True)
    ctx: dict = {
        "eko_journey": {
            "name": "billing_self_service",
            "diagnostic_started": False,
            "selected_service_ref": {
                "service_id": "i1",
                "login": "INT1",
                "service_type": "internet",
                "client_number": "18099",
            },
        }
    }
    apply_domain_resume(cs, "volvamos a lo de internet")
    assert get_journey(ctx).get("diagnostic_started") is False


# ---------------------------------------------------------------------------
# E / F) Authority / LLM
# ---------------------------------------------------------------------------


def test_2_5d3_llm_unknown_kind_rejected():
    cs = _stack_three_kinds()
    r = resolve_domain_resume(
        cs, "volvamos a lo anterior", proposed_kind="connectivity"
    )
    assert r.status == "needs_input"
    assert r.reason_code == "resume_unknown_kind"


def test_2_5d3_llm_kind_not_in_stack_needs_input():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_ADMIN, playbook="facturacion", activate=True)
    r = resolve_domain_resume(
        cs,
        "",
        proposed_kind=KIND_TECNICO,
        resume_requested=True,
    )
    assert r.status == "needs_input"
    assert r.reason_code == "resume_not_in_stack"


def test_2_5d3_llm_cannot_write_domain_stack_directly():
    """No hay API de escritura libre: hydrate ignora basura no-id."""
    cs = hydrate_conversation_state(
        {
            "cs": {
                "v": 1,
                "turn": 1,
                "active_domain_id": "tec-1",
                "domain_stack": ["tec-1", "EVIL_STACK", {"hack": True}],
                "domains": [
                    {
                        "id": "tec-1",
                        "kind": "tecnico",
                        "playbook": "internet",
                        "status": "active",
                        "covered_steps": [],
                        "cursor": 0,
                    }
                ],
                "facts": [],
            }
        }
    )
    assert "EVIL_STACK" not in cs.domain_stack
    assert all(isinstance(x, str) for x in cs.domain_stack)


def test_2_5d3_apply_turn_domain_resume_wired():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet", activate=True)
    pause_domain(cs)
    create_domain(cs, kind=KIND_ADMIN, playbook="facturacion", activate=True)
    trans = apply_turn_domain(cs, "volvamos a lo de internet")
    assert trans.resumed is True
    assert trans.reason == "nl_resume"
    assert cs.active_domain_id == "tec-1"


def test_2_5d3_apply_turn_domain_resume_needs_input_no_create():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_ADMIN, playbook="facturacion", activate=True)
    before = list(cs.domains)
    trans = apply_turn_domain(cs, "volvamos a lo de internet")
    assert trans.reason == "resume_needs_input"
    assert trans.changed is False
    assert len(cs.domains) == len(before)
    assert cs.active_domain_id == "adm-1"


# ---------------------------------------------------------------------------
# G) Regression 2.5D-2 / ese
# ---------------------------------------------------------------------------


def test_2_5d3_regression_el_fijo():
    cat = [
        {
            "id": "t1",
            "type": "telefonia",
            "product": "Fija",
            "label": "Teléfono",
            "login": "",
            "active": True,
        }
    ]
    r = resolve_service_selection(texto="el fijo", catalog=cat, client_number="18099")
    assert r.status == "selected"


def test_2_5d3_regression_el_otro():
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
    assert r.status == "selected" and r.ref and r.ref.service_id == "t1"


def test_2_5d3_regression_ese_multi():
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
            "type": "tv",
            "product": "Sensa",
            "login": "",
            "active": True,
        },
    ]
    r = resolve_service_selection(texto="ese", catalog=cat, client_number="18099")
    assert r.status == "needs_input"


def test_2_5d3_looks_like_cues():
    assert looks_like_domain_resume("volvamos a lo anterior")
    assert looks_like_domain_resume("volviendo a lo anterior")
    assert looks_like_domain_resume("retomemos lo de la factura")
    assert not looks_like_domain_resume("¿cuánto debo?")
    assert not looks_like_domain_resume("el fijo")
