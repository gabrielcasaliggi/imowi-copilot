"""E′1 — segmentación de push por NAS + payload seguro."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.estate import repository as repo
from app.estate.models import Abonado, PortalDevice
from app.services import app_push
from app.services import outages as outage_svc


def _add_abonado(session, org_id: str, *, dni: str, client_number: str = "") -> Abonado:
    abo = Abonado(
        organizacion_id=org_id,
        dni=dni,
        nombre=f"Test {dni}",
        client_number=client_number,
        telefono_e164="",
        servicio="internet",
        estado="activo",
    )
    session.add(abo)
    session.commit()
    session.refresh(abo)
    return abo


def _add_device(
    session,
    org_id: str,
    *,
    dni: str,
    token: str,
    activo: str = "Sí",
) -> PortalDevice:
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


def test_abonado_afectado_match_nas(db):
    session, org_id = db
    abo = _add_abonado(session, org_id, dni="30111222")

    svc = SimpleNamespace(login="user-a")
    sesion = SimpleNamespace(nas="nas-a", online=True, error="")

    client = MagicMock()
    client.sesion_para_login.return_value = sesion

    with (
        patch(
            "app.services.conexion_pppoe.resolve_radius_client",
            return_value=client,
        ),
        patch(
            "app.services.billtrack.lookup_servicios_conectividad_por_dni",
            return_value=[svc],
        ),
    ):
        assert outage_svc.abonado_afectado_por_nas(session, abo, "nas-a") is True
        assert outage_svc.abonado_afectado_por_nas(session, abo, "NAS-A") is True


def test_abonado_no_afectado_otro_nas(db):
    session, org_id = db
    abo = _add_abonado(session, org_id, dni="30111223")
    svc = SimpleNamespace(login="user-b")
    sesion = SimpleNamespace(nas="nas-b", online=True, error="")
    client = MagicMock()
    client.sesion_para_login.return_value = sesion

    with (
        patch(
            "app.services.conexion_pppoe.resolve_radius_client",
            return_value=client,
        ),
        patch(
            "app.services.billtrack.lookup_servicios_conectividad_por_dni",
            return_value=[svc],
        ),
    ):
        assert outage_svc.abonado_afectado_por_nas(session, abo, "nas-a") is False


def test_abonado_sin_nas_resoluble(db):
    session, org_id = db
    abo = _add_abonado(session, org_id, dni="30111224")

    with patch(
        "app.services.conexion_pppoe.resolve_radius_client",
        return_value=None,
    ):
        assert outage_svc.abonado_afectado_por_nas(session, abo, "nas-a") is False

    client = MagicMock()
    client.sesion_para_login.return_value = SimpleNamespace(nas="", online=False, error="x")
    with (
        patch(
            "app.services.conexion_pppoe.resolve_radius_client",
            return_value=client,
        ),
        patch(
            "app.services.billtrack.lookup_servicios_conectividad_por_dni",
            return_value=[SimpleNamespace(login="u1")],
        ),
    ):
        assert outage_svc.abonado_afectado_por_nas(session, abo, "nas-a") is False


def test_abonado_multi_servicio_uno_matchea(db):
    session, org_id = db
    abo = _add_abonado(session, org_id, dni="30111225")
    servicios = [SimpleNamespace(login="svc-b"), SimpleNamespace(login="svc-a")]

    def _sesion(login: str):
        if login == "svc-b":
            return SimpleNamespace(nas="nas-b", online=True, error="")
        return SimpleNamespace(nas="nas-a", online=True, error="")

    client = MagicMock()
    client.sesion_para_login.side_effect = _sesion

    with (
        patch(
            "app.services.conexion_pppoe.resolve_radius_client",
            return_value=client,
        ),
        patch(
            "app.services.billtrack.lookup_servicios_conectividad_por_dni",
            return_value=servicios,
        ),
    ):
        assert outage_svc.abonado_afectado_por_nas(session, abo, "nas-a") is True


def test_listar_tokens_afectado_y_no_afectado(db):
    session, org_id = db
    abo_ok = _add_abonado(session, org_id, dni="40111222")
    abo_no = _add_abonado(session, org_id, dni="40111223")
    _ = abo_ok
    _ = abo_no
    tok_ok = "ExponentPushToken[affected-device]"
    tok_no = "ExponentPushToken[other-device]"
    _add_device(session, org_id, dni="40111222", token=tok_ok)
    _add_device(session, org_id, dni="40111223", token=tok_no)

    def _match(_db, abo, nas, *, nas_ip_outage=""):
        return str(abo.dni) == "40111222" and nas == "nas-a"

    with patch(
        "app.services.outages.abonado_afectado_por_nas",
        side_effect=_match,
    ):
        tokens, affected = app_push.listar_tokens_afectados_por_nas(
            session, org_id, "nas-a"
        )

    assert affected == 1
    assert tokens == [tok_ok]
    assert tok_no not in tokens


def test_listar_tokens_sin_nas_resoluble_cero(db):
    session, org_id = db
    _add_abonado(session, org_id, dni="50111222")
    _add_device(
        session,
        org_id,
        dni="50111222",
        token="ExponentPushToken[no-nas]",
    )

    with patch(
        "app.services.outages.abonado_afectado_por_nas",
        return_value=False,
    ):
        tokens, affected = app_push.listar_tokens_afectados_por_nas(
            session, org_id, "nas-a"
        )

    assert affected == 0
    assert tokens == []


def test_listar_tokens_multi_device(db):
    session, org_id = db
    _add_abonado(session, org_id, dni="60111222")
    t1 = "ExponentPushToken[dev-a]"
    t2 = "ExponentPushToken[dev-b]"
    _add_device(session, org_id, dni="60111222", token=t1)
    _add_device(session, org_id, dni="60111222", token=t2)

    with patch(
        "app.services.outages.abonado_afectado_por_nas",
        return_value=True,
    ):
        tokens, affected = app_push.listar_tokens_afectados_por_nas(
            session, org_id, "nas-a"
        )

    assert affected == 1
    assert set(tokens) == {t1, t2}


def test_payload_seguro_sin_nas(db):
    session, org_id = db
    o = repo.create_network_outage(
        session,
        org_id,
        nas_shortname="nas-secret",
        comentario="interno",
        mensaje_cliente="Mensaje cliente seguro",
    )
    _add_abonado(session, org_id, dni="70111222")
    _add_device(
        session,
        org_id,
        dni="70111222",
        token="ExponentPushToken[payload]",
    )

    captured: dict = {}

    def _fake_enviar(tokens, *, title, body, data=None):
        captured["tokens"] = tokens
        captured["data"] = dict(data or {})
        return {"ok": True, "sent": len(tokens)}

    with (
        patch(
            "app.services.outages.abonado_afectado_por_nas",
            return_value=True,
        ),
        patch.object(app_push, "enviar_push_expo", side_effect=_fake_enviar),
    ):
        result = app_push.notificar_incidente_app(
            session,
            org_id,
            title="Corte en la red",
            body="Mensaje cliente seguro",
            outage_id=o.id,
            nas_shortname="nas-secret",
            nas_ip="1.2.3.4",
            data={"nas": "nas-secret", "comentario": "interno", "foo": "bar"},
        )

    assert result["ok"] is True
    assert result["sent"] == 1
    data = captured["data"]
    assert data["tipo"] == "incidente"
    assert data["outage_id"] == o.id
    assert data["event"] == "declared"
    assert "nas" not in data
    assert "nas_shortname" not in data
    assert "nas_ip" not in data
    assert "comentario" not in data
    assert "created_by" not in data
    # claves extra no prohibidas pueden pasar; nas/comentario no
    assert data.get("foo") == "bar"


def test_expo_failure_no_rompe_notificar(db):
    session, org_id = db
    o = repo.create_network_outage(
        session,
        org_id,
        nas_shortname="nas-a",
        comentario="x",
        mensaje_cliente="body",
    )
    _add_abonado(session, org_id, dni="80111222")
    _add_device(
        session,
        org_id,
        dni="80111222",
        token="ExponentPushToken[fail]",
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
        ),
    ):
        result = app_push.notificar_incidente_app(
            session,
            org_id,
            title="Corte",
            body="body",
            outage_id=o.id,
            nas_shortname="nas-a",
        )

    assert result["ok"] is False
    assert result["sent"] == 0
    assert result["affected_subscribers"] == 1


def test_create_outage_router_traga_error_push(db):
    """POST create: excepción en notificar_incidente_app no impide respuesta creado."""
    from unittest.mock import MagicMock

    from app.api.v1 import outages as outages_api

    session, org_id = db
    ctx = MagicMock()
    ctx.organizacion_id = org_id
    ctx.organizacion_slug = "coop-test"
    ctx.usuario_email = "ops@test"
    ctx.usuario_nombre = "Ops"

    body = outages_api.OutageCreate(
        nas_shortname="nas-a",
        comentario="Fibra cortada en zona test",
        eta_minutos=45,
        eta_validada=False,
        usar_ia=False,
    )

    fake_outage = MagicMock()
    fake_outage.id = "out-1"
    fake_outage.nas_ip = ""
    fake_outage.nas_shortname = "nas-a"
    fake_outage.started_at = None

    with (
        patch.object(outages_api.outage_svc, "outage_activo_para_nas", return_value=None),
        patch.object(
            outages_api.outage_svc,
            "health_nas",
            side_effect=RuntimeError("skip health"),
        ),
        patch.object(
            outages_api.repo,
            "create_network_outage",
            return_value=fake_outage,
        ),
        patch.object(
            outages_api.outage_svc,
            "generar_mensaje_cliente",
            return_value="Mensaje cliente",
        ),
        patch.object(
            outages_api.repo,
            "update_network_outage",
            return_value=fake_outage,
        ),
        patch.object(
            outages_api.outage_svc,
            "outage_to_dict",
            return_value={"id": "out-1", "estado": "activo"},
        ),
        patch(
            "app.services.app_push.notificar_incidente_app",
            side_effect=RuntimeError("expo down"),
        ),
    ):
        result = outages_api.create_outage(body, ctx, session)

    assert result["status"] == "creado"
    assert result["outage"]["id"] == "out-1"


def test_notificar_incidente_no_usa_org_wide(db):
    session, org_id = db
    o = repo.create_network_outage(
        session,
        org_id,
        nas_shortname="nas-a",
        comentario="x",
        mensaje_cliente="body",
    )
    _add_abonado(session, org_id, dni="90111222")
    _add_device(
        session,
        org_id,
        dni="90111222",
        token="ExponentPushToken[orgwide]",
    )

    with (
        patch(
            "app.services.outages.abonado_afectado_por_nas",
            return_value=False,
        ),
        patch.object(app_push, "listar_tokens_org") as org_wide,
        patch.object(
            app_push,
            "enviar_push_expo",
            return_value={"ok": True, "sent": 0},
        ) as send,
    ):
        app_push.notificar_incidente_app(
            session,
            org_id,
            title="Corte",
            body="body",
            outage_id=o.id,
            nas_shortname="nas-a",
        )

    org_wide.assert_not_called()
    send.assert_called_once()
    assert send.call_args.kwargs["data"]["tipo"] == "incidente"
    assert "nas" not in send.call_args.kwargs["data"]
