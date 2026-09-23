"""Eko 2.6E — ticket_customer_note + visibility hardening."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.estate import repository as repo
from app.estate.models import Abonado, ConversacionCanal, PortalDevice
from app.services.eko_action_runtime import (
    ActionRequest,
    TrustedContext,
    execute_action,
    is_registered,
    parse_llm_action_proposal,
    sanitize_parameters,
)
from app.services.eko_proactive_contract import SUPPORTED_PROACTIVE_EVENTS
from app.services.eko_ticket_proactive import (
    emit_ticket_customer_note,
    is_portal_customer_event,
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
    session.refresh(row)
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
    return t


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
        conversation_id="conv-1",
        organization_id=org_id,
        abonado_id=abo.id,
        abonado=abo,
        conv=MagicMock(id="conv-1", ticket_id=ticket_id, estado="bot"),
        ctx={},
        db=session,
        canal="app",
        confirmation_received=False,
        confirmation_rejected=False,
        decision_name="test",
    )


def test_26e_registry_has_ticket_customer_note():
    assert is_registered("ticket_customer_note")
    assert is_registered("update_ticket")


def test_26e_valid_note_creates_event(db):
    session, org_id = db
    abo = _abo(session, org_id, dni="30111001", linea="2235111001")
    t = _ticket_with_owner(session, org_id, abo, tid="TK-26E-1")
    ev = emit_ticket_customer_note(
        session,
        org_id,
        t.id,
        "Seguimos revisando tu línea.",
        actor="agente@coop",
        agent_authorized=True,
    )
    assert ev is not None
    assert ev.tipo == "nota"
    assert ev.visible_cliente == "Sí"
    assert ev.detalle == "Seguimos revisando tu línea."
    assert map_ticket_event_type(ev) == "ticket.updated"


def test_26e_agent_note_enters_pipeline_push_updated(db):
    session, org_id = db
    abo = _abo(session, org_id, dni="30111002", linea="2235111002")
    _device(session, org_id, dni="30111002", token="ExponentPushToken[26e-a]")
    t = _ticket_with_owner(session, org_id, abo, tid="TK-26E-2")
    with patch("app.services.app_push.enviar_push_expo", side_effect=_ok_send) as send:
        ev = emit_ticket_customer_note(
            session,
            org_id,
            t.id,
            "Hay una novedad en tu reclamo.",
            actor="ops@coop",
            agent_authorized=True,
        )
        assert ev is not None
        assert send.called
        data = send.call_args.kwargs.get("data") or {}
        assert data.get("tipo") == "ticket"
        assert data.get("event") == "updated"
        assert "Hay una novedad" not in str(data)
        assert "Hay una novedad" not in (send.call_args.kwargs.get("body") or "")


def test_26e_self_note_no_push(db):
    session, org_id = db
    abo = _abo(session, org_id, dni="30111003", linea="2235111003")
    _device(session, org_id, dni="30111003", token="ExponentPushToken[26e-b]")
    t = _ticket_with_owner(session, org_id, abo, tid="TK-26E-3")
    with patch("app.services.app_push.enviar_push_expo", side_effect=_ok_send) as send:
        ev = emit_ticket_customer_note(
            session,
            org_id,
            t.id,
            "Agrego un detalle desde el chat.",
            actor=f"abonado:{abo.id}",
            abonado=abo,
        )
        assert ev is not None
        assert ev.visible_cliente == "Sí"
        assert send.call_count == 0


def test_26e_own_ticket_runtime_allow(db):
    session, org_id = db
    abo = _abo(session, org_id, dni="30111004", linea="2235111004")
    t = _ticket_with_owner(session, org_id, abo, tid="TK-26E-4")
    trusted = _trusted(session, org_id, abo, ticket_id=t.id)
    with patch("app.services.app_push.enviar_push_expo", side_effect=_ok_send):
        r = execute_action(
            ActionRequest(
                action="ticket_customer_note",
                parameters={"ticket_id": t.id, "mensaje": "Nota propia"},
                source="decision",
            ),
            trusted,
        )
    assert r.status == "success"
    assert r.data.get("ticket_event_id")


def test_26e_foreign_ticket_denied(db):
    session, org_id = db
    owner = _abo(session, org_id, dni="30111005", linea="2235111005")
    other = _abo(session, org_id, dni="30111006", linea="2235111006")
    t = _ticket_with_owner(session, org_id, owner, tid="TK-26E-5")
    trusted = _trusted(session, org_id, other, ticket_id=t.id)
    r = execute_action(
        ActionRequest(
            action="ticket_customer_note",
            parameters={"ticket_id": t.id, "mensaje": "Hack"},
            source="decision",
        ),
        trusted,
    )
    assert r.status == "denied"
    assert r.reason_code == "foreign_ticket"
    events = repo.list_ticket_events(session, org_id, t.id)
    assert not any(e.tipo == "nota" and e.detalle == "Hack" for e in events)


def test_26e_missing_abonado_denied(db):
    session, org_id = db
    abo = _abo(session, org_id, dni="30111007", linea="2235111007")
    t = _ticket_with_owner(session, org_id, abo, tid="TK-26E-6")
    trusted = _trusted(session, org_id, abo, ticket_id=t.id)
    trusted.abonado = None
    r = execute_action(
        ActionRequest(
            action="ticket_customer_note",
            parameters={"ticket_id": t.id, "mensaje": "x"},
            source="decision",
        ),
        trusted,
    )
    assert r.status == "denied"


def test_26e_update_ticket_evidence_only_no_event_no_push(db):
    session, org_id = db
    abo = _abo(session, org_id, dni="30111008", linea="2235111008")
    _device(session, org_id, dni="30111008", token="ExponentPushToken[26e-c]")
    t = _ticket_with_owner(session, org_id, abo, tid="TK-26E-7")
    before = len(repo.list_ticket_events(session, org_id, t.id))
    trusted = _trusted(session, org_id, abo, ticket_id=t.id)
    with patch("app.services.app_push.enviar_push_expo", side_effect=_ok_send) as send:
        r = execute_action(
            ActionRequest(
                action="update_ticket",
                parameters={"ticket_id": t.id, "nota": "evidencia técnica ONU"},
                source="decision",
            ),
            trusted,
        )
    assert r.status == "success"
    session.refresh(t)
    assert "evidencia técnica ONU" in (t.evidencia or "")
    after = repo.list_ticket_events(session, org_id, t.id)
    assert len(after) == before
    assert send.call_count == 0


def test_26e_admin_update_visible_no(db):
    session, org_id = db
    abo = _abo(session, org_id, dni="30111009", linea="2235111009")
    t = _ticket_with_owner(session, org_id, abo, tid="TK-26E-8")
    with patch("app.services.app_push.enviar_push_expo", side_effect=_ok_send) as send:
        repo.update_ticket(
            session, org_id, t.id, nivel="N2", actor="ops@coop"
        )
    events = [e for e in repo.list_ticket_events(session, org_id, t.id) if e.tipo == "actualizacion"]
    assert events
    assert events[-1].visible_cliente == "No"
    assert not is_portal_customer_event(events[-1])
    assert send.call_count == 0


def test_26e_reassignment_visible_no(db):
    session, org_id = db
    abo = _abo(session, org_id, dni="30111010", linea="2235111010")
    t = _ticket_with_owner(session, org_id, abo, tid="TK-26E-9")
    with patch("app.services.app_push.enviar_push_expo", side_effect=_ok_send) as send:
        repo.update_ticket(
            session, org_id, t.id, asignado_a="agente@coop", actor="ops@coop"
        )
    events = [e for e in repo.list_ticket_events(session, org_id, t.id) if e.tipo == "reasignacion"]
    assert events
    assert events[-1].visible_cliente == "No"
    assert not is_portal_customer_event(events[-1])
    assert send.call_count == 0


def test_26e_closed_remains_customer_visible(db):
    session, org_id = db
    abo = _abo(session, org_id, dni="30111011", linea="2235111011")
    _device(session, org_id, dni="30111011", token="ExponentPushToken[26e-d]")
    t = _ticket_with_owner(session, org_id, abo, tid="TK-26E-10")
    with patch("app.services.app_push.enviar_push_expo", side_effect=_ok_send) as send:
        repo.update_ticket(
            session, org_id, t.id, estado="Cerrado", actor="ops@coop"
        )
    events = [
        e
        for e in repo.list_ticket_events(session, org_id, t.id)
        if e.tipo == "actualizacion" and e.estado == "Cerrado"
    ]
    assert events
    assert events[-1].visible_cliente == "Sí"
    assert map_ticket_event_type(events[-1]) == "ticket.closed"
    assert is_portal_customer_event(events[-1])
    assert send.called
    assert send.call_args.kwargs["data"]["event"] == "closed"


def test_26e_existing_semantics_supported():
    assert "ticket.created" in SUPPORTED_PROACTIVE_EVENTS
    assert "ticket.updated" in SUPPORTED_PROACTIVE_EVENTS
    assert "ticket.closed" in SUPPORTED_PROACTIVE_EVENTS
    assert "ticket.sla_breached" in SUPPORTED_PROACTIVE_EVENTS


def test_26e_portal_projection_filters(db):
    session, org_id = db
    abo = _abo(session, org_id, dni="30111012", linea="2235111012")
    t = _ticket_with_owner(session, org_id, abo, tid="TK-26E-11")
    note = emit_ticket_customer_note(
        session, org_id, t.id, "Visible al cliente", actor="ops@coop", agent_authorized=True
    )
    admin = repo.add_ticket_event(
        session,
        org_id,
        t.id,
        tipo="actualizacion",
        titulo="admin",
        detalle="nivel=N2",
        estado="Abierto",
        actor="ops",
        visible_cliente="No",
    )
    reas = repo.add_ticket_event(
        session,
        org_id,
        t.id,
        tipo="reasignacion",
        titulo="re",
        detalle="x",
        estado="Abierto",
        actor="ops",
        visible_cliente="No",
    )
    assert is_portal_customer_event(note)
    assert not is_portal_customer_event(admin)
    assert not is_portal_customer_event(reas)


def test_26e_casi_llm_cannot_set_visibility():
    cleaned = sanitize_parameters(
        {"mensaje": "hola", "visible_cliente": "Sí", "notify": True, "ticket_id": "T1"}
    )
    assert "visible_cliente" not in cleaned
    assert "notify" not in cleaned
    assert cleaned.get("mensaje") == "hola"
    # Proposal may parse action but executor still requires Runtime+ownership
    prop = parse_llm_action_proposal(
        {
            "action": "ticket_customer_note",
            "parameters": {"ticket_id": "T1", "mensaje": "x", "visible_cliente": "Sí"},
            "abonado_id": "fake",
        }
    )
    assert prop is not None
    assert prop.source == "llm_proposal"
    assert "visible_cliente" not in prop.parameters
    assert "abonado_id" not in prop.parameters


def test_26e_idempotent_same_message(db):
    session, org_id = db
    abo = _abo(session, org_id, dni="30111013", linea="2235111013")
    t = _ticket_with_owner(session, org_id, abo, tid="TK-26E-12")
    with patch("app.services.app_push.enviar_push_expo", side_effect=_ok_send) as send:
        e1 = emit_ticket_customer_note(
            session, org_id, t.id, "Mismo texto", actor="ops@coop", agent_authorized=True
        )
        e2 = emit_ticket_customer_note(
            session, org_id, t.id, "Mismo texto", actor="ops@coop", agent_authorized=True
        )
    assert e1 is not None and e2 is not None
    assert e1.id == e2.id
    assert send.call_count == 1


def test_26e_dedup_claim_no_second_push(db):
    session, org_id = db
    abo = _abo(session, org_id, dni="30111014", linea="2235111014")
    _device(session, org_id, dni="30111014", token="ExponentPushToken[26e-e]")
    t = _ticket_with_owner(session, org_id, abo, tid="TK-26E-13")
    with patch("app.services.app_push.enviar_push_expo", side_effect=_ok_send) as send:
        ev = emit_ticket_customer_note(
            session, org_id, t.id, "Una sola vez", actor="ops@coop", agent_authorized=True
        )
        assert ev is not None
        maybe_deliver_ticket_event_push(session, ev)
    assert send.call_count == 1


# --- 2.6G hardenings ---


def test_26g_default_actions_includes_note_not_update_ticket():
    from app.config import ACTION_RUNTIME_ACTIONS

    assert "ticket_customer_note" in ACTION_RUNTIME_ACTIONS
    assert "update_ticket" not in ACTION_RUNTIME_ACTIONS
    # 2.6K: create_ticket joins default ACTIONS (still gated by ENABLED)
    assert "create_ticket" in ACTION_RUNTIME_ACTIONS
    assert "escalate_human" not in ACTION_RUNTIME_ACTIONS
    assert "close_conversation" not in ACTION_RUNTIME_ACTIONS


def test_26g_runtime_covers_note_when_enabled(monkeypatch):
    from app.config import ACTION_RUNTIME_ACTIONS
    from app.services import eko_action_bridge as bridge

    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", True)
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ACTIONS", ACTION_RUNTIME_ACTIONS)
    assert bridge.action_runtime_covers("ticket_customer_note") is True
    assert bridge.action_runtime_covers("create_ticket") is True
    assert bridge.action_runtime_covers("update_ticket") is False


def test_26g_emit_denies_without_owner_or_agent(db):
    session, org_id = db
    abo = _abo(session, org_id, dni="30111020", linea="2235111020")
    t = _ticket_with_owner(session, org_id, abo, tid="TK-26G-1")
    ev = emit_ticket_customer_note(
        session, org_id, t.id, "sin autoridad", actor="ops@coop"
    )
    assert ev is None


def test_26g_emit_denies_foreign_abonado(db):
    session, org_id = db
    owner = _abo(session, org_id, dni="30111021", linea="2235111021")
    other = _abo(session, org_id, dni="30111022", linea="2235111022")
    t = _ticket_with_owner(session, org_id, owner, tid="TK-26G-2")
    with patch("app.services.app_push.enviar_push_expo", side_effect=_ok_send) as send:
        ev = emit_ticket_customer_note(
            session,
            org_id,
            t.id,
            "ajeno",
            actor=f"abonado:{other.id}",
            abonado=other,
        )
    assert ev is None
    assert send.call_count == 0
    assert not any(
        e.tipo == "nota" and e.detalle == "ajeno"
        for e in repo.list_ticket_events(session, org_id, t.id)
    )


def test_26g_add_ticket_event_default_not_visible(db):
    session, org_id = db
    abo = _abo(session, org_id, dni="30111023", linea="2235111023")
    t = _ticket_with_owner(session, org_id, abo, tid="TK-26G-3")
    ev = repo.add_ticket_event(
        session,
        org_id,
        t.id,
        tipo="paso_operativo",
        titulo="x",
        detalle="interno",
        actor="ops",
    )
    assert ev.visible_cliente == "No"
