"""Tests de incidentes masivos / NAS Radius."""

from __future__ import annotations

from types import SimpleNamespace

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
    msg = outage_svc.plantilla_mensaje_cliente(
        alcance="parcial",
        comentario="Rama de fibra caída en calle San Martín",
        eta_minutos=45,
        nas_shortname="apposada",
    )
    assert "inconveniente" in msg.lower()
    assert "45" in msg
    assert "reclamo" in msg.lower()
    assert "San Martín" in msg


def test_plantilla_total():
    msg = outage_svc.plantilla_mensaje_cliente(
        alcance="total",
        comentario="",
        eta_minutos=30,
        nas_shortname="apchapa",
    )
    assert "masivo" in msg.lower()
    assert "30" in msg


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


def test_mensaje_ya_informado():
    o = SimpleNamespace(
        mensaje_cliente="Mensaje largo del incidente.",
        alcance="total",
        comentario="x",
        eta_minutos=40,
        nas_shortname="apposada",
    )
    first = outage_svc.mensaje_para_conversacion(o, ya_informado=False)
    again = outage_svc.mensaje_para_conversacion(o, ya_informado=True)
    assert first == "Mensaje largo del incidente."
    assert "Seguimos" in again
    assert "apposada" in again


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
        mensaje_cliente="Detectamos un inconveniente técnico masivo en tu zona.",
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
        session, org_id, conv, abo, ctx, canal="web"
    )
    assert resp is not None
    assert resp["ok"] is True
    assert "inconveniente" in resp["respuesta"].lower()
    assert resp["outage_nas"] == "apposada"
    assert "ticket_id" not in resp
    assert sent.get("texto")


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
    )
    assert resp is None
