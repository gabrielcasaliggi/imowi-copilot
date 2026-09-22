"""Eko 2.3E — anti-spam, dedup, token hygiene (outage path only)."""

from __future__ import annotations

from unittest.mock import patch

import httpx

from app.estate import repository as repo
from app.estate.models import Abonado, PortalDevice
from app.services import app_push
from app.services.eko_proactive_contract import ProactiveEvent
from app.services.eko_proactive_policy import (
    authorize_outage_push,
    evaluate_proactive_notification,
)
from app.services.eko_proactive_push import deliver_proactive_push


def _add_abonado(session, org_id: str, *, dni: str, client_number: str = "") -> Abonado:
    abo = Abonado(
        organizacion_id=org_id,
        dni=dni,
        nombre=f"Test {dni}",
        telefono_e164="",
        servicio="internet",
        estado="activo",
        client_number=client_number,
    )
    session.add(abo)
    session.commit()
    session.refresh(abo)
    return abo


def _add_device(session, org_id: str, *, dni: str, token: str, activo: str = "Sí") -> PortalDevice:
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


def _add_outage(session, org_id: str, *, nas: str = "nas-a"):
    return repo.create_network_outage(
        session,
        org_id,
        nas_shortname=nas,
        nas_ip="",
        comentario="test",
        mensaje_cliente="Hay una incidencia en tu zona.",
        eta_validada="No",
        created_by="test",
    )


def _decision(org_id: str, outage_id: str, event_type: str, msg: str = "msg"):
    return authorize_outage_push(
        event_type=event_type,
        org_id=org_id,
        outage_id=outage_id,
        customer_message=msg,
        customer_title="t",
    )


def _ok_send(tokens, *, title, body, data=None):
    return {"ok": True, "sent": len(tokens), "error_category": "ok", "retryable": False}


# --- A. Lifecycle ---


def test_23e_started_once(db):
    session, org_id = db
    o = _add_outage(session, org_id)
    _add_abonado(session, org_id, dni="23100001")
    _add_device(session, org_id, dni="23100001", token="ExponentPushToken[a1]")
    with (
        patch("app.services.outages.abonado_afectado_por_nas", return_value=True),
        patch.object(app_push, "enviar_push_expo", side_effect=_ok_send) as send,
    ):
        r = deliver_proactive_push(
            session, _decision(org_id, o.id, "outage.started"), nas_shortname="nas-a"
        )
    assert r["sent"] == 1
    assert send.call_count == 1


def test_23e_duplicate_started(db):
    session, org_id = db
    o = _add_outage(session, org_id)
    _add_abonado(session, org_id, dni="23100002")
    _add_device(session, org_id, dni="23100002", token="ExponentPushToken[a2]")
    d = _decision(org_id, o.id, "outage.started")
    with (
        patch("app.services.outages.abonado_afectado_por_nas", return_value=True),
        patch.object(app_push, "enviar_push_expo", side_effect=_ok_send) as send,
    ):
        r1 = deliver_proactive_push(session, d, nas_shortname="nas-a")
        r2 = deliver_proactive_push(session, d, nas_shortname="nas-a")
    assert r1["sent"] == 1
    assert r2["skipped"] == "already_declared"
    assert r2["sent"] == 0
    assert send.call_count == 1


def test_23e_material_update_1_and_duplicate(db):
    session, org_id = db
    o = _add_outage(session, org_id)
    _add_abonado(session, org_id, dni="23100003")
    _add_device(session, org_id, dni="23100003", token="ExponentPushToken[a3]")
    msg = "Actualización material uno"
    d = _decision(org_id, o.id, "outage.material_update", msg)
    with (
        patch("app.services.outages.abonado_afectado_por_nas", return_value=True),
        patch.object(app_push, "enviar_push_expo", side_effect=_ok_send) as send,
    ):
        r1 = deliver_proactive_push(session, d, nas_shortname="nas-a")
        r2 = deliver_proactive_push(session, d, nas_shortname="nas-a")
    assert r1["sent"] == 1
    assert r2["skipped"] == "already_material_fp"
    assert r2["sent"] == 0
    assert send.call_count == 1


def test_23e_legitimate_material_update_2(db):
    session, org_id = db
    o = _add_outage(session, org_id)
    _add_abonado(session, org_id, dni="23100004")
    _add_device(session, org_id, dni="23100004", token="ExponentPushToken[a4]")
    d1 = _decision(org_id, o.id, "outage.material_update", "Update A")
    d2 = _decision(org_id, o.id, "outage.material_update", "Update B distinto")
    with (
        patch("app.services.outages.abonado_afectado_por_nas", return_value=True),
        patch.object(app_push, "enviar_push_expo", side_effect=_ok_send) as send,
    ):
        r1 = deliver_proactive_push(session, d1, nas_shortname="nas-a")
        r2 = deliver_proactive_push(session, d2, nas_shortname="nas-a")
        r3 = deliver_proactive_push(session, d2, nas_shortname="nas-a")
    assert r1["sent"] == 1
    assert r2["sent"] == 1
    assert r3["skipped"] == "already_material_fp"
    assert send.call_count == 2


