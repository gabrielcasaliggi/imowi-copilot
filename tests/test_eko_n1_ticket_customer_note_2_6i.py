"""Eko 2.6I — N1 wire for ticket_customer_note (Runtime dispatch, CASI, XOR)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.config as app_config
import app.services.eko_action_bridge as bridge
from app.estate import repository as repo
from app.estate.models import Abonado, ConversacionCanal, PortalDevice, TicketEvent
from app.services.eko_action_coverage import coverage_for, runtime_governed_actions
from app.services.eko_action_runtime import (
    ActionRequest,
    TrustedContext,
    execute_action,
    parse_llm_action_proposal,
    sanitize_parameters,
)
from app.services.eko_journeys import (
    _advance_ticket_customer_note,
    _wants_ticket_customer_note,
    detect_journey_name,
    maybe_handle_journey_turn,
)
from app.services.eko_ticket_proactive import (
    emit_ticket_customer_note,
    map_ticket_event_type,
    maybe_deliver_ticket_event_push,
)
from tests.conftest import add_ticket


def _abo(session, org_id: str, *, dni: str, linea: str = "") -> Abonado:
    abo = Abonado(
        organizacion_id=org_id,
        dni=dni,
        nombre=f"Abo {dni}",
        telefono_e164=linea,
        linea_msisdn=linea,
        servicio="internet",
        estado="activo",
    )
    session.add(abo)
    session.commit()
    session.refresh(abo)
    return abo


def _device(session, org_id: str, *, dni: str, token: str) -> PortalDevice:
    row = PortalDevice(
        organizacion_id=org_id,
        dni_normalized=dni,
        expo_push_token=token,
        platform="android",
        activo="Sí",
    )
    session.add(row)
    session.commit()
    return row


def _ticket_with_owner(session, org_id: str, abo: Abonado, *, tid: str):
    linea = abo.linea_msisdn or abo.telefono_e164 or "2235000001"
    t = add_ticket(session, org_id, id=tid, linea=linea, estado="Abierto")
    conv = ConversacionCanal(
        organizacion_id=org_id,
        canal="app",
        telefono=linea,
        abonado_id=abo.id,
        ticket_id=t.id,
        estado="bot",
    )
    session.add(conv)
    session.commit()
    return t, conv


def _ok_send(tokens, *, title, body, data=None):
    return {
        "ok": True,
        "sent": len(tokens),
        "error_category": "ok",
        "retryable": False,
        "provider_message_ids": ["m1"],
        "invalid_tokens": [],
        "invalid_token_fps": [],
    }


def _trusted(session, org_id: str, abo: Abonado, *, ticket_id: str = "") -> TrustedContext:
    return TrustedContext(
        conversation_id="conv-26i",
        organization_id=org_id,
        abonado_id=abo.id,
        abonado=abo,
        conv=MagicMock(id="conv-26i", ticket_id=ticket_id, estado="bot"),
        ctx={},
        db=session,
        canal="app",
        confirmation_received=False,
        confirmation_rejected=False,
        decision_name="test_26i",
    )


def _enable_journeys(monkeypatch):
    monkeypatch.setattr(app_config, "EKO_JOURNEYS_ENABLED", True)


def _enable_runtime(monkeypatch, *actions: str):
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", True)
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ACTIONS", frozenset(actions))


# --- Detection / coverage ---


def test_26i_phrase_detects_note_not_status():
    assert _wants_ticket_customer_note("Quiero dejar una nota: el técnico no vino")
    assert detect_journey_name("dejar nota en el ticket: sin señal") == "ticket_consulta"
    assert not _wants_ticket_customer_note("estado del ticket")


def test_26i_coverage_n1_wired_executed_by_runtime():
    row = coverage_for("ticket_customer_note")
    assert row is not None
    assert row.status == "EXECUTED_BY_RUNTIME"
    assert "ticket_customer_note" in runtime_governed_actions()
    assert coverage_for("update_ticket").status == "RUNTIME_EXECUTOR_ONLY"


# --- Happy path N1 journey → Runtime ---


def test_26i_n1_journey_dispatches_runtime_and_creates_visible_nota(db, monkeypatch):
    session, org_id = db
    abo = _abo(session, org_id, dni="30126001", linea="2235126001")
    t, conv = _ticket_with_owner(session, org_id, abo, tid="TK-26I-1")
    _device(session, org_id, dni="30126001", token="ExponentPushToken[26i-a]")
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "ticket_customer_note")
    ctx: dict = {}
    with (
        patch("app.services.app_push.enviar_push_expo", side_effect=_ok_send) as send,
        patch(
            "app.services.eko_ticket_proactive.maybe_deliver_ticket_event_push",
            wraps=maybe_deliver_ticket_event_push,
        ) as deliver,
    ):
        turn = maybe_handle_journey_turn(
            session,
            org_id,
            conv,
            abo,
            "dejar nota en el ticket: Seguimos sin servicio esta mañana",
            canal="wa",
            ctx=ctx,
        )
    assert turn is not None
    assert turn.action == "ticket_customer_note"
    assert turn.action_status == "success"
    events = [e for e in repo.list_ticket_events(session, org_id, t.id) if e.tipo == "nota"]
    assert len(events) == 1
    assert events[0].visible_cliente == "Sí"
    assert "Seguimos sin servicio" in (events[0].detalle or "")
    assert map_ticket_event_type(events[0]) == "ticket.updated"
    # Proactive detector path entered; N1 abonado actor → SELF_NOTE_NO_PUSH (no Expo)
    assert deliver.call_count >= 1
    assert send.call_count == 0
    assert events[0].actor.startswith("abonado")



# --- Ownership ---


def test_26i_own_ticket_allow(db, monkeypatch):
    session, org_id = db
    abo = _abo(session, org_id, dni="30126002", linea="2235126002")
    t, conv = _ticket_with_owner(session, org_id, abo, tid="TK-26I-2")
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "ticket_customer_note")
    ctx: dict = {}
    turn = maybe_handle_journey_turn(
        session,
        org_id,
        conv,
        abo,
        "agregar al ticket: constancia de corte",
        canal="wa",
        ctx=ctx,
    )
    assert turn is not None
    assert turn.action_status == "success"
    assert any(
        e.tipo == "nota" and e.visible_cliente == "Sí"
        for e in repo.list_ticket_events(session, org_id, t.id)
    )


def test_26i_foreign_ticket_deny(db, monkeypatch):
    session, org_id = db
    owner = _abo(session, org_id, dni="30126003", linea="2235126003")
    other = _abo(session, org_id, dni="30126004", linea="2235126004")
    foreign_tid = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeee0003"
    t, _ = _ticket_with_owner(session, org_id, owner, tid=foreign_tid)
    other_conv = ConversacionCanal(
        organizacion_id=org_id,
        canal="app",
        telefono="2235126004",
        abonado_id=other.id,
        ticket_id="",  # no link — ownership solo vía ticket_id en texto
        estado="bot",
    )
    session.add(other_conv)
    session.commit()
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "ticket_customer_note")
    ctx: dict = {}
    turn = maybe_handle_journey_turn(
        session,
        org_id,
        other_conv,
        other,
        f"dejar nota {foreign_tid}: intento ajeno",
        canal="wa",
        ctx=ctx,
    )
    assert turn is not None
    assert turn.action_status == "denied"
    assert turn.reason_code == "foreign_ticket"
    assert not any(
        e.detalle and "intento ajeno" in e.detalle
        for e in repo.list_ticket_events(session, org_id, t.id)
    )


def test_26i_unresolved_ownership_no_effect(db, monkeypatch):
    session, org_id = db
    abo = _abo(session, org_id, dni="30126005", linea="2235126005")
    conv = ConversacionCanal(
        organizacion_id=org_id,
        canal="app",
        telefono="2235126005",
        abonado_id=abo.id,
        ticket_id="",
        estado="bot",
    )
    session.add(conv)
    session.commit()
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "ticket_customer_note")
    ctx: dict = {}
    turn = maybe_handle_journey_turn(
        session,
        org_id,
        conv,
        abo,
        "dejar nota: sin ticket asociado",
        canal="wa",
        ctx=ctx,
    )
    assert turn is not None
    assert turn.action_status == "needs_input"
    assert turn.reason_code == "missing_ticket"
    assert session.query(TicketEvent).filter_by(organizacion_id=org_id).count() == 0


def test_26i_llm_cannot_override_ownership(db):
    session, org_id = db
    owner = _abo(session, org_id, dni="30126006", linea="2235126006")
    other = _abo(session, org_id, dni="30126007", linea="2235126007")
    t, _ = _ticket_with_owner(session, org_id, owner, tid="TK-26I-4")
    prop = parse_llm_action_proposal(
        {
            "action": "ticket_customer_note",
            "parameters": {
                "ticket_id": t.id,
                "mensaje": "steal",
                "abonado_id": other.id,
                "ownership": "agent_authorized",
                "actor": "ops@coop",
            },
            "abonado_id": other.id,
        }
    )
    assert prop is not None
    assert "abonado_id" not in prop.parameters
    assert "ownership" not in prop.parameters
    assert "actor" not in prop.parameters
    trusted = _trusted(session, org_id, other, ticket_id=t.id)
    r = execute_action(prop, trusted)
    assert r.status == "denied"
    assert r.reason_code == "foreign_ticket"


# --- Ambiguity ---


def test_26i_multiple_tickets_needs_input(db, monkeypatch):
    session, org_id = db
    abo = _abo(session, org_id, dni="30126008", linea="2235126008")
    add_ticket(session, org_id, id="TK-26I-5A", linea="2235126008", estado="Abierto")
    add_ticket(session, org_id, id="TK-26I-5B", linea="2235126008", estado="Abierto")
    conv = ConversacionCanal(
        organizacion_id=org_id,
        canal="app",
        telefono="2235126008",
        abonado_id=abo.id,
        ticket_id="",
        estado="bot",
    )
    session.add(conv)
    session.commit()
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "ticket_customer_note")
    ctx: dict = {}
    turn = maybe_handle_journey_turn(
        session,
        org_id,
        conv,
        abo,
        "dejar nota: texto ambiguo multi",
        canal="wa",
        ctx=ctx,
    )
    assert turn is not None
    assert turn.action_status == "needs_input"
    assert turn.reason_code == "ambiguous_ticket"
    assert session.query(TicketEvent).filter_by(organizacion_id=org_id).count() == 0


def test_26i_no_selected_ticket_needs_input(db, monkeypatch):
    session, org_id = db
    abo = _abo(session, org_id, dni="30126009", linea="2235126009")
    conv = SimpleNamespace(
        id="conv-empty",
        ticket_id="",
        estado="bot",
        telefono="2235126009",
        canal="wa",
        abonado_id=abo.id,
    )
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "ticket_customer_note")
    turn = _advance_ticket_customer_note(
        db=session,
        org_id=org_id,
        conv=conv,
        abonado=abo,
        texto="nota al ticket: hi",
        ctx={},
        canal="wa",
    )
    assert turn.action_status == "needs_input"
    assert turn.reason_code in ("missing_ticket", "missing_message")


# --- Separation update_ticket ---


def test_26i_update_ticket_remains_internal_no_nota_no_push(db):
    session, org_id = db
    abo = _abo(session, org_id, dni="30126010", linea="2235126010")
    t, _ = _ticket_with_owner(session, org_id, abo, tid="TK-26I-6")
    _device(session, org_id, dni="30126010", token="ExponentPushToken[26i-u]")
    trusted = _trusted(session, org_id, abo, ticket_id=t.id)
    with patch("app.services.app_push.enviar_push_expo", side_effect=_ok_send) as send:
        r = execute_action(
            ActionRequest(
                action="update_ticket",
                parameters={"ticket_id": t.id, "nota": "evidencia interna N1"},
                source="decision",
            ),
            trusted,
        )
    assert r.status == "success"
    events = repo.list_ticket_events(session, org_id, t.id)
    assert not any(e.tipo == "nota" and e.visible_cliente == "Sí" for e in events)
    assert send.call_count == 0


# --- CASI ---


def test_26i_casi_llm_may_propose_note():
    prop = parse_llm_action_proposal(
        {
            "action": "ticket_customer_note",
            "parameters": {"ticket_id": "T1", "mensaje": "hola"},
        }
    )
    assert prop is not None
    assert prop.action == "ticket_customer_note"
    assert prop.source == "llm_proposal"


def test_26i_casi_visible_false_cannot_suppress(db):
    session, org_id = db
    abo = _abo(session, org_id, dni="30126011", linea="2235126011")
    t, _ = _ticket_with_owner(session, org_id, abo, tid="TK-26I-7")
    cleaned = sanitize_parameters(
        {"mensaje": "x", "visible_cliente": "No", "ticket_id": t.id}
    )
    assert "visible_cliente" not in cleaned
    trusted = _trusted(session, org_id, abo, ticket_id=t.id)
    r = execute_action(
        ActionRequest(
            action="ticket_customer_note",
            parameters={**cleaned, "visible_cliente": "No"},
            source="llm_proposal",
        ),
        trusted,
    )
    # Even if raw key sneaks past (execute re-sanitizes), event is always Sí
    assert r.status == "success"
    evs = [e for e in repo.list_ticket_events(session, org_id, t.id) if e.tipo == "nota"]
    assert len(evs) == 1
    assert evs[0].visible_cliente == "Sí"


def test_26i_casi_visible_true_is_not_authority():
    cleaned = sanitize_parameters({"visible_cliente": "Sí", "mensaje": "m", "notify": True})
    assert "visible_cliente" not in cleaned
    assert "notify" not in cleaned


def test_26i_casi_notify_true_cannot_trigger_delivery_directly(db):
    session, org_id = db
    abo = _abo(session, org_id, dni="30126012", linea="2235126012")
    t, _ = _ticket_with_owner(session, org_id, abo, tid="TK-26I-8")
    prop = parse_llm_action_proposal(
        {
            "action": "ticket_customer_note",
            "parameters": {
                "ticket_id": t.id,
                "mensaje": "con notify",
                "notify": True,
                "push": True,
            },
        }
    )
    assert prop is not None
    assert "notify" not in prop.parameters
    assert "push" not in prop.parameters
    # Proposal alone does not call push
    with patch("app.services.app_push.enviar_push_expo", side_effect=_ok_send) as send:
        assert send.call_count == 0


def test_26i_casi_arbitrary_event_type_ignored():
    cleaned = sanitize_parameters(
        {"mensaje": "x", "tipo": "estado", "event_type": "ticket.closed"}
    )
    assert "tipo" not in cleaned
    assert "event_type" not in cleaned


def test_26i_casi_llm_cannot_write_ticket_event_or_push_directly():
    """LLM path is proposal-only; no repository/push APIs on proposal."""
    prop = parse_llm_action_proposal(
        {
            "action": "ticket_customer_note",
            "parameters": {"ticket_id": "T", "mensaje": "m", "tipo": "nota"},
        }
    )
    assert prop is not None
    assert not hasattr(prop, "add_ticket_event")
    assert prop.source == "llm_proposal"


# --- XOR ---


def test_26i_xor_one_intent_one_runtime_one_event_at_most_one_push(db, monkeypatch):
    session, org_id = db
    abo = _abo(session, org_id, dni="30126013", linea="2235126013")
    t, conv = _ticket_with_owner(session, org_id, abo, tid="TK-26I-9")
    _device(session, org_id, dni="30126013", token="ExponentPushToken[26i-x]")
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "ticket_customer_note")
    ctx: dict = {}
    with (
        patch("app.services.app_push.enviar_push_expo", side_effect=_ok_send) as send,
        patch(
            "app.services.eko_journeys.dispatch_runtime",
            wraps=bridge.dispatch_runtime,
        ) as disp,
    ):
        turn = maybe_handle_journey_turn(
            session,
            org_id,
            conv,
            abo,
            "dejar nota: XOR única",
            canal="wa",
            ctx=ctx,
        )
    assert turn is not None
    assert turn.action_status == "success"
    assert disp.call_count == 1
    assert disp.call_args.args[0] == "ticket_customer_note"
    notas = [e for e in repo.list_ticket_events(session, org_id, t.id) if e.tipo == "nota"]
    assert len(notas) == 1
    assert send.call_count <= 1


def test_26i_xor_gate_off_no_legacy_customer_note(db, monkeypatch):
    session, org_id = db
    abo = _abo(session, org_id, dni="30126014", linea="2235126014")
    t, conv = _ticket_with_owner(session, org_id, abo, tid="TK-26I-10")
    _enable_journeys(monkeypatch)
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", False)
    ctx: dict = {}
    with patch("app.estate.repository.add_ticket_event") as add_ev:
        turn = maybe_handle_journey_turn(
            session,
            org_id,
            conv,
            abo,
            "dejar nota: no debe legacy",
            canal="wa",
            ctx=ctx,
        )
    assert turn is not None
    assert turn.action_status == "unavailable"
    assert turn.reason_code == "runtime_gate_off"
    add_ev.assert_not_called()
    assert not any(
        e.tipo == "nota" and e.visible_cliente == "Sí"
        for e in repo.list_ticket_events(session, org_id, t.id)
    )


# --- Self-note ---


def test_26i_self_note_no_push(db, monkeypatch):
    session, org_id = db
    abo = _abo(session, org_id, dni="30126015", linea="2235126015")
    t, conv = _ticket_with_owner(session, org_id, abo, tid="TK-26I-11")
    _device(session, org_id, dni="30126015", token="ExponentPushToken[26i-s]")
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "ticket_customer_note")
    ctx: dict = {}
    with patch("app.services.app_push.enviar_push_expo", side_effect=_ok_send) as send:
        turn = maybe_handle_journey_turn(
            session,
            org_id,
            conv,
            abo,
            "dejar nota: self note path",
            canal="wa",
            ctx=ctx,
        )
    assert turn is not None
    assert turn.action_status == "success"
    # Actor is abonado:* → SELF_NOTE_NO_PUSH
    assert send.call_count == 0
    evs = [e for e in repo.list_ticket_events(session, org_id, t.id) if e.tipo == "nota"]
    assert len(evs) == 1
    assert evs[0].visible_cliente == "Sí"


def test_26i_agent_note_still_pushes_via_emit(db):
    """Regression: agent path unchanged (not N1 self-note)."""
    session, org_id = db
    abo = _abo(session, org_id, dni="30126016", linea="2235126016")
    t, _ = _ticket_with_owner(session, org_id, abo, tid="TK-26I-12")
    _device(session, org_id, dni="30126016", token="ExponentPushToken[26i-ag]")
    with patch("app.services.app_push.enviar_push_expo", side_effect=_ok_send) as send:
        ev = emit_ticket_customer_note(
            session,
            org_id,
            t.id,
            "Nota de agente",
            actor="agente@coop",
            agent_authorized=True,
        )
        assert ev is not None
        maybe_deliver_ticket_event_push(session, ev)
    assert send.call_count == 1
