"""Tests de incidentes masivos / NAS Radius."""

from __future__ import annotations

from types import SimpleNamespace

from datetime import UTC, datetime

from app.estate import repository as repo
from app.estate.models import Abonado
from app.radius.client import RadiusNasClient, parse_all_nas
from app.radius.contract import NasResourceStatus
from app.services import outages as outage_svc
from app.services.canal_abonado import _talvez_respuesta_outage


def test_parse_all_nas_payload_real():
    payload = {
        "status": "success",
        "count": 2,
        "data": [
            {"shortname": "apposada", "nasname": "181.41.244.186"},
            {"shortname": "apchapa", "nasname": "181.41.245.44"},
        ],
    }
    items = parse_all_nas(payload)
    assert len(items) == 2
    assert items[0].shortname == "apchapa"  # ordenado
    assert items[1].shortname == "apposada"
    assert items[1].nasname == "181.41.244.186"


def test_plantilla_parcial_incluye_comentario():
    started = datetime(2026, 8, 17, 17, 5, tzinfo=UTC)
    msg = outage_svc.plantilla_mensaje_cliente(
        alcance="parcial",
        comentario="Rama de fibra caída en calle San Martín",
        eta_minutos=45,
        nas_shortname="apposada",
        started_at=started,
        eta_validada="Sí",
    )
    assert "incidencia" in msg.lower()
    assert "validó" in msg.lower()
    assert "14:05" in msg
    assert "45" in msg
    assert "reclamo" in msg.lower()
    assert "San Martín" in msg


def test_plantilla_total():
    msg = outage_svc.plantilla_mensaje_cliente(
        alcance="total",
        comentario="",
        eta_minutos=30,
        nas_shortname="apchapa",
        started_at=datetime(2026, 8, 17, 12, 0, tzinfo=UTC),
        eta_validada="Sí",
    )
    assert "incidencia" in msg.lower()
    assert "validó" in msg.lower()
    assert "30" in msg


def test_plantilla_sin_eta_validada():
    msg = outage_svc.plantilla_mensaje_cliente(
        alcance="total",
        comentario="",
        eta_minutos=45,
        eta_validada="No",
    )
    assert "validó" in msg.lower()
    assert "45" not in msg
    assert "estimación" in msg.lower() or "confirmada" in msg.lower()


def test_mensaje_para_conversacion_regenera_texto_viejo_sin_valido():
    o = SimpleNamespace(
        mensaje_cliente="Hay un corte de fibra en tu zona. ETA 45 min.",
        alcance="total",
        comentario="",
        eta_minutos=45,
        eta_validada="Sí",
        started_at=datetime(2026, 8, 17, 17, 5, tzinfo=UTC),
        nas_shortname="apposada",
    )
    msg = outage_svc.mensaje_para_conversacion(o, ya_informado=False)
    assert "validó" in msg.lower()
    assert "14:05" in msg
    assert "45" in msg
    assert "Hay un corte de fibra" not in msg


def test_mensaje_para_conversacion_no_inventa_eta_sin_validar():
    o = SimpleNamespace(
        mensaje_cliente="",
        alcance="total",
        comentario="",
        eta_minutos=45,
        eta_validada="No",
        started_at=datetime(2026, 8, 17, 17, 5, tzinfo=UTC),
        nas_shortname="apposada",
    )
    msg = outage_svc.mensaje_para_conversacion(o, ya_informado=False)
    assert "validó" in msg.lower()
    assert "45" not in msg
    assert "confirmada" in msg.lower() or "confirmada" in msg.lower() or "todavía" in msg.lower()


def test_cliente_indica_problema_individual():
    assert outage_svc.cliente_indica_problema_individual("mis vecinos tienen internet")
    assert outage_svc.cliente_indica_problema_individual("solo en mi casa")
    assert not outage_svc.cliente_indica_problema_individual("no tengo internet")


