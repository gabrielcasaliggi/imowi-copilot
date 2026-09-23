"""Eko 2.6K — create_ticket Runtime activation (allowlist + CASI/XOR)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.services.eko_action_bridge as bridge
from app.config import ACTION_RUNTIME_ACTIONS
from app.estate import repository as repo
from app.estate.models import Abonado, ConversacionCanal, TicketEvent
from app.services.eko_action_coverage import coverage_for
from app.services.eko_action_runtime import (
    ActionRequest,
    TrustedContext,
    execute_action,
    parse_llm_action_proposal,
    sanitize_parameters,
)
from app.services.eko_ticket_proactive import map_ticket_event_type


def _abo_ns(**kwargs):
    d = {
        "id": "abo-26k",
        "organizacion_id": "org-1",
        "nombre": "María",
        "dni": "30126001",
        "servicio": "internet",
        "plan": "100Mb",
        "estado": "activo",
        "linea_msisdn": "2235126001",
        "client_number": "200",
    }
    d.update(kwargs)
    return SimpleNamespace(**d)


def _conv_ns(**kwargs):
    d = {
        "id": "conv-26k",
        "ticket_id": "",
        "estado": "bot",
        "telefono": "2235126001",
        "canal": "whatsapp",
        "abonado_id": "abo-26k",
        "servicio_detectado": "",
    }
    d.update(kwargs)
    return SimpleNamespace(**d)


def _trusted(
    *,
    conv=None,
    abonado=None,
    confirmation_received: bool = False,
    confirmation_rejected: bool = False,
    ctx: dict | None = None,
    db=None,
    org_id: str = "org-1",
) -> TrustedContext:
    return TrustedContext(
        conversation_id="conv-26k",
        organization_id=org_id,
        abonado_id=getattr(abonado, "id", None) if abonado else "abo-26k",
        abonado=abonado if abonado is not None else _abo_ns(),
        conv=conv if conv is not None else _conv_ns(),
        ctx=ctx if ctx is not None else {},
        db=db if db is not None else MagicMock(),
        canal="wa",
        confirmation_received=confirmation_received,
        confirmation_rejected=confirmation_rejected,
        decision_name="test_26k",
    )


def _enable_runtime(monkeypatch):
    """ENABLED + default ACTIONS (incluye create_ticket tras 2.6K)."""
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", True)
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ACTIONS", ACTION_RUNTIME_ACTIONS)


# --- Activation / coverage ---


def test_26k_default_actions_includes_create_ticket():
    assert "create_ticket" in ACTION_RUNTIME_ACTIONS
    assert "ticket_customer_note" in ACTION_RUNTIME_ACTIONS
    assert "update_ticket" not in ACTION_RUNTIME_ACTIONS
    assert "escalate_human" not in ACTION_RUNTIME_ACTIONS
    assert "close_conversation" not in ACTION_RUNTIME_ACTIONS


def test_26k_covers_when_enabled(monkeypatch):
    _enable_runtime(monkeypatch)
    assert bridge.action_runtime_covers("create_ticket") is True
    assert coverage_for("create_ticket").status == "EXECUTED_BY_RUNTIME"


def test_26k_covers_false_when_master_off(monkeypatch):
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", False)
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ACTIONS", ACTION_RUNTIME_ACTIONS)
    assert bridge.action_runtime_covers("create_ticket") is False


# --- Confirmation ---


def test_26k_without_confirmation_no_create(monkeypatch):
    _enable_runtime(monkeypatch)
    conv = _conv_ns()
    with patch("app.services.canal_abonado._crear_ticket_n2") as create:
        ar = bridge.dispatch_runtime(
            "create_ticket",
            db=MagicMock(),
            org_id="org-1",
            conv=conv,
            abonado=_abo_ns(),
            ctx={},
            parameters={"motivo": "sin confirmar"},
            texto="quiero un ticket",
            historial=[],
        )
    assert ar is not None
    assert ar.status == "needs_confirmation"
    create.assert_not_called()


def test_26k_with_confirmation_creates(monkeypatch):
    _enable_runtime(monkeypatch)
    ctx = {"eko_action": {"action": "create_ticket", "status": "confirmation_pending"}}
    conv = _conv_ns()
    with patch(
        "app.services.canal_abonado._crear_ticket_n2",
        return_value="TK-26K-NEW",
    ) as create:
        ar = bridge.dispatch_runtime(
            "create_ticket",
            db=MagicMock(),
            org_id="org-1",
            conv=conv,
            abonado=_abo_ns(),
            ctx=ctx,
            parameters={"motivo": "cliente confirma"},
            texto="sí",
            historial=[],
        )
    assert ar is not None
    assert ar.status == "success"
    assert ar.data.get("ticket_id") == "TK-26K-NEW"
    assert create.call_count == 1


# --- Ownership / identity ---


def test_26k_missing_abonado_denied(monkeypatch):
    _enable_runtime(monkeypatch)
    trusted = _trusted(abonado=None, confirmation_received=True)
    trusted.abonado = None
    trusted.abonado_id = None
    r = execute_action(
        ActionRequest(action="create_ticket", parameters={"motivo": "x"}, source="decision"),
        trusted,
    )
    assert r.status == "denied"
    assert r.reason_code == "missing_abonado"


def test_26k_valid_abonado_allow_with_confirm(monkeypatch):
    _enable_runtime(monkeypatch)
    conv = _conv_ns()
    trusted = _trusted(conv=conv, confirmation_received=True)
    with patch(
        "app.services.canal_abonado._crear_ticket_n2",
        return_value="TK-26K-OK",
    ) as create:
        r = execute_action(
            ActionRequest(
                action="create_ticket",
                parameters={"motivo": "escalamiento"},
                source="decision",
            ),
            trusted,
        )
    assert r.status == "success"
    create.assert_called_once()


# --- XOR ---


def test_26k_xor_runtime_on_legacy_zero(monkeypatch):
    _enable_runtime(monkeypatch)
    from app.services.canal_abonado import _ticket_via_runtime_o_legacy

    conv = _conv_ns()
    ctx: dict = {
        "eko_action": {"action": "create_ticket", "status": "confirmation_pending"}
    }
    db = MagicMock()
    with (
        patch(
            "app.services.canal_abonado._crear_ticket_n2",
            return_value="TK-26K-XOR",
        ) as legacy_direct,
        patch(
            "app.services.eko_action_bridge.dispatch_runtime",
            wraps=bridge.dispatch_runtime,
        ) as disp,
        patch("app.estate.canal_repo.list_mensajes", return_value=[]),
    ):
        # When covers: _ticket_via_runtime_o_legacy must NOT call Legacy branch
        # (Legacy branch is the direct _crear_ticket_n2 at start of helper).
        # Executor still calls _crear_ticket_n2 once via Runtime — count that separately.
        tid, pending = _ticket_via_runtime_o_legacy(
            db,
            "org-1",
            conv,
            _abo_ns(),
            "motivo xor",
            ctx=ctx,
            canal="wa",
            texto="sí",
            decision_name="create_ticket",
        )
    assert pending is None
    assert tid == "TK-26K-XOR"
    assert disp.call_count == 1
    assert disp.call_args.args[0] == "create_ticket"
    # Exactly one writer invocation (via executor), not Runtime+Legacy dual
    assert legacy_direct.call_count == 1


def test_26k_xor_gate_off_uses_legacy_only(monkeypatch):
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", False)
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ACTIONS", ACTION_RUNTIME_ACTIONS)
    from app.services.canal_abonado import _ticket_via_runtime_o_legacy

    conv = _conv_ns()
    ctx: dict = {}
    with (
        patch(
            "app.services.canal_abonado._crear_ticket_n2",
            return_value="TK-LEGACY",
        ) as create,
        patch("app.services.eko_action_bridge.dispatch_runtime") as disp,
    ):
        tid, pending = _ticket_via_runtime_o_legacy(
            MagicMock(),
            "org-1",
            conv,
            _abo_ns(),
            "motivo",
            ctx=ctx,
            canal="wa",
            texto="",
        )
    assert tid == "TK-LEGACY"
    assert pending is None
    disp.assert_not_called()
    assert create.call_count == 1


def test_26k_already_done_no_second_ticket(monkeypatch):
    _enable_runtime(monkeypatch)
    conv = _conv_ns(ticket_id="TK-EXIST")
    with patch("app.services.canal_abonado._crear_ticket_n2") as create:
        ar = bridge.dispatch_runtime(
            "create_ticket",
            db=MagicMock(),
            org_id="org-1",
            conv=conv,
            abonado=_abo_ns(),
            ctx={},
            parameters={"motivo": "retry"},
            texto="sí",
            historial=[{"rol": "usuario", "contenido": "sí"}],
        )
    assert ar is not None
    assert ar.status == "already_done"
    create.assert_not_called()


# --- CASI ---


def test_26k_casi_llm_may_propose():
    prop = parse_llm_action_proposal(
        {
            "action": "create_ticket",
            "parameters": {"motivo": "sin internet", "client_number": "HACK"},
            "abonado_id": "fake",
            "actor": "admin",
        }
    )
    assert prop is not None
    assert prop.action == "create_ticket"
    assert prop.source == "llm_proposal"
    assert "client_number" not in prop.parameters
    assert "abonado_id" not in prop.parameters
    assert "actor" not in (prop.parameters or {})


def test_26k_casi_visibility_notify_stripped():
    cleaned = sanitize_parameters(
        {
            "motivo": "x",
            "visible_cliente": "Sí",
            "notify": True,
            "actor": "ops@coop",
            "ownership": "agent",
        }
    )
    assert cleaned.get("motivo") == "x"
    assert "visible_cliente" not in cleaned
    assert "notify" not in cleaned
    assert "actor" not in cleaned
    assert "ownership" not in cleaned


def test_26k_casi_llm_cannot_skip_confirmation(monkeypatch):
    _enable_runtime(monkeypatch)
    prop = parse_llm_action_proposal(
        {
            "action": "create_ticket",
            "parameters": {"motivo": "force", "confirmation": True},
        }
    )
    assert prop is not None
    assert "confirmation" not in prop.parameters
    trusted = _trusted(confirmation_received=False)
    with patch("app.services.canal_abonado._crear_ticket_n2") as create:
        r = execute_action(prop, trusted)
    assert r.status == "needs_confirmation"
    create.assert_not_called()


# --- Event (executor reuses _crear_ticket_n2 → creacion) ---


def test_26k_event_creacion_from_writer(db, monkeypatch):
    """When writer runs, TicketEvent creacion is produced (existing contract)."""
    session, org_id = db
    abo = Abonado(
        organizacion_id=org_id,
        dni="30126099",
        nombre="Abo 26K",
        telefono_e164="2235126099",
        linea_msisdn="2235126099",
        servicio="internet",
        estado="activo",
    )
    session.add(abo)
    session.commit()
    session.refresh(abo)
    conv = ConversacionCanal(
        organizacion_id=org_id,
        canal="wa",
        telefono="2235126099",
        abonado_id=abo.id,
        ticket_id="",
        estado="bot",
    )
    session.add(conv)
    session.commit()
    session.refresh(conv)

    _enable_runtime(monkeypatch)
    trusted = TrustedContext(
        conversation_id=conv.id,
        organization_id=org_id,
        abonado_id=abo.id,
        abonado=abo,
        conv=conv,
        ctx={},
        db=session,
        canal="wa",
        confirmation_received=True,
        confirmation_rejected=False,
        decision_name="test_26k_event",
    )
    r = execute_action(
        ActionRequest(
            action="create_ticket",
            parameters={"motivo": "Event creacion 26K"},
            source="decision",
        ),
        trusted,
    )
    assert r.status == "success"
    tid = r.data.get("ticket_id")
    assert tid
    events = [e for e in repo.list_ticket_events(session, org_id, tid) if e.tipo == "creacion"]
    assert len(events) == 1
    assert events[0].visible_cliente == "Sí"
    assert map_ticket_event_type(events[0]) == "ticket.created"
    # Exactly one creacion Event for this ticket
    assert (
        session.query(TicketEvent)
        .filter_by(organizacion_id=org_id, ticket_id=tid, tipo="creacion")
        .count()
        == 1
    )


# --- No regression note ---


def test_26k_note_still_in_default_and_covers(monkeypatch):
    assert "ticket_customer_note" in ACTION_RUNTIME_ACTIONS
    _enable_runtime(monkeypatch)
    assert bridge.action_runtime_covers("ticket_customer_note") is True
    assert coverage_for("ticket_customer_note").status == "EXECUTED_BY_RUNTIME"
