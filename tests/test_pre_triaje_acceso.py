"""Pre-triaje: protocolo de mesa (cuenta → sondas → diálogo)."""

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
            state="Habilitado",
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
    assert "baja" in nota.lower()
    assert "pagar" in nota.lower() or "ov.batan" in nota.lower()
    assert "padrón" not in nota.lower() and "padron" not in nota.lower()
    assert "wifi" not in nota.lower() and "wi‑fi" not in nota.lower()


def test_habilitado_no_acusa_baja():
    svc = ServicioConectividad(
        login="palaciosvaleBAI",
        state="Habilitado",
        product="Internet acceso Bai Hogar 15MB",
        service_on=True,
    )
    assert nota_administrativa(_abo(), svc) == ""
    assert nota_administrativa(_abo(estado="activo"), svc) == ""


def test_todo_ok_demuestra_acceso_y_pregunta_wifi():
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
    assert "billtrack" not in low and "radius" not in low and "bcm" not in low
    assert "181.41.1.20" in msg
    assert "activa" in low
    assert "potencia" in low or "-18" in msg
    assert "wifi" in low or "wi-fi" in low or "wi‑fi" in low
    assert "cable" in low
    assert "toda la casa" not in low
    assert "lejos del router" not in low


def test_radius_ok_sin_planta_muestra_sesion():
    estado = _ftth_online()
    msg = mensaje_pre_triaje_acceso(estado, abonado=_abo(), es_ftth=True)
    assert msg
    assert "181.41.1.20" in msg
    assert "activa" in msg.lower()
    assert "wifi" in msg.lower() or "wi‑fi" in msg.lower() or "wi-fi" in msg.lower()
    assert "luces" not in msg.lower()

def test_sin_sesion_pregunta_luces_no_wifi():
    estado = EstadoConexionPPPoE(
        servicio=ServicioConectividad(
            login="4640854",
            service_type_code="INTFO",
            service_type_label="Fibra Optica",
            state="Habilitado",
        ),
        sesion=SesionPPPoE(username="4640854", online=False),
    )
    msg = mensaje_pre_triaje_acceso(estado, abonado=_abo(), es_ftth=True)
    assert msg
    low = msg.lower()
    assert "toda la casa" not in low
    assert "luces" in low or "ont" in low or "desenchuf" in low
    assert "zona" not in low


def test_radius_caido_pregunta_como_mesa():
    estado = EstadoConexionPPPoE(
        servicio=ServicioConectividad(
            login="4640854",
            service_type_code="INTFO",
            service_type_label="Fibra Optica",
            state="Habilitado",
        ),
        error="radius api no configurada",
    )
    msg = mensaje_pre_triaje_acceso(estado, abonado=_abo(), es_ftth=True)
    assert msg
    low = msg.lower()
    assert "padrón" not in low and "padron" not in low
    assert "radius" not in low
    assert "luces" in low or "ont" in low or "desenchuf" in low


def test_onu_offline_lo_dice_antes_del_cuestionario():
    estado = _ftth_online()
    onu = EstadoOnuBcm(
        numero_cliente="12345",
        encontrado=True,
        online=False,
        rx_dbm=-21.0,
        calidad_optica="buena",
    )
    msg = mensaje_pre_triaje_acceso(
        estado, abonado=_abo(), onu=onu, es_ftth=True
    )
    assert msg
    assert "no está registrada" in msg.lower() or "central" in msg.lower()
    assert "181.41.1.20" not in msg
    # No contradecir con barra de potencia "zona verde" si la ONT está offline
    assert "Potencia de tu ONT" not in msg
    assert "-21" not in msg