def test_23e_resolved_once_and_duplicate(db):
    session, org_id = db
    o = _add_outage(session, org_id)
    _add_abonado(session, org_id, dni="23100005")
    _add_device(session, org_id, dni="23100005", token="ExponentPushToken[a5]")
    d = _decision(org_id, o.id, "outage.resolved", "")
    with (
        patch("app.services.outages.abonado_afectado_por_nas", return_value=True),
        patch.object(app_push, "enviar_push_expo", side_effect=_ok_send) as send,
    ):
        r1 = deliver_proactive_push(session, d, nas_shortname="nas-a")
        r2 = deliver_proactive_push(session, d, nas_shortname="nas-a")
    assert r1["sent"] == 1
    assert r2["skipped"] == "already_resolved"
    assert send.call_count == 1


def test_23e_new_outage_independent(db):
    session, org_id = db
    o1 = _add_outage(session, org_id, nas="nas-a")
    o2 = _add_outage(session, org_id, nas="nas-b")
    _add_abonado(session, org_id, dni="23100006")
    _add_device(session, org_id, dni="23100006", token="ExponentPushToken[a6]")
    with (
        patch("app.services.outages.abonado_afectado_por_nas", return_value=True),
        patch.object(app_push, "enviar_push_expo", side_effect=_ok_send) as send,
    ):
        r1 = deliver_proactive_push(
            session, _decision(org_id, o1.id, "outage.started"), nas_shortname="nas-a"
        )
        r2 = deliver_proactive_push(
            session, _decision(org_id, o2.id, "outage.started"), nas_shortname="nas-b"
        )
    assert r1["sent"] == 1
    assert r2["sent"] == 1
    assert send.call_count == 2


# --- B. Devices ---


def test_23e_no_eligible_devices(db):
    session, org_id = db
    o = _add_outage(session, org_id)
    with patch.object(app_push, "enviar_push_expo", side_effect=_ok_send) as send:
        r = deliver_proactive_push(
            session, _decision(org_id, o.id, "outage.started"), nas_shortname="nas-a"
        )
    assert r["sent"] == 0
    # Puede llamar con lista vacía (short-circuit) o no; no hay devices afectados.
    if send.called:
        assert send.call_args[0][0] == []


def test_23e_multiple_valid_devices(db):
    session, org_id = db
    o = _add_outage(session, org_id)
    _add_abonado(session, org_id, dni="23100007")
    t1, t2 = "ExponentPushToken[m1]", "ExponentPushToken[m2]"
    _add_device(session, org_id, dni="23100007", token=t1)
    _add_device(session, org_id, dni="23100007", token=t2)
    captured = {}

    def _send(tokens, *, title, body, data=None):
        captured["tokens"] = list(tokens)
        return {"ok": True, "sent": len(tokens), "error_category": "ok"}

    with (
        patch("app.services.outages.abonado_afectado_por_nas", return_value=True),
        patch.object(app_push, "enviar_push_expo", side_effect=_send),
    ):
        r = deliver_proactive_push(
            session, _decision(org_id, o.id, "outage.started"), nas_shortname="nas-a"
        )
    assert r["sent"] == 2
    assert set(captured["tokens"]) == {t1, t2}


def test_23e_invalid_device_does_not_suppress_valid(db):
    """DeviceNotRegistered en A no impide ticket ok en B; A se desactiva."""
    session, org_id = db
    o = _add_outage(session, org_id)
    _add_abonado(session, org_id, dni="23100008")
    dead = "ExponentPushToken[dead]"
    live = "ExponentPushToken[live]"
    d_dead = _add_device(session, org_id, dni="23100008", token=dead)
    d_live = _add_device(session, org_id, dni="23100008", token=live)

    def _fake_post(url, json=None, **kwargs):
        # Orden de messages = orden de tokens
        resp = httpx.Response(
            200,
            json={
                "data": [
                    {
                        "status": "error",
                        "details": {"error": "DeviceNotRegistered"},
                    },
                    {"status": "ok", "id": "ticket-live-1"},
                ]
            },
        )
        return resp

    with (
        patch("app.services.outages.abonado_afectado_por_nas", return_value=True),
        patch("httpx.Client") as client_cls,
    ):
        client = client_cls.return_value.__enter__.return_value
        client.post.side_effect = _fake_post
        # Forzar orden de tokens
        with patch.object(
            app_push,
            "listar_tokens_afectados_por_nas",
            return_value=([dead, live], 1),
        ):
            r = app_push.notificar_incidente_app(
                session,
                org_id,
                title="Corte",
                body="msg",
                outage_id=o.id,
                nas_shortname="nas-a",
            )

    assert r["ok"] is True
    assert r["sent"] == 1
    assert r["error_category"] in ("partial", "ok")
    session.refresh(d_dead)
    session.refresh(d_live)
    assert d_dead.activo == "No"
    assert d_live.activo == "Sí"


