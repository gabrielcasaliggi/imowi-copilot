"""E′3 — política de push updated (cambios materiales)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.api.v1 import outages as outages_api
from app.estate import repository as repo
from app.estate.models import Abonado, PortalDevice
from app.services import app_push
from app.services import outages as outage_svc


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


def _add_outage(
    session,
    org_id: str,
    *,
    nas: str = "nas-a",
    mensaje: str = "Mensaje A",
    eta: int = 30,
    eta_validada: str = "No",
    alcance: str = "total",
    comentario: str = "interno A",
):
    return repo.create_network_outage(
        session,
        org_id,
        nas_shortname=nas,
        alcance=alcance,
        comentario=comentario,
        mensaje_cliente=mensaje,
        eta_minutos=eta,
        eta_validada=eta_validada,
        created_by="test",
    )


def test_material_mensaje_cambia():
    assert (
        outage_svc.outage_update_es_material(
            prev_mensaje_cliente="Mensaje A",
            new_mensaje_cliente="Mensaje B",
            prev_eta_minutos=30,
            new_eta_minutos=30,
            prev_eta_validada="No",
            new_eta_validada="No",
            prev_alcance="total",
            new_alcance="parcial",
            touched_alcance=True,
        )
        is True
    )


def test_material_mensaje_igual():
    assert (
        outage_svc.outage_update_es_material(
            prev_mensaje_cliente="Mensaje A",
            new_mensaje_cliente="Mensaje A",
            prev_eta_minutos=30,
            new_eta_minutos=30,
            prev_eta_validada="Sí",
            new_eta_validada="Sí",
            prev_alcance="total",
            new_alcance="total",
            touched_comentario=True,
            touched_alcance=True,
            touched_eta_minutos=True,
        )
        is False
    )


def test_material_solo_comentario_no():
    assert (
        outage_svc.outage_update_es_material(
            prev_mensaje_cliente="Mensaje A",
            new_mensaje_cliente="Mensaje A con comentario B embebido",
            prev_eta_minutos=30,
            new_eta_minutos=30,
            prev_eta_validada="No",
            new_eta_validada="No",
            prev_alcance="parcial",
            new_alcance="parcial",
            touched_comentario=True,
        )
        is False
    )


def test_material_eta_no_validada_no():
    assert (
        outage_svc.outage_update_es_material(
            prev_mensaje_cliente="sin eta",
            new_mensaje_cliente="sin eta pero plantilla distinta",
            prev_eta_minutos=30,
            new_eta_minutos=20,
            prev_eta_validada="No",
            new_eta_validada="No",
            prev_alcance="total",
            new_alcance="total",
            touched_eta_minutos=True,
        )
        is False
    )


def test_material_eta_validada_cambia_si():
    assert (
        outage_svc.outage_update_es_material(
            prev_mensaje_cliente="eta 30",
            new_mensaje_cliente="eta 20",
            prev_eta_minutos=30,
            new_eta_minutos=20,
            prev_eta_validada="Sí",
            new_eta_validada="Sí",
            prev_alcance="total",
            new_alcance="total",
            touched_eta_minutos=True,
        )
        is True
    )


def test_material_eta_pasa_a_validada_si():
    assert (
        outage_svc.outage_update_es_material(
            prev_mensaje_cliente="sin eta",
            new_mensaje_cliente="con eta",
            prev_eta_minutos=30,
            new_eta_minutos=30,
            prev_eta_validada="No",
            new_eta_validada="Sí",
            prev_alcance="total",
            new_alcance="total",
            touched_eta_validada=True,
        )
        is True
    )


def test_material_eta_igual_no():
    assert (
        outage_svc.outage_update_es_material(
            prev_mensaje_cliente="eta 30",
            new_mensaje_cliente="eta 30",
            prev_eta_minutos=30,
            new_eta_minutos=30,
            prev_eta_validada="Sí",
            new_eta_validada="Sí",
            prev_alcance="total",
            new_alcance="total",
            touched_eta_minutos=True,
        )
        is False
    )


def test_patch_eta_validada_dispara_updated(db):
    session, org_id = db
    o = _add_outage(
        session,
        org_id,
        mensaje="Antes",
        eta=30,
        eta_validada="Sí",
    )
    _add_abonado(session, org_id, dni="31100001")
    _add_device(
        session, org_id, dni="31100001", token="ExponentPushToken[u1]"
    )
    ctx = MagicMock()
    ctx.organizacion_id = org_id
    ctx.organizacion_slug = "coop-test"
    body = outages_api.OutageUpdate(eta_minutos=20, usar_ia=False)
    captured = {}

    def _send(tokens, *, title, body, data=None):
        captured["data"] = dict(data or {})
        captured["title"] = title
        captured["body"] = body
        return {"ok": True, "sent": len(tokens)}

    with (
        patch(
            "app.services.outages.abonado_afectado_por_nas",
            return_value=True,
        ),
        patch.object(app_push, "enviar_push_expo", side_effect=_send),
        patch.object(
            outages_api.outage_svc,
            "generar_mensaje_cliente",
            return_value="Mensaje con ETA 20",
        ),
    ):
        result = outages_api.update_outage(o.id, body, ctx, session)

    assert result["status"] == "actualizado"
    assert captured["data"]["event"] == "updated"
    assert captured["data"]["tipo"] == "incidente"
    assert captured["data"]["outage_id"] == o.id
    assert "nas" not in captured["data"]
    assert captured["title"] == app_push.TITLE_UPDATED


def test_patch_comentario_no_push(db):
    session, org_id = db
    o = _add_outage(session, org_id, comentario="interno A")
    _add_abonado(session, org_id, dni="31100002")
    _add_device(
        session, org_id, dni="31100002", token="ExponentPushToken[u2]"
    )
    ctx = MagicMock()
    ctx.organizacion_id = org_id
    body = outages_api.OutageUpdate(comentario="interno B", usar_ia=False)

    with (
        patch(
            "app.services.outages.abonado_afectado_por_nas",
            return_value=True,
        ),
        patch.object(app_push, "enviar_push_expo") as send,
        patch.object(
            outages_api.outage_svc,
            "generar_mensaje_cliente",
            return_value="Mensaje regenerado por comentario",
        ),
    ):
        outages_api.update_outage(o.id, body, ctx, session)

    send.assert_not_called()


def test_patch_eta_no_validada_no_push(db):
    session, org_id = db
    o = _add_outage(session, org_id, eta=30, eta_validada="No")
    _add_abonado(session, org_id, dni="31100003")
    _add_device(
        session, org_id, dni="31100003", token="ExponentPushToken[u3]"
    )
    ctx = MagicMock()
    ctx.organizacion_id = org_id
    body = outages_api.OutageUpdate(eta_minutos=20, usar_ia=False)

    with (
        patch(
            "app.services.outages.abonado_afectado_por_nas",
            return_value=True,
        ),
        patch.object(app_push, "enviar_push_expo") as send,
        patch.object(
            outages_api.outage_svc,
            "generar_mensaje_cliente",
            return_value="Plantilla sin eta confirmada",
        ),
    ):
        outages_api.update_outage(o.id, body, ctx, session)

    send.assert_not_called()


def test_patch_nas_distinto_cero(db):
    session, org_id = db
    o = _add_outage(session, org_id, eta=30, eta_validada="Sí")
    _add_abonado(session, org_id, dni="31100004")
    _add_device(
        session, org_id, dni="31100004", token="ExponentPushToken[u4]"
    )
    ctx = MagicMock()
    ctx.organizacion_id = org_id
    body = outages_api.OutageUpdate(eta_minutos=15, usar_ia=False)

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
        patch.object(
            outages_api.outage_svc,
            "generar_mensaje_cliente",
            return_value="ETA 15",
        ),
    ):
        outages_api.update_outage(o.id, body, ctx, session)

    assert send.call_count == 1
    assert send.call_args.args[0] == [] or send.call_args.kwargs.get(
        "data", {}
    ).get("event") == "updated"


def test_patch_multi_device(db):
    session, org_id = db
    o = _add_outage(session, org_id, eta=30, eta_validada="Sí")
    _add_abonado(session, org_id, dni="31100005")
    t1 = "ExponentPushToken[ua]"
    t2 = "ExponentPushToken[ub]"
    _add_device(session, org_id, dni="31100005", token=t1)
    _add_device(session, org_id, dni="31100005", token=t2)
    ctx = MagicMock()
    ctx.organizacion_id = org_id
    body = outages_api.OutageUpdate(eta_minutos=10, usar_ia=False)
    captured = {}

    def _send(tokens, *, title, body, data=None):
        captured["tokens"] = list(tokens)
        return {"ok": True, "sent": len(tokens)}

    with (
        patch(
            "app.services.outages.abonado_afectado_por_nas",
            return_value=True,
        ),
        patch.object(app_push, "enviar_push_expo", side_effect=_send),
        patch.object(
            outages_api.outage_svc,
            "generar_mensaje_cliente",
            return_value="ETA 10",
        ),
    ):
        outages_api.update_outage(o.id, body, ctx, session)

    assert set(captured["tokens"]) == {t1, t2}


def test_patch_expo_fail_no_rompe(db):
    session, org_id = db
    o = _add_outage(session, org_id, eta=30, eta_validada="Sí")
    ctx = MagicMock()
    ctx.organizacion_id = org_id
    body = outages_api.OutageUpdate(eta_minutos=5, usar_ia=False)

    with (
        patch(
            "app.services.app_push.notificar_incidente_actualizado_app",
            side_effect=RuntimeError("expo"),
        ),
        patch.object(
            outages_api.outage_svc,
            "generar_mensaje_cliente",
            return_value="ETA 5",
        ),
        patch.object(
            outages_api.outage_svc,
            "outage_to_dict",
            return_value={"id": o.id, "estado": "activo"},
        ),
    ):
        result = outages_api.update_outage(o.id, body, ctx, session)

    assert result["status"] == "actualizado"


def test_resuelto_no_acepta_patch_updated(db):
    session, org_id = db
    o = _add_outage(session, org_id, eta=30, eta_validada="Sí")
    o = repo.resolve_network_outage(session, o)
    ctx = MagicMock()
    ctx.organizacion_id = org_id
    body = outages_api.OutageUpdate(eta_minutos=5, usar_ia=False)

    from fastapi import HTTPException

    with patch.object(app_push, "enviar_push_expo") as send:
        try:
            outages_api.update_outage(o.id, body, ctx, session)
            raised = False
        except HTTPException as exc:
            raised = True
            assert exc.status_code == 400
    assert raised is True
    send.assert_not_called()


def test_resolve_no_emite_updated(db):
    session, org_id = db
    o = _add_outage(session, org_id)
    _add_abonado(session, org_id, dni="31100006")
    _add_device(
        session, org_id, dni="31100006", token="ExponentPushToken[u6]"
    )
    ctx = MagicMock()
    ctx.organizacion_id = org_id
    events = []

    def _send(tokens, *, title, body, data=None):
        events.append((data or {}).get("event"))
        return {"ok": True, "sent": len(tokens)}

    with (
        patch(
            "app.services.outages.abonado_afectado_por_nas",
            return_value=True,
        ),
        patch.object(app_push, "enviar_push_expo", side_effect=_send),
        patch.object(
            outages_api.outage_svc,
            "outage_to_dict",
            return_value={"id": o.id, "estado": "resuelto"},
        ),
    ):
        outages_api.resolve_outage(o.id, ctx, session)

    assert events == ["resolved"]