def test_outage_activo_por_nas_match(db):
    session, org_id = db
    o = repo.create_network_outage(
        session,
        org_id,
        nas_shortname="apposada",
        nas_ip="181.41.244.186",
        alcance="parcial",
        comentario="rama caída",
        mensaje_cliente="Hay un corte parcial en tu zona.",
        eta_minutos=45,
    )
    assert outage_svc.outage_activo_para_nas(session, org_id, "apposada").id == o.id
    assert outage_svc.outage_activo_para_nas(session, org_id, "APPOSADA").id == o.id
    assert outage_svc.outage_activo_para_nas(session, org_id, "181.41.244.186").id == o.id
    assert outage_svc.outage_activo_para_nas(session, org_id, "otro") is None

    repo.resolve_network_outage(session, o)
    assert outage_svc.outage_activo_para_nas(session, org_id, "apposada") is None


def test_rest_list_resources_unreachable_contract():
    st = NasResourceStatus(shortname="caido", reachable=False, error="NAS not found")
    d = st.to_dict()
    assert d["reachable"] is False
    assert d["alcance_sugerido"] == "total"


def test_rest_list_resources_reachable_client(monkeypatch):
    client = RadiusNasClient(base_url="https://example.test", token="t")

    class _Resp:
        status_code = 200
        text = '{"uptime":"1d","version":"7.18","platform":"MikroTik"}'

        def json(self):
            return {"uptime": "1d", "version": "7.18", "platform": "MikroTik"}

    class _Http:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            return _Resp()

    monkeypatch.setattr("app.radius.client.httpx.Client", lambda **k: _Http())
    st = client.rest_list_resources("apposada")
    assert st.reachable is True
    assert st.to_dict()["alcance_sugerido"] == "parcial"


def test_rest_list_resources_down_client(monkeypatch):
    client = RadiusNasClient(base_url="https://example.test", token="t")

    class _Resp:
        status_code = 200
        text = '{"error":"NAS not found"}'

        def json(self):
            return {"error": "NAS not found"}

    class _Http:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            return _Resp()

    monkeypatch.setattr("app.radius.client.httpx.Client", lambda **k: _Http())
    st = client.rest_list_resources("caido")
    assert st.reachable is False
    assert "NAS not found" in st.error


def test_get_all_nas_client(monkeypatch):
    client = RadiusNasClient(base_url="https://example.test", api_key="k")

    class _Resp:
        status_code = 200
        text = "ok"

        def json(self):
            return {
                "status": "success",
                "data": [{"shortname": "apposada", "nasname": "1.2.3.4"}],
            }

    class _Http:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            return _Resp()

        def post(self, *a, **k):
            return _Resp()

    monkeypatch.setattr("app.radius.client.httpx.Client", lambda **k: _Http())
    items = client.get_all_nas()
    assert len(items) == 1
    assert items[0].shortname == "apposada"
    assert items[0].nasname == "1.2.3.4"


def test_mensaje_ya_informado_sin_nombre_tecnico():
    # Cache sin "validó" → se regenera plantilla autorizada
    o = SimpleNamespace(
        mensaje_cliente="Mensaje largo del incidente.",
        alcance="total",
        comentario="x",
        eta_minutos=40,
        eta_validada="Sí",
        started_at=datetime(2026, 8, 17, 14, 5, tzinfo=UTC),
        nas_shortname="apposada",
    )
    first = outage_svc.mensaje_para_conversacion(o, ya_informado=False)
    again = outage_svc.mensaje_para_conversacion(o, ya_informado=True)
    assert "validó" in first.lower()
    assert "40" in first
    assert "validada" in again.lower()
    assert "apposada" not in again
    assert "domicilio" in again.lower()

    # Cache con "validó" se respeta
    o2 = SimpleNamespace(
        mensaje_cliente=(
            "Detectamos una incidencia que afecta a tu zona. "
            "El equipo de operaciones la validó a las 11:05. "
            "La estimación actual de restitución es de 40 minutos. "
            "Te avisaremos si cambia el estado. No es necesario generar otro reclamo."
        ),
        alcance="total",
        comentario="x",
        eta_minutos=40,
        eta_validada="Sí",
        started_at=datetime(2026, 8, 17, 14, 5, tzinfo=UTC),
        nas_shortname="apposada",
    )
    assert outage_svc.mensaje_para_conversacion(o2, ya_informado=False) == o2.mensaje_cliente


