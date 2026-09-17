"""E′2 — dedup declared + push resolved."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.estate import repository as repo
from app.estate.models import Abonado, PortalDevice
from app.services import app_push


def _add_abonado(session, org_id: str, *, dni: str) -> Abonado:
    abo = Abonado(
        organizacion_id=org_id,
        dni=dni,
        nombre=f"Test {dni}",
        telefono_e164="",
        servicio="internet",
        estado="activo",
    )
    session.add(abo)
    session.commit()
    session.refresh(abo)
    return abo


def _add_device(session, org_id: str, *, dni: str, token: str) -> PortalDevice:
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


def _add_outage(session, org_id: str, *, nas: str = "nas-a", nas_ip: str = ""):
    return repo.create_network_outage(
        session,
        org_id,
        nas_shortname=nas,
        nas_ip=nas_ip,
        comentario="test",
        mensaje_cliente="Hay una incidencia en tu zona.",
        eta_validada="No",
        created_by="test",
    )


def test_declared_primer_envio(db):
    session, org_id = db
    o = _add_outage(session, org_id, nas="nas-a")
    _add_abonado(session, org_id, dni="11100001")
    _add_device(
        session, org_id, dni="11100001", token="ExponentPushToken[d1]"
    )
    captured = {}

    def _send(tokens, *, title, body, data=None):
        captured["data"] = dict(data or {})
        captured["tokens"] = list(tokens)
        return {"ok": True, "sent": len(tokens)}

    with (
        patch(
            "app.services.outages.abonado_afectado_por_nas",
            return_value=True,
        ),
        patch.object(app_push, "enviar_push_expo", side_effect=_send),
    ):
        r1 = app_push.notificar_incidente_app(
            session,
            org_id,
            title="Corte en la red",
            body="msg",
            outage_id=o.id,
            nas_shortname="nas-a",
        )

    assert r1.get("skipped") is None
    assert r1["sent"] == 1
    assert captured["data"]["event"] == "declared"
    assert captured["data"]["tipo"] == "incidente"
    assert captured["data"]["outage_id"] == o.id
    assert "nas" not in captured["data"]
    session.refresh(o)
    assert o.push_declared_at is not None


def test_declared_segundo_intento_cero(db):
    session, org_id = db
    o = _add_outage(session, org_id, nas="nas-a")
    _add_abonado(session, org_id, dni="11100002")
    _add_device(
        session, org_id, dni="11100002", token="ExponentPushToken[d2]"
    )

    with (
        patch(
            "app.services.outages.abonado_afectado_por_nas",
            return_value=True,
        ),
        patch.object(
            app_push,
            "enviar_push_expo",
            return_value={"ok": True, "sent": 1},
        ) as send,
    ):
        r1 = app_push.notificar_incidente_app(
            session,
            org_id,
            title="Corte",
            body="msg",
            outage_id=o.id,
            nas_shortname="nas-a",
        )
        r2 = app_push.notificar_incidente_app(
            session,
            org_id,
            title="Corte",
            body="msg",
            outage_id=o.id,
            nas_shortname="nas-a",
        )

    assert r1["sent"] == 1
    assert r2["sent"] == 0
    assert r2.get("skipped") == "already_declared"
    assert send.call_count == 1


def test_resolved_primer_envio(db):
    session, org_id = db
    o = _add_outage(session, org_id, nas="nas-a")
    o = repo.resolve_network_outage(session, o)
    _add_abonado(session, org_id, dni="11100003")
    _add_device(
        session, org_id, dni="11100003", token="ExponentPushToken[d3]"
    )
    captured = {}

    def _send(tokens, *, title, body, data=None):
        captured["data"] = dict(data or {})
        captured["title"] = title
        return {"ok": True, "sent": len(tokens)}

    with (
        patch(
            "app.services.outages.abonado_afectado_por_nas",
            return_value=True,
        ),
        patch.object(app_push, "enviar_push_expo", side_effect=_send),
    ):
        r = app_push.notificar_incidente_resuelto_app(
            session,
            org_id,
            outage_id=o.id,
            nas_shortname="nas-a",
        )

    assert r["sent"] == 1
    assert captured["data"]["event"] == "resolved"
    assert captured["data"]["tipo"] == "incidente"
    assert captured["data"]["outage_id"] == o.id
    assert "nas" not in captured["data"]
    assert "comentario" not in captured["data"]
    assert captured["title"] == app_push.TITLE_RESOLVED
    session.refresh(o)
    assert o.push_resolved_at is not None


def test_resolved_repetido_cero(db):
    session, org_id = db
    o = _add_outage(session, org_id, nas="nas-a")
    o = repo.resolve_network_outage(session, o)
    _add_abonado(session, org_id, dni="11100004")
    _add_device(
        session, org_id, dni="11100004", token="ExponentPushToken[d4]"
    )

    with (
        patch(
            "app.services.outages.abonado_afectado_por_nas",
            return_value=True,
        ),
        patch.object(
            app_push,
            "enviar_push_expo",
            return_value={"ok": True, "sent": 1},
        ) as send,
    ):
        r1 = app_push.notificar_incidente_resuelto_app(
            session, org_id, outage_id=o.id, nas_shortname="nas-a"
        )
        r2 = app_push.notificar_incidente_resuelto_app(
            session, org_id, outage_id=o.id, nas_shortname="nas-a"
        )

    assert r1["sent"] == 1
    assert r2["sent"] == 0
    assert r2.get("skipped") == "already_resolved"
    assert send.call_count == 1


def test_resolved_sin_afectados(db):
    session, org_id = db
    o = _add_outage(session, org_id, nas="nas-a")
    o = repo.resolve_network_outage(session, o)
    _add_abonado(session, org_id, dni="11100005")
    _add_device(
        session, org_id, dni="11100005", token="ExponentPushToken[d5]"
    )

    with (
        patch(
            "app.services.outages.abonado_afectado_por_nas",
            return_value=False,
        ),
        patch.object(
            app_push,
            "enviar_push_expo",
            return_value={"ok": True, "sent": 0},
        ) as send,
    ):
        r = app_push.notificar_incidente_resuelto_app(
            session, org_id, outage_id=o.id, nas_shortname="nas-a"
        )

    assert r["affected_subscribers"] == 0
    assert r["sent"] == 0
    send.assert_called_once()
    session.refresh(o)
    assert o.push_resolved_at is not None  # claim antes del envío


def test_declared_expo_fail_no_reenvia(db):
    """Claim antes del envío: fallo Expo no libera un segundo declared."""
    session, org_id = db
    o = _add_outage(session, org_id, nas="nas-a")
    _add_abonado(session, org_id, dni="11100006")
    _add_device(
        session, org_id, dni="11100006", token="ExponentPushToken[d6]"
    )

    with (
        patch(
            "app.services.outages.abonado_afectado_por_nas",
            return_value=True,
        ),
        patch.object(
            app_push,
            "enviar_push_expo",
            return_value={"ok": False, "sent": 0, "status": 500},
        ) as send,
    ):
        r1 = app_push.notificar_incidente_app(
            session,
            org_id,
            title="Corte",
            body="msg",
            outage_id=o.id,
            nas_shortname="nas-a",
        )
        r2 = app_push.notificar_incidente_app(
            session,
            org_id,
            title="Corte",
            body="msg",
            outage_id=o.id,
            nas_shortname="nas-a",
        )

    assert r1["ok"] is False
    assert r2.get("skipped") == "already_declared"
    assert send.call_count == 1


def test_resolve_router_traga_error_push(db):
    from app.api.v1 import outages as outages_api

    session, org_id = db
    o = _add_outage(session, org_id, nas="nas-a")
    ctx = MagicMock()
    ctx.organizacion_id = org_id
    ctx.organizacion_slug = "coop-test"

    with (
        patch.object(
            outages_api.outage_svc,
            "outage_to_dict",
            return_value={"id": o.id, "estado": "resuelto"},
        ),
        patch(
            "app.services.app_push.notificar_incidente_resuelto_app",
            side_effect=RuntimeError("expo"),
        ),
    ):
        result = outages_api.resolve_outage(o.id, ctx, session)

    assert result["status"] == "resuelto"
    session.refresh(o)
    assert o.estado == "resuelto"


def test_claim_concurrente_solo_uno(db):
    session, org_id = db
    o = _add_outage(session, org_id, nas="nas-a")
    assert repo.claim_outage_push_declared(session, o.id) is True
    assert repo.claim_outage_push_declared(session, o.id) is False
    assert repo.claim_outage_push_resolved(session, o.id) is True
    assert repo.claim_outage_push_resolved(session, o.id) is False
