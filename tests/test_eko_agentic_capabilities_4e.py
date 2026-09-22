"""Fase 4E — Agentic Ops Capability Contract (sin migración masiva)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.services.eko_action_bridge as bridge
from app.services.eco_voice import build_contexto_abonado
from app.services.eko_action_bridge import dispatch_runtime
from app.services.eko_action_coverage import coverage_for, coverage_matrix
from app.services.eko_action_runtime import (
    ActionRequest,
    TrustedContext,
    execute_action,
    get_action_state,
    list_registered_actions,
    parse_llm_action_proposal,
    sanitize_parameters,
)
from app.services.eko_capability_contract import (
    AUTHORITY_BOUNDARIES,
    AUTHORIZATION_CONTRACT,
    CONFIRMATION_CONTRACT,
    DIAGNOSTIC_BOUNDARY,
    LLM_MAY,
    LLM_MAY_NOT,
    REQUIRED_CONTRACT_FIELDS,
    all_capabilities,
    build_capability,
    capability_matrix_rows,
    channel_allows,
    contract_invariants,
    is_agentic_decision,
    protocolo_mesa_boundary,
)
from app.services.eko_context import build_eko_facts


def _abo(**kwargs):
    d = {
        "id": "abo-1",
        "organizacion_id": "org-1",
        "nombre": "María",
        "dni": "30111222",
        "servicio": "internet",
        "plan": "100Mb",
        "estado": "activo",
        "deuda_monto": "1500",
        "linea_msisdn": "2235551234",
        "client_number": "200",
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
        "servicio_detectado": "",
    }
    d.update(kwargs)
    return SimpleNamespace(**d)


def _enable(monkeypatch, *actions: str):
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", True)
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ACTIONS", frozenset(actions))


# --- Registry / metadata ---


def test_4e_all_exposed_capabilities_registered():
    registered = set(list_registered_actions())
    for cap in all_capabilities():
        assert cap.name in registered
    inv = contract_invariants()
    assert inv["registered_equals_contracted"] is True
    assert inv["coverage_equals_contracted"] is True
    assert inv["capability_count"] == 15


def test_4e_capability_metadata_required_fields():
    for cap in all_capabilities():
        d = cap.to_dict()
        for field in REQUIRED_CONTRACT_FIELDS:
            assert field in d, f"{cap.name} missing {field}"
            assert d[field] is not None
        assert cap.risk in ("LOW", "MEDIUM", "HIGH")
        assert cap.type in (
            "READ",
            "PRESENTATION",
            "NAVIGATION",
            "DIAGNOSTIC",
            "MUTATION",
            "ESCALATION",
        )
        assert len(cap.preconditions) >= 1
        assert len(cap.postconditions) >= 1


def test_4e_matrix_matches_coverage():
    rows = {r["capability"]: r for r in capability_matrix_rows()}
    for cov in coverage_matrix():
        assert cov.action in rows
        assert rows[cov.action]["n1_runtime"] == cov.status


def test_4e_risk_model_mutating_high():
    for name in ("create_ticket", "update_ticket", "close_conversation", "escalate_human"):
        assert build_capability(name).risk == "HIGH"
        assert build_capability(name).requires_confirmation or name == "update_ticket"


def test_4e_diagnostic_requires_intent_and_selection():
    for name in (
        "run_diagnostic_pppoe",
        "run_diagnostic_bcm",
        "run_diagnostic_uisp",
    ):
        cap = build_capability(name)
        assert cap.requires_diagnostic_intent is True
        assert cap.requires_service_selection is True
        assert cap.risk == "MEDIUM"


# --- Confirmation / authorization ---


def test_4e_mutating_without_confirmation_needs_confirmation(monkeypatch):
    _enable(monkeypatch, "create_ticket")
    with patch("app.services.canal_abonado._crear_ticket_n2") as create:
        ar = dispatch_runtime(
            "create_ticket",
            db=MagicMock(),
            org_id="org-1",
            conv=_conv(),
            abonado=_abo(),
            ctx={},
            parameters={"motivo": "x", "confirmation_received": True},
            source="llm_proposal",
            texto="agente",
            historial=[{"rol": "usuario", "contenido": "agente"}],
        )
    assert ar is not None
    assert ar.status == "needs_confirmation"
    create.assert_not_called()


def test_4e_confirmation_contract_text():
    assert "resolve_user_confirmation" in CONFIRMATION_CONTRACT
    assert "auto_confirmado" in CONFIRMATION_CONTRACT
    assert "LLM" in CONFIRMATION_CONTRACT


def test_4e_authorization_contract_text():
    assert "Trusted Identity" in AUTHORIZATION_CONTRACT
    assert "Policy" in AUTHORIZATION_CONTRACT


def test_4e_foreign_ticket_denied():
    trusted = TrustedContext(
        conversation_id="c",
        organization_id="org-1",
        abonado_id="abo-1",
        abonado=_abo(),
        conv=_conv(),
        ctx={},
        db=MagicMock(),
        correlation_id="c",
    )
    trusted.db.get.return_value = SimpleNamespace(id="foreign", organizacion_id="org-1")
    with patch(
        "app.services.abonado_tickets.ticket_pertenece_abonado",
        return_value=False,
    ):
        r = execute_action(
            ActionRequest(action="show_ticket", parameters={"ticket_id": "foreign"}),
            trusted,
        )
    assert r.status == "denied"
    assert r.reason_code == "foreign_ticket"


# --- LLM boundary ---


def test_4e_llm_may_and_may_not():
    assert "propose_action" in LLM_MAY
    assert "authorize" in LLM_MAY_NOT
    assert "confirm" in LLM_MAY_NOT
    assert "execute_arbitrary_code_or_tool" in LLM_MAY_NOT
    assert LLM_MAY.isdisjoint(LLM_MAY_NOT)


def test_4e_arbitrary_capability_denied():
    r = execute_action(
        ActionRequest(action="arbitrary_http_call", source="llm_proposal"),
        TrustedContext(
            conversation_id="c",
            organization_id="org-1",
            abonado=_abo(),
            conv=_conv(),
            ctx={},
            confirmation_received=True,
        ),
    )
    assert r.status == "denied"
    assert r.reason_code == "unknown_action"
    assert is_agentic_decision(action="arbitrary_http_call", passed_runtime=True) is False


def test_4e_llm_confirmation_stripped():
    req = parse_llm_action_proposal(
        {
            "action": "create_ticket",
            "parameters": {"confirmation_received": True, "abonado_id": "evil"},
        }
    )
    assert req is not None
    assert "confirmation_received" not in req.parameters
    assert "abonado_id" not in sanitize_parameters(
        {"abonado_id": "x", "authorized": True, "dni": "1"}
    )


def test_4e_llm_text_without_runtime_not_agentic():
    assert is_agentic_decision(action="show_balance", passed_runtime=False) is False
    assert is_agentic_decision(action="show_balance", passed_runtime=True) is True


# --- Diagnostic / multi-account ---


def test_4e_diagnostic_boundary_documented():
    assert DIAGNOSTIC_BOUNDARY["normal_conversation"]["probes"] == 0
    assert DIAGNOSTIC_BOUNDARY["multi_account_no_selection"]["probes"] == 0
    assert "required reader" in str(
        DIAGNOSTIC_BOUNDARY["explicit_diagnostic"]["probes"]
    )


def test_4e_normal_zero_probes():
    abo = _abo()
    with (
        patch(
            "app.services.conexion_pppoe.contexto_pppoe_para_abonado",
            side_effect=AssertionError("R"),
        ) as p,
        patch(
            "app.services.conexion_bcm.contexto_bcm_para_abonado",
            side_effect=AssertionError("B"),
        ) as b,
        patch(
            "app.services.conexion_uisp.contexto_uisp_para_abonado",
            side_effect=AssertionError("U"),
        ) as u,
        patch(
            "app.services.outages.abonado_afectado_por_nas",
            side_effect=AssertionError("O"),
        ),
    ):
        build_eko_facts(abo)
        build_contexto_abonado(abo)
    assert p.call_count == b.call_count == u.call_count == 0


def test_4e_multi_account_needs_input_zero_probes(monkeypatch):
    _enable(monkeypatch, "run_diagnostic_pppoe")
    with patch(
        "app.services.conexion_pppoe.consultar_conexion_pppoe",
        side_effect=AssertionError("Radius"),
    ) as radius:
        ar = dispatch_runtime(
            "run_diagnostic_pppoe",
            db=MagicMock(),
            org_id="org-1",
            conv=_conv(),
            abonado=_abo(),
            ctx={"multi_cuenta_pendiente": True},
        )
    assert ar is not None
    assert ar.status == "needs_input"
    radius.assert_not_called()


# --- Idempotency ---


def test_4e_create_ticket_retry_already_done(monkeypatch):
    _enable(monkeypatch, "create_ticket")
    with patch("app.services.canal_abonado._crear_ticket_n2") as create:
        ar = dispatch_runtime(
            "create_ticket",
            db=MagicMock(),
            org_id="org-1",
            conv=_conv(ticket_id="T-EXIST"),
            abonado=_abo(),
            ctx={},
            texto="sí",
            historial=[{"rol": "usuario", "contenido": "sí"}],
            parameters={"motivo": "x"},
        )
    assert ar is not None
    assert ar.status == "already_done"
    create.assert_not_called()
    cap = build_capability("create_ticket")
    assert "conv.ticket_id" in cap.idempotent or "PROTECTED" in cap.idempotent


# --- Runtime / Legacy ---


def test_4e_covered_runtime_uncovered_legacy(monkeypatch):
    _enable(monkeypatch, "show_balance")
    assert coverage_for("show_balance").status == "EXECUTED_BY_RUNTIME"
    assert bridge.action_runtime_covers("show_balance") is True
    assert bridge.action_runtime_covers("create_ticket") is False
    cap_ct = build_capability("create_ticket")
    assert cap_ct.runtime_status == "EXECUTED_BY_RUNTIME"  # wired, not necessarily on
    assert cap_ct.lifecycle in ("CHANNEL_ENABLED", "PRODUCTION_ENABLED")


def test_4e_legacy_capabilities_documented():
    for name in (
        "run_diagnostic_bcm",
        "run_diagnostic_uisp",
        "update_ticket",
        "close_conversation",
        "escalate_human",
        "send_message",
    ):
        cap = build_capability(name)
        assert cap.runtime_status in ("PARTIAL", "RUNTIME_EXECUTOR_ONLY")
        assert cap.why_legacy or cap.migration_precondition


# --- State isolation ---


def test_4e_action_result_to_state_not_facts(monkeypatch):
    _enable(monkeypatch, "show_balance")
    ctx: dict = {}
    with patch(
        "app.services.eko_context.build_eko_facts",
        return_value={"billing": {"status": "live", "balance": "0"}},
    ), patch(
        "app.services.eko_context.billing_amount_str", return_value="0"
    ), patch(
        "app.services.eko_context.has_positive_debt", return_value=False
    ), patch(
        "app.services.eco_voice.mensaje_saldo_padron", return_value="ok"
    ):
        ar = dispatch_runtime(
            "show_balance",
            db=None,
            org_id="org-1",
            conv=_conv(),
            abonado=_abo(),
            ctx=ctx,
            decision_name="consulta_saldo",
        )
    assert ar is not None
    st = get_action_state(ctx)
    assert st.get("last_action") == "show_balance"
    assert "billing" not in st
    assert "dni" not in st
    # Facts layer remains separate
    facts = build_eko_facts(_abo())
    assert "eko_action" not in facts


# --- Channel policy ---


def test_4e_channel_policy():
    assert channel_allows("show_balance", "whatsapp") is True
    assert channel_allows("show_balance", "n1") is True
    # helpdesk not in show_balance allowed set
    assert channel_allows("show_balance", "helpdesk") is False
    assert channel_allows("update_ticket", "helpdesk") is True
    assert channel_allows("unknown_cap", "whatsapp") is False


# --- Authority / protocolo_mesa ---


def test_4e_authority_boundaries_complete():
    for key in (
        "LLM",
        "Facts",
        "State",
        "Decision",
        "Policy",
        "Runtime",
        "Legacy",
        "TechnicalReaders",
    ):
        assert key in AUTHORITY_BOUNDARIES


def test_4e_protocolo_mesa_bounded():
    b = protocolo_mesa_boundary()
    assert b["status"] == "MIXED_BOUNDED"
    assert b["bypass_policy"].startswith("no")
    assert "no Runtime" in b["double_runtime_action"]


def test_4e_lifecycle_distinguishes_executor_from_production(monkeypatch):
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", False)
    cap = build_capability("show_balance")
    assert cap.lifecycle == "CHANNEL_ENABLED"
    assert cap.runtime_status == "EXECUTED_BY_RUNTIME"
    # Executor-only never PRODUCTION_ENABLED while flag irrelevant
    sm = build_capability("send_message")
    assert sm.lifecycle == "TESTED"