def test_es_ack_outage():
    assert outage_svc.es_ack_outage("Gracias")
    assert outage_svc.es_ack_outage("ok")
    assert outage_svc.es_ack_outage("Ok!")
    assert outage_svc.es_ack_outage("Bien gracias")
    assert outage_svc.es_ack_outage("Si gracias")
    assert outage_svc.es_ack_outage("sí gracias")
    assert not outage_svc.es_ack_outage("sigue sin internet")
    assert not outage_svc.es_ack_outage("Internet")
    assert outage_svc.pide_estado_outage("Sigue la falla?")


def test_mensaje_resolucion():
    o = SimpleNamespace(nas_shortname="mkfobatan2")
    msg = outage_svc.mensaje_resolucion_outage(o)
    assert "resuelto" in msg.lower()
    assert "mkfobatan2" not in msg


def test_intencion_bloquea():
    assert outage_svc.intencion_bloquea_outage("facturacion")
    assert outage_svc.intencion_bloquea_outage("corte_deuda")
    assert not outage_svc.intencion_bloquea_outage("internet")
    assert not outage_svc.intencion_bloquea_outage("")


def test_interceptor_responde_sin_ticket(db, monkeypatch):
    session, org_id = db
    abo = Abonado(
        organizacion_id=org_id,
        dni="30111222",
        nombre="Test",
        telefono_e164="+5492234000000",
    )
    session.add(abo)
    session.commit()

    repo.create_network_outage(
        session,
        org_id,
        nas_shortname="apposada",
        comentario="corte",
        mensaje_cliente=(
            "Detectamos una incidencia que afecta a tu zona. "
            "El equipo de operaciones la validó. "
            "La estimación actual de restitución es de 45 minutos."
        ),
        eta_minutos=45,
    )

    monkeypatch.setattr(
        outage_svc,
        "resolver_nas_abonado",
        lambda db, abonado: "apposada",
    )

    conv = SimpleNamespace(
        id="conv-1",
        estado="bot",
        contexto_json="{}",
        servicio_detectado="",
        ticket_id="",
    )
    monkeypatch.setattr(
        "app.services.canal_abonado.crepo.set_contexto",
        lambda c, ctx: None,
    )
    monkeypatch.setattr(
        "app.services.canal_abonado.crepo.abonado_to_dict",
        lambda a: {"dni": a.dni},
    )
    sent = {}

    def _send(*a, **k):
        sent["texto"] = a[3] if len(a) > 3 else k.get("texto")

    monkeypatch.setattr("app.services.canal_abonado._enviar_respuesta", _send)

    ctx: dict = {}
    resp = _talvez_respuesta_outage(
        session, org_id, conv, abo, ctx, canal="web", texto="Internet"
    )
    assert resp is not None
    assert resp["ok"] is True
    assert "incidencia" in resp["respuesta"].lower()
    assert "validó" in resp["respuesta"].lower()
    assert resp["outage_nas"] == "apposada"
    assert "ticket_id" not in resp
    assert sent.get("texto")

    # Bien gracias → ack (variante real de WA)
    resp2 = _talvez_respuesta_outage(
        session, org_id, conv, abo, ctx, canal="web", texto="Bien gracias"
    )
    assert resp2 is not None
    assert "de nada" in resp2["respuesta"].lower()
    assert "todavía" not in resp2["respuesta"].lower()
    assert "apposada" not in resp2["respuesta"].lower()
    assert ctx.get("outage_ack") is True

    # Ok otra vez → cierre corto, sin insistir
    resp3 = _talvez_respuesta_outage(
        session, org_id, conv, abo, ctx, canal="web", texto="Ok"
    )
    assert resp3 is not None
    assert "cualquier cosa" in resp3["respuesta"].lower()

    # Problema aparentemente individual → no interceptar (N1)
    resp4 = _talvez_respuesta_outage(
        session, org_id, conv, abo, ctx, canal="web", texto="Mis vecinos tienen internet"
    )
    assert resp4 is None
    assert ctx.get("outage_individual") is True