def test_23e_all_devices_invalid(db):
    session, org_id = db
    o = _add_outage(session, org_id)
    tok = "ExponentPushToken[alldead]"
    row = _add_device(session, org_id, dni="23100009", token=tok)
    _add_abonado(session, org_id, dni="23100009")

    def _fake_post(url, json=None, **kwargs):
        return httpx.Response(
            200,
            json={
                "data": [
                    {"status": "error", "details": {"error": "DeviceNotRegistered"}},
                ]
            },
        )

    with (
        patch("app.services.outages.abonado_afectado_por_nas", return_value=True),
        patch("httpx.Client") as client_cls,
    ):
        client = client_cls.return_value.__enter__.return_value
        client.post.side_effect = _fake_post
        with patch.object(
            app_push,
            "listar_tokens_afectados_por_nas",
            return_value=([tok], 1),
        ):
            r = app_push.notificar_incidente_app(
                session,
                org_id,
                title="Corte",
                body="msg",
                outage_id=o.id,
                nas_shortname="nas-a",
            )
    assert r["ok"] is False
    assert r["sent"] == 0
    assert r["error_category"] == "invalid_token"
    session.refresh(row)
    assert row.activo == "No"


# --- C. Ownership ---


def test_23e_unresolved_ownership(db):
    session, org_id = db
    d = authorize_outage_push(
        event_type="outage.started",
        org_id="",
        outage_id="x",
        customer_message="m",
    )
    assert d.suppression_reason == "OWNERSHIP_UNRESOLVED"
    with patch.object(app_push, "enviar_push_expo") as send:
        r = deliver_proactive_push(session, d)
    assert r["sent"] == 0
    send.assert_not_called()


def test_23e_cross_account_isolation(db):
    """Abonado B no afectado → no recibe tokens aunque tenga device."""
    session, org_id = db
    o = _add_outage(session, org_id)
    _add_abonado(session, org_id, dni="23100010", client_number="A")
    _add_device(session, org_id, dni="23100010", token="ExponentPushToken[accA]")
    _add_abonado(session, org_id, dni="23100011", client_number="B")
    _add_device(session, org_id, dni="23100011", token="ExponentPushToken[accB]")

    def _match(_db, abo, nas, nas_ip_outage=""):
        return str(getattr(abo, "client_number", "")) == "A"

    captured = {}

    def _send(tokens, *, title, body, data=None):
        captured["tokens"] = list(tokens)
        return {"ok": True, "sent": len(tokens)}

    with (
        patch("app.services.outages.abonado_afectado_por_nas", side_effect=_match),
        patch.object(app_push, "enviar_push_expo", side_effect=_send),
    ):
        r = deliver_proactive_push(
            session, _decision(org_id, o.id, "outage.started"), nas_shortname="nas-a"
        )
    assert r["sent"] == 1
    assert captured["tokens"] == ["ExponentPushToken[accA]"]


# --- D. Provider ---


def test_23e_provider_permanent_http_not_success(db):
    session, org_id = db
    o = _add_outage(session, org_id)
    _add_abonado(session, org_id, dni="23100012")
    _add_device(session, org_id, dni="23100012", token="ExponentPushToken[p1]")

    def _fake_post(url, json=None, **kwargs):
        return httpx.Response(400, text="bad request")

    with (
        patch("app.services.outages.abonado_afectado_por_nas", return_value=True),
        patch("httpx.Client") as client_cls,
    ):
        client = client_cls.return_value.__enter__.return_value
        client.post.side_effect = _fake_post
        r = deliver_proactive_push(
            session, _decision(org_id, o.id, "outage.started"), nas_shortname="nas-a"
        )
    assert r["ok"] is False
    assert r["provider_ok"] is False
    assert r["sent"] == 0
    assert r.get("error_category") == "permanent"


def test_23e_provider_timeout_not_success(db):
    session, org_id = db
    o = _add_outage(session, org_id)
    _add_abonado(session, org_id, dni="23100013")
    _add_device(session, org_id, dni="23100013", token="ExponentPushToken[p2]")

    with (
        patch("app.services.outages.abonado_afectado_por_nas", return_value=True),
        patch("httpx.Client") as client_cls,
    ):
        client = client_cls.return_value.__enter__.return_value
        client.post.side_effect = httpx.TimeoutException("timeout")
        r = deliver_proactive_push(
            session, _decision(org_id, o.id, "outage.started"), nas_shortname="nas-a"
        )
    assert r["ok"] is False
    assert r["sent"] == 0
    assert r.get("error_category") == "timeout"
    assert r.get("retryable") is True


