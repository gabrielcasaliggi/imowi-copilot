"""Eko 2.6A — Customer ticket SLA breach proactive push."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from app.estate import repository as repo
from app.estate.models import Abonado, ConversacionCanal, PortalDevice, TicketEvent
from app.estate.sla_engine import apply_sla_to_ticket
from app.services import app_push
from app.services.eko_proactive_contract import (
    SUPPORTED_PROACTIVE_EVENTS,
    TICKET_EVENT_TO_LEGACY_PUSH,
    ProactiveEvent,
)
from app.services.eko_proactive_policy import evaluate_proactive_notification
from app.services.eko_ticket_proactive import (
    emit_customer_sla_breach_event,
    map_ticket_event_type,
    maybe_deliver_ticket_event_push,
    ticket_event_to_proactive_event,
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


def _device(session, org_id: str, *, dni: str, token: str, activo: str = "Sí") -> PortalDevice:
    row = PortalDevice(
        organizacion_id=org_id,
        dni_normalized=dni,
        expo_push_token=token,
        platform="android",
        activo=activo,
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


def test_26a_supported_includes_sla_breached():
    assert "ticket.sla_breached" in SUPPORTED_PROACTIVE_EVENTS
    assert TICKET_EVENT_TO_LEGACY_PUSH["ticket.sla_breached"] == "sla_breached"
    assert "ticket.created" in SUPPORTED_PROACTIVE_EVENTS
    assert "ticket.updated" in SUPPORTED_PROACTIVE_EVENTS
    assert "ticket.closed" in SUPPORTED_PROACTIVE_EVENTS


def test_26a_map_sla_breach_tipo():
    ev = TicketEvent(
        id="e1",
        organizacion_id="o",
        ticket_id="t",
        tipo="sla_breach",
        titulo="x",
        visible_cliente="Sí",
        estado="Abierto",
    )
    assert map_ticket_event_type(ev) == "ticket.sla_breached"


def test_26a_policy_allow_valid_sla_event():
    pe = ProactiveEvent(
        event_type="ticket.sla_breached",
        source="estate.ticket_events",
        source_event_id="ev-1",
        source_authority="AUTHORITATIVE",
        ticket_id="TK-1",
        organizacion_id="org",
        customer_message="msg",
        customer_title="t",
        channel="app_push",
    )
    d = evaluate_proactive_notification(pe)
    assert d.decision == "ALLOW"


def test_26a_policy_invalid_missing_message():
    pe = ProactiveEvent(
        event_type="ticket.sla_breached",
        source="estate.ticket_events",
        source_event_id="ev-1",
        source_authority="AUTHORITATIVE",
        ticket_id="TK-1",
        organizacion_id="org",
        customer_message="",
        channel="app_push",
    )
    d = evaluate_proactive_notification(pe)
    assert d.decision == "INVALID"


def test_26a_closed_event_not_eligible():
    ev = TicketEvent(
        id="e-closed",
        organizacion_id="o",
        ticket_id="t1",
        tipo="sla_breach",
        titulo="x",
        visible_cliente="Sí",
        estado="Cerrado",
    )
    assert ticket_event_to_proactive_event(ev) is None


def test_26a_internal_tipo_not_mapped_as_sla():
    ev = TicketEvent(
        id="e-int",
        organizacion_id="o",
        ticket_id="t",
        tipo="nota_interna",
        titulo="x",
        visible_cliente="Sí",
        estado="Abierto",
    )
    assert map_ticket_event_type(ev) is None


def test_26a_valid_breach_sends_push(db):
    session, org_id = db
    abo = _abo(session, org_id, dni="30111111", linea="2235111001")
    _device(session, org_id, dni="30111111", token="ExponentPushToken[sla-ok]")
    t = _ticket_with_owner(session, org_id, abo, tid="TK-SLA-OK")
    t.created_at = datetime.now(UTC) - timedelta(hours=50)
    t.sla_due_at = datetime.now(UTC) - timedelta(hours=1)
    session.commit()

    with (
        patch("app.services.sla_notify.send_email"),
        patch("app.services.app_push.enviar_push_expo", side_effect=_ok_send) as send,
    ):
        repo.refresh_tickets_sla(session, [t])
        session.refresh(t)

    assert t.sla_breached_at is not None
    ev = session.query(TicketEvent).filter_by(ticket_id=t.id, tipo="sla_breach").one()
    assert ev.visible_cliente == "Sí"
    assert send.called
    data = send.call_args.kwargs.get("data") or {}
    assert data.get("tipo") == "ticket"
    assert data.get("ticket_id") == "TK-SLA-OK"
    assert data.get("event") == "sla_breached"


def test_26a_no_owner_zero_push(db):
    session, org_id = db
    t = add_ticket(session, org_id, id="TK-SLA-NOOWN", linea="2235999999", estado="Abierto")
    t.created_at = datetime.now(UTC) - timedelta(hours=50)
    t.sla_due_at = datetime.now(UTC) - timedelta(hours=1)
    session.commit()

    with (
        patch("app.services.sla_notify.send_email"),
        patch("app.services.app_push.enviar_push_expo") as send,
    ):
        repo.refresh_tickets_sla(session, [t])

    assert session.query(TicketEvent).filter_by(ticket_id=t.id, tipo="sla_breach").count() == 1
    send.assert_not_called()


def test_26a_duplicate_suppresses_second_push(db):
    session, org_id = db
    abo = _abo(session, org_id, dni="30222222", linea="2235222002")
    _device(session, org_id, dni="30222222", token="ExponentPushToken[sla-dup]")
    t = _ticket_with_owner(session, org_id, abo, tid="TK-SLA-DUP")
    t.created_at = datetime.now(UTC) - timedelta(hours=50)
    t.sla_due_at = datetime.now(UTC) - timedelta(hours=1)
    session.commit()

    with (
        patch("app.services.sla_notify.send_email"),
        patch("app.services.app_push.enviar_push_expo", side_effect=_ok_send) as send,
    ):
        repo.refresh_tickets_sla(session, [t])
        n1 = send.call_count
        repo.refresh_tickets_sla(session, [t])
        emit_customer_sla_breach_event(session, t)

    assert n1 == 1
    assert send.call_count == 1
    assert session.query(TicketEvent).filter_by(ticket_id=t.id, tipo="sla_breach").count() == 1


def test_26a_claim_blocks_reprocess(db):
    session, org_id = db
    abo = _abo(session, org_id, dni="30333333", linea="2235333003")
    _device(session, org_id, dni="30333333", token="ExponentPushToken[sla-claim]")
    t = _ticket_with_owner(session, org_id, abo, tid="TK-SLA-CLM")
    t.sla_breached_at = datetime.now(UTC) - timedelta(hours=1)
    session.commit()

    with patch("app.services.app_push.enviar_push_expo", side_effect=_ok_send) as send:
        ev = emit_customer_sla_breach_event(session, t)
        assert ev is not None
        r2 = maybe_deliver_ticket_event_push(session, ev)

    assert send.call_count == 1
    assert r2.get("skipped") == "already_claimed" or r2.get("sent") == 0


def test_26a_multi_device_all_attempted(db):
    session, org_id = db
    abo = _abo(session, org_id, dni="30444444", linea="2235444004")
    _device(session, org_id, dni="30444444", token="ExponentPushToken[sla-a]")
    _device(session, org_id, dni="30444444", token="ExponentPushToken[sla-b]")
    t = _ticket_with_owner(session, org_id, abo, tid="TK-SLA-MULTI")
    t.created_at = datetime.now(UTC) - timedelta(hours=50)
    t.sla_due_at = datetime.now(UTC) - timedelta(hours=1)
    session.commit()

    with (
        patch("app.services.sla_notify.send_email"),
        patch("app.services.app_push.enviar_push_expo", side_effect=_ok_send) as send,
    ):
        repo.refresh_tickets_sla(session, [t])

    tokens = send.call_args.args[0]
    assert len(tokens) == 2


def test_26a_payload_contract():
    p = app_push._payload_ticket_seguro(ticket_id="T1", event="sla_breached")
    assert p == {"tipo": "ticket", "ticket_id": "T1", "event": "sla_breached"}
    assert app_push._payload_ticket_seguro(ticket_id="T1", event="created")["event"] == "created"


def test_26a_created_updated_closed_unchanged():
    assert map_ticket_event_type(
        TicketEvent(tipo="creacion", estado="Abierto", visible_cliente="Sí")
    ) == "ticket.created"
    assert map_ticket_event_type(
        TicketEvent(tipo="actualizacion", estado="Abierto", visible_cliente="Sí")
    ) == "ticket.updated"
    assert map_ticket_event_type(
        TicketEvent(tipo="actualizacion", estado="Cerrado", visible_cliente="Sí")
    ) == "ticket.closed"


def test_26a_apply_sla_sets_breached_at_once():
    """Authority: NULL → due deadline; no second rewrite."""
    from app.estate.models import Ticket

    t = Ticket(
        id="x",
        organizacion_id="o",
        estado="Abierto",
        nivel="N1",
        created_at=datetime.now(UTC) - timedelta(hours=100),
    )
    apply_sla_to_ticket(t, now=datetime.now(UTC))
    first = t.sla_breached_at
    assert first is not None
    apply_sla_to_ticket(t, now=datetime.now(UTC) + timedelta(hours=5))
    assert t.sla_breached_at == first