def test_interceptor_avisa_cuando_se_resuelve(db, monkeypatch):
    session, org_id = db
    abo = Abonado(organizacion_id=org_id, dni="30111224", nombre="Test")
    session.add(abo)
    session.commit()
    o = repo.create_network_outage(
        session,
        org_id,
        nas_shortname="mkfobatan2",
        comentario="parcial",
        mensaje_cliente="Hay un corte parcial.",
    )
    monkeypatch.setattr(outage_svc, "resolver_nas_abonado", lambda *a, **k: "mkfobatan2")
    monkeypatch.setattr("app.services.canal_abonado.crepo.set_contexto", lambda *a, **k: None)
    monkeypatch.setattr(
        "app.services.canal_abonado.crepo.abonado_to_dict", lambda a: {"dni": a.dni}
    )
    monkeypatch.setattr("app.services.canal_abonado._enviar_respuesta", lambda *a, **k: None)
    conv = SimpleNamespace(id="c3", estado="bot", contexto_json="{}", servicio_detectado="", ticket_id="")
    ctx: dict = {}
    assert _talvez_respuesta_outage(
        session, org_id, conv, abo, ctx, canal="web", texto="Internet"
    )
    repo.resolve_network_outage(session, o)
    # Forzar cache previo (simula conversación ya avisada)
    ctx["outage_id"] = o.id
    ctx["outage_informado"] = True
    ctx["outage_nas"] = "mkfobatan2"
    resp = _talvez_respuesta_outage(
        session, org_id, conv, abo, ctx, canal="web", texto="Sigue la falla?"
    )
    assert resp is not None
    assert "resuelto" in resp["respuesta"].lower()
    assert "mkfobatan2" not in resp["respuesta"]
    assert ctx.get("outage_resuelto_avisado") == o.id

    # Tras resolución, "Si gracias" cierra el hilo (no deuda/N1)
    monkeypatch.setattr(
        "app.services.canal_abonado.enviar_encuesta_cierre",
        lambda *a, **k: None,
    )
    resp2 = _talvez_respuesta_outage(
        session, org_id, conv, abo, ctx, canal="web", texto="Si gracias"
    )
    assert resp2 is not None
    assert resp2.get("modo") == "cerrado" or "alegra" in resp2["respuesta"].lower()
    assert conv.estado == "cerrado"
    assert not ctx.get("outage_resuelto_avisado")


def test_cliente_salir_aviso_deuda():
    from app.services.canal_abonado import _cliente_salir_aviso_deuda

    assert _cliente_salir_aviso_deuda("No")
    assert _cliente_salir_aviso_deuda("No nada")
    assert _cliente_salir_aviso_deuda("Funciona todo bien")
    assert not _cliente_salir_aviso_deuda("quiero pagar")
    assert not _cliente_salir_aviso_deuda("seguí con el diagnóstico")


def test_interceptor_omite_facturacion(db, monkeypatch):
    session, org_id = db
    abo = Abonado(organizacion_id=org_id, dni="30111223", nombre="Test")
    session.add(abo)
    session.commit()
    repo.create_network_outage(
        session,
        org_id,
        nas_shortname="apposada",
        comentario="corte",
        mensaje_cliente="msg",
    )
    monkeypatch.setattr(outage_svc, "resolver_nas_abonado", lambda *a, **k: "apposada")
    conv = SimpleNamespace(id="c2", estado="bot", contexto_json="{}")
    resp = _talvez_respuesta_outage(
        session,
        org_id,
        conv,
        abo,
        {"intencion": "facturacion"},
        canal="web",
        texto="quiero pagar",
    )
    assert resp is None