def test_sin_sesion_con_rx_stale_no_pega_barra_verde_sobre_luces(monkeypatch):
    """Caso IBOT: sin sesión + RX en BCM no debe decir potencia buena y preguntar luces."""
    from app.services import canal_pppoe as cp
    from app.services import conexion_bcm as cb
    from app.services import conexion_pppoe as cpp
    from app.services import conexion_uisp as cu

    estado = EstadoConexionPPPoE(
        servicio=ServicioConectividad(
            login="4640854",
            service_type_code="INTFO",
            service_type_label="Fibra Optica",
            state="Habilitado",
            service_on=True,
        ),
        sesion=SesionPPPoE(username="4640854", online=False),
    )
    # RX presente pero ONU sin online claro → no enlace_ok
    onu = EstadoOnuBcm(
        numero_cliente="71514953",
        encontrado=True,
        online=None,
        rx_dbm=-21.0,
        calidad_optica="buena",
    )
    monkeypatch.setattr(cpp, "consultar_conexion_pppoe", lambda **kw: estado)
    monkeypatch.setattr(cu, "resolve_uisp_client", lambda db=None: None)
    monkeypatch.setattr(cb, "resolve_bcm_client", lambda db=None: object())
    monkeypatch.setattr(cb, "consultar_onu_bcm", lambda *a, **k: onu)
    monkeypatch.setattr(cb, "consultar_onu_bcm_mejor_esfuerzo", lambda *a, **k: onu)

    msg = cp._talvez_mensaje_pppoe(MagicMock(), _abo(), {}, "internet")
    assert msg
    low = msg.lower()
    assert "luces" in low or "desenchuf" in low
    assert "Potencia de tu ONT" not in msg
    assert "zona verde" not in low


def test_sin_sesion_con_onu_ok_demuestra_potencia_no_pregunta_luces():
    estado = EstadoConexionPPPoE(
        servicio=ServicioConectividad(
            login="4640854",
            service_type_code="INTFO",
            service_type_label="Fibra Optica",
            state="Habilitado",
        ),
        sesion=SesionPPPoE(username="4640854", online=False),
    )
    onu = EstadoOnuBcm(
        numero_cliente="12345",
        encontrado=True,
        online=True,
        rx_dbm=-21.0,
        calidad_optica="buena",
    )
    msg = mensaje_pre_triaje_acceso(
        estado, abonado=_abo(), onu=onu, es_ftth=True
    )
    assert msg
    low = msg.lower()
    assert "potencia" in low or "-21" in msg
    assert "no figura conectado" in low or "no figurás conectado" in low or "conectado" in low
    assert "¿las luces" not in low
    assert "prendidas" not in low
    assert "toda la casa" not in msg.lower()


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
            state="Habilitado",
        ),
        error="radius api no configurada",
    )
    monkeypatch.setattr(cpp, "consultar_conexion_pppoe", lambda **kw: estado)
    monkeypatch.setattr(cu, "resolve_uisp_client", lambda db=None: None)
    monkeypatch.setattr(cb, "resolve_bcm_client", lambda db=None: None)

    msg = cp._talvez_mensaje_pppoe(MagicMock(), _abo(), {}, "internet")
    assert msg
    assert "padrón" not in msg.lower() and "padron" not in msg.lower()
    assert "luces" in msg.lower() or "ont" in msg.lower() or "wifi" in msg.lower()


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
    assert "billtrack" not in low and "uisp" not in low
    assert "enlazada" in low
    assert "poe" in low or "inyecto" in low
    assert "baja" not in low or "no es una baja" in low
    assert "reactiv" not in low
    assert "pago" not in low
    assert "15mb" not in low


def test_baja_real_es_comercial_no_wifi():
    estado = EstadoConexionPPPoE(
        servicio=ServicioConectividad(
            login="viejo",
            state="Baja",
            product="10MB",
            service_on=False,
        ),
        sesion=None,
    )
    msg = mensaje_pre_triaje_acceso(estado, abonado=_abo(estado="baja"))
    assert msg
    low = msg.lower()
    assert "baja" in low
    assert "ov.batan" in low or "pagar" in low
    assert "poe" not in low
    assert "wifi" not in low


def test_baja_no_consulta_uisp_ni_bcm(monkeypatch):
    from app.services import canal_pppoe as cp
    from app.services import conexion_bcm as cb
    from app.services import conexion_pppoe as cpp
    from app.services import conexion_uisp as cu

    estado = EstadoConexionPPPoE(
        servicio=ServicioConectividad(
            login="viejo",
            state="Baja",
            service_on=False,
            service_type_code="INTBA",
        )
    )
    monkeypatch.setattr(cpp, "consultar_conexion_pppoe", lambda **kw: estado)

    def no_uisp(*_a, **_k):
        raise AssertionError("baja: no abrir UISP")

    def no_bcm(*_a, **_k):
        raise AssertionError("baja: no abrir BCM")

    monkeypatch.setattr(cu, "resolve_uisp_client", no_uisp)
    monkeypatch.setattr(cb, "resolve_bcm_client", no_bcm)
    msg = cp._talvez_mensaje_pppoe(MagicMock(), _abo(estado="baja"), {}, "internet")
    assert msg
    assert "baja" in msg.lower()
    assert "ov.batan" in msg.lower() or "pagar" in msg.lower()
