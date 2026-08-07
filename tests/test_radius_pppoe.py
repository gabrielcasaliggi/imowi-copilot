"""Tests Radius/NAS client + orquestación PPPoE (mocks, sin red)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.radius.client import RadiusNasClient, extract_nas_name, parse_ppp_sessions
from app.radius.contract import EstadoConexionPPPoE, ServicioConectividad, SesionPPPoE
from app.services.billtrack import (
    SERVICE_TYPE_CONECTIVIDAD,
    elegir_servicio_principal,
    map_service_row,
)


def test_extract_nas_variantes():
    assert extract_nas_name("NAS-01") == "NAS-01"
    assert extract_nas_name({"nas": "mk-fibra-1"}) == "mk-fibra-1"
    assert extract_nas_name({"data": {"nasname": "core-pppoe"}}) == "core-pppoe"
    assert extract_nas_name({"results": [{"ip": "10.0.0.1"}]}) == "10.0.0.1"
    assert extract_nas_name({}) == ""


def test_parse_ppp_session_lista_mikrotik():
    payload = [
        {
            "name": "4640854",
            "address": "181.41.1.20",
            "uptime": "2h31m",
            "caller-id": "AA:BB:CC:DD:EE:FF",
        }
    ]
    ses = parse_ppp_sessions("4640854", "nas-1", payload)
    assert ses.online is True
    assert ses.public_ip == "181.41.1.20"
    assert ses.uptime == "2h31m"
    assert ses.nas == "nas-1"


def test_parse_ppp_session_vacia():
    ses = parse_ppp_sessions("4640854", "nas-1", [])
    assert ses.online is False
    assert ses.public_ip == ""


def test_map_service_row_y_principal():
    row = {
        "id": "9",
        "login": "4640854",
        "service_type_code": "intfo",
        "service_type_label": "Fibra Optica",
        "product": "Fibra 100",
        "service_on": "true",
        "base_account_number": "200",
    }
    svc = map_service_row(row)
    assert svc.login == "4640854"
    assert svc.service_type_code == "INTFO"
    assert svc.service_type_code in SERVICE_TYPE_CONECTIVIDAD
    assert svc.service_on is True

    off = ServicioConectividad(login="1", service_on=False, service_type_code="INTBA")
    on = ServicioConectividad(login="2", service_on=True, service_type_code="INTFO")
    assert elegir_servicio_principal([off, on]).login == "2"
    assert elegir_servicio_principal([ServicioConectividad(login="")]) is None


def test_resumen_prompt_conectado():
    estado = EstadoConexionPPPoE(
        servicio=ServicioConectividad(
            login="4640854",
            service_type_label="Fibra Optica",
            service_type_code="INTFO",
        ),
        sesion=SesionPPPoE(
            username="4640854",
            online=True,
            nas="nas-1",
            public_ip="1.2.3.4",
            uptime="10m",
        ),
    )
    r = estado.resumen_prompt()
    assert "conectado" in r
    assert "1.2.3.4" in r
    assert "4640854" in r


def test_consultar_conexion_orquesta(monkeypatch):
    from app.services import conexion_pppoe as cp
    from app.services import billtrack as bt

    monkeypatch.setattr(
        bt,
        "lookup_servicios_conectividad_por_dni",
        lambda dni, db=None: [
            ServicioConectividad(
                login="4640854",
                service_type_code="INTFO",
                service_type_label="Fibra Optica",
                service_on=True,
            )
        ],
    )

    fake = MagicMock()
    fake.sesion_para_login.return_value = SesionPPPoE(
        username="4640854",
        online=True,
        nas="NAS-A",
        public_ip="10.1.2.3",
        uptime="1h",
    )
    monkeypatch.setattr(cp, "resolve_radius_client", lambda db=None: fake)

    estado = cp.consultar_conexion_pppoe(dni="30111222")
    assert estado.online is True
    assert estado.servicio is not None
    assert estado.servicio.login == "4640854"
    assert estado.sesion is not None
    assert estado.sesion.public_ip == "10.1.2.3"
    fake.sesion_para_login.assert_called_once_with("4640854")


def test_contexto_pppoe_sin_radius_vacio(monkeypatch):
    from app.services import conexion_pppoe as cp

    monkeypatch.setattr(cp, "resolve_radius_client", lambda db=None: None)
    abo = SimpleNamespace(dni="30111222", client_number="")
    ctx = cp.contexto_pppoe_para_abonado(abo)
    assert ctx["pppoe_estado"] == ""
    assert ctx["pppoe_resumen"] == ""


def test_contexto_pppoe_conectado(monkeypatch):
    from app.services import conexion_pppoe as cp

    monkeypatch.setattr(cp, "resolve_radius_client", lambda db=None: MagicMock())
    monkeypatch.setattr(
        cp,
        "consultar_conexion_pppoe",
        lambda **kwargs: EstadoConexionPPPoE(
            servicio=ServicioConectividad(
                login="4640854",
                service_type_label="Fibra Optica",
                service_type_code="INTFO",
            ),
            sesion=SesionPPPoE(
                username="4640854",
                online=True,
                nas="NAS-A",
                public_ip="9.9.9.9",
                uptime="5m",
            ),
        ),
    )
    abo = SimpleNamespace(dni="30111222")
    ctx = cp.contexto_pppoe_para_abonado(abo)
    assert ctx["pppoe_estado"] == "conectado"
    assert ctx["pppoe_ip"] == "9.9.9.9"
    assert "conectado" in ctx["pppoe_resumen"]


def test_mensaje_abonado_conectado_y_offline():
    from app.services.conexion_pppoe import mensaje_abonado_pppoe

    online = EstadoConexionPPPoE(
        servicio=ServicioConectividad(
            login="4640854",
            service_type_label="Fibra Optica",
            service_type_code="INTFO",
        ),
        sesion=SesionPPPoE(
            username="4640854",
            online=True,
            public_ip="1.2.3.4",
            uptime="2h",
        ),
    )
    msg = mensaje_abonado_pppoe(online)
    assert msg is not None
    assert "activa" in msg.lower() or "conectado" in msg.lower() or "activa" in msg
    assert "1.2.3.4" in msg

    offline = EstadoConexionPPPoE(
        servicio=ServicioConectividad(
            login="4640854",
            service_type_label="Fibra Optica",
            service_type_code="INTFO",
        ),
        sesion=SesionPPPoE(username="4640854", online=False, nas="NAS-A"),
    )
    msg2 = mensaje_abonado_pppoe(offline)
    assert msg2 is not None
    assert "no hay sesión" in msg2.lower() or "no figura conectado" in msg2.lower()


def test_mensaje_abonado_sin_dato():
    from app.services.conexion_pppoe import mensaje_abonado_pppoe

    assert mensaje_abonado_pppoe(EstadoConexionPPPoE(error="radius api no configurada")) is None


def test_radius_client_headers_no_leak_empty():
    c = RadiusNasClient(api_key="", token="")
    assert c.configured() is False
    c2 = RadiusNasClient(api_key="k", token="t")
    h = c2._headers()
    assert h["Authorization"] == "Bearer t"
    assert h["X-API-KEY"] == "k"