def test_23e_provider_transient_5xx(db):
    session, org_id = db
    o = _add_outage(session, org_id)
    _add_abonado(session, org_id, dni="23100014")
    _add_device(session, org_id, dni="23100014", token="ExponentPushToken[p3]")

    def _fake_post(url, json=None, **kwargs):
        return httpx.Response(503, text="unavailable")

    with (
        patch("app.services.outages.abonado_afectado_por_nas", return_value=True),
        patch("httpx.Client") as client_cls,
    ):
        client = client_cls.return_value.__enter__.return_value
        client.post.side_effect = _fake_post
        r = deliver_proactive_push(
            session, _decision(org_id, o.id, "outage.started"), nas_shortname="nas-a"
        )
    assert r["ok"] is False
    assert r.get("error_category") == "transient"
    assert r.get("retryable") is True


def test_23e_malformed_token_local_not_success(db):
    session, org_id = db
    assert app_push.token_push_valido("not-a-token") is False
    r = app_push.enviar_push_expo(
        ["not-a-token"], title="t", body="b", data={"tipo": "incidente"}
    )
    assert r["ok"] is False
    assert r["error_category"] == "invalid_token"
    assert r["sent"] == 0


# --- E. Concurrency / claims ---


def test_23e_concurrent_declared_claim_only_one(db):
    session, org_id = db
    o = _add_outage(session, org_id)
    assert repo.claim_outage_push_declared(session, o.id) is True
    assert repo.claim_outage_push_declared(session, o.id) is False


def test_23e_concurrent_material_claim_same_fp(db):
    session, org_id = db
    o = _add_outage(session, org_id)
    fp = app_push.material_update_fingerprint("mismo contenido")
    assert repo.claim_outage_push_material(session, o.id, fp) is True
    assert repo.claim_outage_push_material(session, o.id, fp) is False
    fp2 = app_push.material_update_fingerprint("contenido distinto")
    assert repo.claim_outage_push_material(session, o.id, fp2) is True


# --- F. Unsupported domains ---


def test_23e_unsupported_domains(db):
    session, org_id = db
    for et in (
        "billing.invoice_available",
        "connectivity.down",
        "service.changed",
        "ticket.resolved",  # explícitamente no habilitado (sin estado Resuelto)
    ):
        d = evaluate_proactive_notification(
            ProactiveEvent(
                event_type=et,
                source="x",
                source_event_id="1",
                organizacion_id=org_id,
                source_authority="AUTHORITATIVE",
                customer_message="m",
            )
        )
        assert d.suppression_reason == "SIGNAL_NOT_SUPPORTED"
        with patch.object(app_push, "enviar_push_expo") as send:
            r = deliver_proactive_push(session, d)
        assert r["sent"] == 0
        send.assert_not_called()


def test_23e_no_false_delivered_on_unknown_empty_tickets(db):
    session, org_id = db
    o = _add_outage(session, org_id)
    _add_abonado(session, org_id, dni="23100015")
    _add_device(session, org_id, dni="23100015", token="ExponentPushToken[u1]")

    def _fake_post(url, json=None, **kwargs):
        return httpx.Response(200, json={"data": None})

    with (
        patch("app.services.outages.abonado_afectado_por_nas", return_value=True),
        patch("httpx.Client") as client_cls,
    ):
        client = client_cls.return_value.__enter__.return_value
        client.post.side_effect = _fake_post
        r = deliver_proactive_push(
            session, _decision(org_id, o.id, "outage.started"), nas_shortname="nas-a"
        )
    assert r["ok"] is False
    assert r["sent"] == 0
    assert r.get("error_category") == "unknown"


def test_23e_transient_error_does_not_deactivate_token(db):
    session, org_id = db
    tok = "ExponentPushToken[keep]"
    row = _add_device(session, org_id, dni="23100016", token=tok)
    _add_abonado(session, org_id, dni="23100016")
    o = _add_outage(session, org_id)

    def _fake_post(url, json=None, **kwargs):
        return httpx.Response(503, text="down")

    with (
        patch("app.services.outages.abonado_afectado_por_nas", return_value=True),
        patch("httpx.Client") as client_cls,
    ):
        client = client_cls.return_value.__enter__.return_value
        client.post.side_effect = _fake_post
        with patch.object(
            app_push,
            "listar_tokens_afectados_por_nas",
            return_value=([tok], 1),
        ):
            app_push.notificar_incidente_app(
                session,
                org_id,
                title="Corte",
                body="msg",
                outage_id=o.id,
                nas_shortname="nas-a",
            )
    session.refresh(row)
    assert row.activo == "Sí"
