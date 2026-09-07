"""Pre-triaje: padrón → Radius → BCM/UISP antes del cuestionario hogareño."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.bcm.contract import EstadoOnuBcm
from app.radius.contract import EstadoConexionPPPoE, ServicioConectividad, SesionPPPoE
from app.services.pre_triaje_acceso import (
    linea_padron,
    mensaje_pre_triaje_acceso,
    nota_administrativa,
)
from app.uisp.contract import EstadoCpeUisp


def _abo(**kw):
    base = dict(
        dni="30111222",
        client_number="12345",
        servicio="internet",
        estado="activo",
        deuda_monto="0",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _ftth_online(**kw):
    return EstadoConexionPPPoE(
        servicio=ServicioConectividad(
            login="4640854",
            service_type_label="Fibra Optica",
            service_type_code="INTFO",
            product="Ecolan 50Mb",
            service_on=True,
        ),
        sesion=SesionPPPoE(
            username="4640854",
            online=True,
            public_ip="181.41.1.20",
            uptime="4d4h",
        ),
        **kw,
    )


def test_padron_nombra_fibra():
    txt = linea_padron(_ftth_online())
    assert "fibra" in txt.lower()
    assert "Ecolan 50Mb" in txt


def test_admin_servicio_apagado():
    svc = ServicioConectividad(login="1", service_on=False, state="baja")
    nota = nota_administrativa(_abo(), svc)
    assert "apagado" in nota.lower() or "baja" in nota.lower()
    assert "administrativ" in nota.lower()
    assert "padrón" not in nota.lower() and "padron" not in nota.lower()


def test_habilitado_no_acusa_baja():
    svc = ServicioConectividad(
        login="palaciosvaleBAI",
        state="Habilitado",
        product="Internet acceso Bai Hogar 15MB",
        service_on=True,
    )
    assert nota_administrativa(_abo(), svc) == ""
    assert nota_administrativa(_abo(estado="activo"), svc) == ""


def test_todo_ok_demuestra_acceso_y_pregunta_cable():
    onu = EstadoOnuBcm(
        numero_cliente="12345",
        encontrado=True,
        online=True,
        rx_dbm=-18.0,
        calidad_optica="buena",
    )
    msg = mensaje_pre_triaje_acceso(
        _ftth_online(),
        abonado=_abo(),
        onu=onu,
        es_ftth=True,
    )
    assert msg
    low = msg.lower()
    assert "padrón" not in low and "padron" not in low
    assert "sistema" in low or "figura" in low
    assert "activa" in low
    assert "wifi" in low or "wi-fi" in low or "wi‑fi" in low
    assert "cable" in low
    assert "toda la casa" not in low
    assert "lejos del router" not in low


def test_sin_sesion_no_arranca_por_wifi():
    estado = EstadoConexionPPPoE(
        servicio=ServicioConectividad(
            login="4640854",
            service_type_code="INTFO",
            service_type_label="Fibra Optica",
        ),
        sesion=SesionPPPoE(username="4640854", online=False),
    )
    msg = mensaje_pre_triaje_acceso(estado, abonado=_abo(), es_ftth=True)
    assert msg
    low = msg.lower()
    assert "no figura conectado" in low or "no hay sesión" in low
    assert "toda la casa" not in low
    assert "luces" in low or "reinici" in low


def test_radius_caido_igual_informa_padron():
    estado = EstadoConexionPPPoE(
        servicio=ServicioConectividad(
            login="4640854",
            service_type_code="INTFO",
            service_type_label="Fibra Optica",
        ),
        error="radius api no configurada",
    )
    msg = mensaje_pre_triaje_acceso(estado, abonado=_abo(), es_ftth=True)
    assert msg
    low = msg.lower()
    assert "padrón" not in low and "padron" not in low
    assert "sistema" in low or "figura" in low
    assert "no pude" in low or "luces" in low


def test_onu_offline_lo_dice_antes_del_cuestionario():
    estado = _ftth_online()
    onu = EstadoOnuBcm(
        numero_cliente="12345",
        encontrado=True,
        online=False,
    )
    msg = mensaje_pre_triaje_acceso(
        estado, abonado=_abo(), onu=onu, es_ftth=True
    )
    assert msg
    assert "no está registrada" in msg.lower() or "central" in msg.lower()
    assert "181.41.1.20" not in msg


def test_canal_pre_triaje_sin_radius_no_devuelve_none(monkeypatch):
    from app.services import canal_pppoe as cp
    from app.services import conexion_bcm as cb
    from app.services import conexion_pppoe as cpp
    from app.services import conexion_uisp as cu

    estado = EstadoConexionPPPoE(
        servicio=ServicioConectividad(
            login="4640854",
            service_type_code="INTFO",
            service_type_label="Fibra Optica",
        ),
        error="radius api no configurada",
    )
    monkeypatch.setattr(cpp, "consultar_conexion_pppoe", lambda **kw: estado)
    monkeypatch.setattr(cu, "resolve_uisp_client", lambda db=None: None)
    monkeypatch.setattr(cb, "resolve_bcm_client", lambda db=None: None)

    msg = cp._talvez_mensaje_pppoe(MagicMock(), _abo(), {}, "internet")
    assert msg
    assert "padrón" not in msg.lower() and "padron" not in msg.lower()
    assert "fibra" in msg.lower() or "sistema" in msg.lower() or "luces" in msg.lower()


def test_radio_sin_cpe_dice_antena_no_enlazada_no_reactivacion():
    estado = EstadoConexionPPPoE(
        servicio=ServicioConectividad(
            login="palaciosvaleBAI",
            service_type_code="INTBA",
            service_type_label="ACCESO INTERNET INALAMBRICO",
            product="Internet acceso Bai Hogar 15MB",
            state="Habilitado",
            service_on=True,
        ),
        error="radius timeout",
    )
    cpe = EstadoCpeUisp(login="palaciosvaleBAI", encontrado=False)
    msg = mensaje_pre_triaje_acceso(
        estado, abonado=_abo(), cpe=cpe, es_radio=True
    )
    assert msg
    low = msg.lower()
    assert "padrón" not in low and "padron" not in low
    assert "sistema" in low
    assert "15MB" in msg or "15mb" in low
    assert "enlazada" in low
    assert "baja" not in low or "no es una baja" in low
    assert "reactiv" not in low
    assert "pago" not in low
