"""Eko 2.3G-B — ticket proactive detector + push (sin Expo real)."""

from __future__ import annotations

from unittest.mock import patch

from app.estate import repository as repo
from app.estate.models import Abonado, ConversacionCanal, PortalDevice, TicketEvent
from app.services import app_push
from app.services.eko_proactive_contract import SUPPORTED_PROACTIVE_EVENTS
from app.services.eko_proactive_policy import evaluate_proactive_notification
from app.services.eko_ticket_proactive import (
    is_ticket_event_customer_visible,
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


def test_23gb_supported_includes_ticket_not_resolved():
    assert "ticket.created" in SUPPORTED_PROACTIVE_EVENTS
    assert "ticket.updated" in SUPPORTED_PROACTIVE_EVENTS
    assert "ticket.closed" in SUPPORTED_PROACTIVE_EVENTS
    assert "ticket.resolved" not in SUPPORTED_PROACTIVE_EVENTS
    assert "outage.started" in SUPPORTED_PROACTIVE_EVENTS


def test_23gb_gate_and_mapping(db):
    session, org_id = db
    abo = _abo(session, org_id, dni="30100001", linea="2235010001")
    t = _ticket_with_owner(session, org_id, abo, tid="TK-GB-MAP")

    with patch.object(app_push, "enviar_push_expo", side_effect=_ok_send):
        ev_c = repo.add_ticket_event(
            session,
            org_id,
            t.id,
            tipo="creacion",
            titulo="x",
            estado="Abierto",
            visible_cliente="Sí",
        )
    assert is_ticket_event_customer_visible(ev_c)
    assert map_ticket_event_type(ev_c) == "ticket.created"

    ev_u = TicketEvent(
        organizacion_id=org_id,
        ticket_id=t.id,
        tipo="actualizacion",
        estado="En Revisión",
        visible_cliente="Sí",
    )
    assert map_ticket_event_type(ev_u) == "ticket.updated"

    ev_cl = TicketEvent(
        organizacion_id=org_id,
        ticket_id=t.id,
        tipo="actualizacion",
        estado="Cerrado",
        visible_cliente="Sí",
    )
    assert map_ticket_event_type(ev_cl) == "ticket.closed"

    # No hay ticket.resolved: estado Resuelto no es canónico de cierre.
    assert map_ticket_event_type(
        TicketEvent(tipo="resuelto", estado="Resuelto", visible_cliente="Sí")
    ) is None


def test_23gb_internal_and_invisible_no_push(db):
    session, org_id = db
    abo = _abo(session, org_id, dni="30100002", linea="2235010002")
    _device(session, org_id, dni="30100002", token="ExponentPushToken[gb2]")
    t = _ticket_with_owner(session, org_id, abo, tid="TK-GB-INT")

    with patch.object(app_push, "enviar_push_expo", side_effect=_ok_send) as send:
        before = send.call_count
        for tipo, visible in (
            ("nota_interna", "No"),
            ("reasignacion", "Sí"),
            ("paso_operativo", "Sí"),
            ("csat_bajo", "Sí"),
            ("kb_propuesta", "No"),
            ("nota", "No"),
        ):
            repo.add_ticket_event(
                session,
                org_id,
                t.id,
                tipo=tipo,
                titulo="interno",
                detalle="secreto",
                estado="Abierto",
                visible_cliente=visible,
            )
    assert send.call_count == before


def test_23gb_created_updated_closed_payload_and_dedup(db):
    session, org_id = db
    abo = _abo(session, org_id, dni="30100003", linea="2235010003")
    _device(session, org_id, dni="30100003", token="ExponentPushToken[gb3a]")
    _device(session, org_id, dni="30100003", token="ExponentPushToken[gb3b]")
    t = _ticket_with_owner(session, org_id, abo, tid="TK-GB-OK")

    payloads = []

    def _capture(tokens, *, title, body, data=None):
        payloads.append(
            {"tokens": list(tokens), "data": dict(data or {}), "title": title, "body": body}
        )
        return _ok_send(tokens, title=title, body=body, data=data)

    with patch.object(app_push, "enviar_push_expo", side_effect=_capture) as send:
        repo.add_ticket_event(
            session,
            org_id,
            t.id,
            tipo="creacion",
            titulo="alta",
            estado="Abierto",
            visible_cliente="Sí",
        )
        ev_u = repo.add_ticket_event(
            session,
            org_id,
            t.id,
            tipo="actualizacion",
            titulo="upd",
            detalle="interno no va al payload",
            estado="En Revisión",
            visible_cliente="Sí",
        )
        r_dup = maybe_deliver_ticket_event_push(session, ev_u)
        repo.add_ticket_event(
            session,
            org_id,
            t.id,
            tipo="actualizacion",
            titulo="cierre",
            estado="Cerrado",
            visible_cliente="Sí",
        )

    assert r_dup.get("skipped") == "already_claimed"
    ticket_payloads = [p for p in payloads if (p["data"] or {}).get("tipo") == "ticket"]
    assert len(ticket_payloads) == 3
    for p in ticket_payloads:
        d = p["data"]
        assert d["tipo"] == "ticket"
        assert d["ticket_id"] == t.id
        assert d["event"] in ("created", "updated", "closed")
        assert "interno" not in str(d)
        assert "detalle" not in d
        assert len(p["tokens"]) == 2

    events = {p["data"]["event"] for p in ticket_payloads}
    assert events == {"created", "updated", "closed"}
    assert send.call_count == 3


def test_23gb_nota_maps_updated(db):
    session, org_id = db
    abo = _abo(session, org_id, dni="30100004", linea="2235010004")
    _device(session, org_id, dni="30100004", token="ExponentPushToken[gb4]")
    t = _ticket_with_owner(session, org_id, abo, tid="TK-GB-NOTA")

    with patch.object(app_push, "enviar_push_expo", side_effect=_ok_send) as send:
        repo.add_ticket_event(
            session,
            org_id,
            t.id,
            tipo="nota",
            titulo="Nota",
            detalle="visible nota",
            estado="Abierto",
            visible_cliente="Sí",
        )
    ticket_calls = [
        c
        for c in send.call_args_list
        if (c.kwargs.get("data") or {}).get("tipo") == "ticket"
        and (c.kwargs.get("data") or {}).get("event") == "updated"
    ]
    assert ticket_calls
    assert "visible nota" not in str(ticket_calls[-1].kwargs.get("data"))


def test_23gb_foreign_device_not_targeted(db):
    session, org_id = db
    owner = _abo(session, org_id, dni="30100005", linea="2235010005")
    _abo(session, org_id, dni="30100006", linea="2235010006")
    _device(session, org_id, dni="30100006", token="ExponentPushToken[gb6]")
    _device(session, org_id, dni="30100005", token="ExponentPushToken[gb5]")
    t = _ticket_with_owner(session, org_id, owner, tid="TK-GB-FOR")

    with patch.object(app_push, "enviar_push_expo", side_effect=_ok_send) as send:
        repo.add_ticket_event(
            session,
            org_id,
            t.id,
            tipo="nota",
            titulo="n",
            estado="Abierto",
            visible_cliente="Sí",
        )
    assert send.call_count == 1
    tokens = send.call_args.kwargs.get("tokens") or send.call_args.args[0]
    assert "ExponentPushToken[gb5]" in tokens
    assert "ExponentPushToken[gb6]" not in tokens


def test_23gb_unresolved_ownership_zero_expo(db):
    session, org_id = db
    orphan = add_ticket(session, org_id, id="TK-GB-ORPH", linea="9999999999")
    with patch.object(app_push, "enviar_push_expo", side_effect=_ok_send) as send:
        r = repo.add_ticket_event(
            session,
            org_id,
            orphan.id,
            tipo="nota",
            titulo="n",
            estado="Abierto",
            visible_cliente="Sí",
        )
        pe = ticket_event_to_proactive_event(r)
        assert pe is not None
        out = maybe_deliver_ticket_event_push(session, r)
    assert out.get("skipped") == "OWNERSHIP_UNRESOLVED"
    assert send.call_count == 0


def test_23gb_unsupported_tipo_no_push(db):
    session, org_id = db
    abo = _abo(session, org_id, dni="30100007", linea="2235010007")
    _device(session, org_id, dni="30100007", token="ExponentPushToken[gb7]")
    t = _ticket_with_owner(session, org_id, abo, tid="TK-GB-UNS")

    with patch.object(app_push, "enviar_push_expo", side_effect=_ok_send) as send:
        before = send.call_count
        repo.add_ticket_event(
            session,
            org_id,
            t.id,
            tipo="tipo_desconocido_xyz",
            titulo="x",
            estado="Abierto",
            visible_cliente="Sí",
        )
    assert send.call_count == before


def test_23gb_invalid_token_hygiene_does_not_block_valid(db):
    session, org_id = db
    abo = _abo(session, org_id, dni="30100008", linea="2235010008")
    _device(session, org_id, dni="30100008", token="ExponentPushToken[gb8bad]")
    _device(session, org_id, dni="30100008", token="ExponentPushToken[gb8ok]")
    t = _ticket_with_owner(session, org_id, abo, tid="TK-GB-HYG")

    def _partial(tokens, *, title, body, data=None):
        return {
            "ok": True,
            "sent": 1,
            "error_category": "ok",
            "retryable": False,
            "provider_message_ids": ["m"],
            "invalid_tokens": ["ExponentPushToken[gb8bad]"],
            "invalid_token_fps": ["dead"],
        }

    with (
        patch.object(app_push, "enviar_push_expo", side_effect=_partial),
        patch.object(app_push, "deactivate_invalid_push_tokens") as deact,
    ):
        repo.add_ticket_event(
            session,
            org_id,
            t.id,
            tipo="nota",
            titulo="n",
            estado="Abierto",
            visible_cliente="Sí",
        )
    assert deact.called


def test_23gb_provider_failure_not_business_success(db):
    session, org_id = db
    abo = _abo(session, org_id, dni="30100009", linea="2235010009")
    _device(session, org_id, dni="30100009", token="ExponentPushToken[gb9]")
    t = _ticket_with_owner(session, org_id, abo, tid="TK-GB-FAIL")

    def _fail(tokens, *, title, body, data=None):
        return {
            "ok": False,
            "sent": 0,
            "error_category": "transient",
            "retryable": True,
            "provider_message_ids": [],
            "invalid_tokens": [],
        }

    with patch.object(app_push, "enviar_push_expo", side_effect=_fail):
        ev = repo.add_ticket_event(
            session,
            org_id,
            t.id,
            tipo="nota",
            titulo="n",
            estado="Abierto",
            visible_cliente="Sí",
        )
        r2 = maybe_deliver_ticket_event_push(session, ev)
    assert r2.get("skipped") == "already_claimed"


def test_23gb_outage_regression_still_works(db):
    session, org_id = db
    from app.services.eko_proactive_policy import authorize_outage_push
    from app.services.eko_proactive_push import deliver_proactive_push

    o = repo.create_network_outage(
        session,
        org_id,
        nas_shortname="nas-gb",
        nas_ip="",
        comentario="c",
        mensaje_cliente="Hay una incidencia en tu zona.",
        eta_validada="No",
        created_by="test",
    )
    _abo(session, org_id, dni="30100010")
    _device(session, org_id, dni="30100010", token="ExponentPushToken[gb10]")
    d = authorize_outage_push(
        event_type="outage.started",
        org_id=org_id,
        outage_id=o.id,
        customer_message="Hay una incidencia en tu zona.",
        customer_title="Corte",
    )
    with (
        patch("app.services.outages.abonado_afectado_por_nas", return_value=True),
        patch.object(app_push, "enviar_push_expo", side_effect=_ok_send) as send,
    ):
        r = deliver_proactive_push(session, d, nas_shortname="nas-gb")
    assert r["sent"] == 1
    assert send.call_count == 1
    data = send.call_args.kwargs.get("data") or {}
    assert data.get("tipo") == "incidente"
    assert data.get("outage_id") == o.id


def test_23gb_billing_connectivity_service_still_rejected():
    from app.services.eko_proactive_contract import ProactiveEvent

    for et in (
        "billing.invoice_issued",
        "connectivity.lost",
        "service.activated",
    ):
        ev = ProactiveEvent(
            event_type=et,
            source="x",
            source_event_id="1",
            source_authority="TRUSTED_READ",
            organizacion_id="org",
            customer_message="x",
        )
        d = evaluate_proactive_notification(ev)
        assert d.decision == "NOT_ELIGIBLE"
        assert d.suppression_reason == "SIGNAL_NOT_SUPPORTED"


def test_23gb_payload_builder_no_internal_fields():
    p = app_push._payload_ticket_seguro(ticket_id="TK-1", event="created")
    assert p == {"tipo": "ticket", "ticket_id": "TK-1", "event": "created"}
    p2 = app_push._payload_ticket_seguro(ticket_id="TK-1", event="weird")
    assert p2["event"] == ""
