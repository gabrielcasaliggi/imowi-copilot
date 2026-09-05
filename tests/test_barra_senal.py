"""Barrita didáctica de potencia ONU / señal antena en mensajes N1."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.bcm.contract import EstadoOnuBcm
from app.radius.contract import EstadoConexionPPPoE, ServicioConectividad, SesionPPPoE
from app.services.barra_senal import (
    anexar_antes_de_preguntas,
    bloque_potencia_onu,
    bloque_senal_antena,
    color_optica_didactica,
    color_radio_didactica,
)
from app.services.conexion_bcm import mensaje_abonado_bcm
from app.services.conexion_uisp import mensaje_abonado_uisp
from app.uisp.contract import EstadoCpeUisp


def test_colores_optica_tr069():
    assert color_optica_didactica(-18.0) == "green"
    assert color_optica_didactica(-16.0) == "green"
    assert color_optica_didactica(-24.0) == "green"
    assert color_optica_didactica(-15.0) == "orange"
    assert color_optica_didactica(-25.0) == "orange"
    assert color_optica_didactica(-12.0) == "red"
    assert color_optica_didactica(-27.0) == "red"
    assert color_optica_didactica(-8.0) == "red"


def test_colores_radio():
    assert color_radio_didactica(-55.0) == "green"
    assert color_radio_didactica(-70.0) == "orange"
    assert color_radio_didactica(-80.0) == "red"


def test_bloque_potencia_incluye_valor_y_barra():
    txt = bloque_potencia_onu(-18.0)
    assert "📊" in txt
    assert "-18.0 dBm" in txt
    assert "zona verde" in txt
    assert "🟢" in txt
    assert "🟥" in txt and "🟩" in txt
    assert "floja" in txt.lower() and "fuerte" in txt.lower()
    assert "🔵" not in txt
    assert bloque_potencia_onu(None) == ""


def test_bloque_potencia_regular_y_mala():
    regular = bloque_potencia_onu(-25.5)
    assert "zona naranja" in regular
    assert "regular" in regular
    assert "🟠" in regular

    floja = bloque_potencia_onu(-29.0)
    assert "zona roja" in floja
    assert "muy floja" in floja
    assert "🔴" in floja

    saturada = bloque_potencia_onu(-10.0)
    assert "saturada" in saturada
    assert "🔴" in saturada


def test_bloque_senal_antena():
    txt = bloque_senal_antena(-55.0)
    assert "📊" in txt
    assert "-55 dBm" in txt
    assert "zona verde" in txt
    assert "🟢" in txt
    assert bloque_senal_antena(None) == ""

    regular = bloque_senal_antena(-70.0)
    assert "zona naranja" in regular
    assert "🟠" in regular

    mala = bloque_senal_antena(-82.0)
    assert "zona roja" in mala
    assert "🔴" in mala


def test_anexar_antes_de_preguntas():
    msg = "La línea está bien. ¿Probaste con cable?"
    out = anexar_antes_de_preguntas(msg, "Potencia: -18 dBm")
    assert out.index("Potencia") < out.index("¿")
    assert anexar_antes_de_preguntas("sin pregunta", "extra").endswith("extra")
    assert anexar_antes_de_preguntas("hola", "") == "hola"


def test_mensaje_bcm_enlace_ok_lleva_barra():
    ok = EstadoOnuBcm(
        numero_cliente="x", encontrado=True, online=True, rx_dbm=-18.0, calidad_optica="buena"
    )
    msg = mensaje_abonado_bcm(ok, es_ftth=True)
    assert msg
    assert "Potencia de tu ONT" in msg
    assert "-18.0 dBm" in msg
    assert "se ve bien" in msg
    assert msg.index("Potencia") < msg.index("¿")


def test_mensaje_bcm_regular_no_dice_bien():
    regular = EstadoOnuBcm(
        numero_cliente="x", encontrado=True, online=True, rx_dbm=-25.5, calidad_optica="aceptable"
    )
    msg = mensaje_abonado_bcm(regular, es_ftth=True)
    assert msg
    assert "regular" in msg
    assert "🟠" in msg
    assert "se ve bien" not in msg


def test_mensaje_bcm_potencia_mala_lleva_barra():
    mala = EstadoOnuBcm(
        numero_cliente="x", encontrado=True, online=True, rx_dbm=-29.0, calidad_optica="mala"
    )
    msg = mensaje_abonado_bcm(mala, es_ftth=True)
    assert msg
    assert "baja" in msg.lower()
    assert "-29.0 dBm" in msg
    assert "zona roja" in msg
    assert "🔴" in msg


def test_mensaje_uisp_enlace_ok_lleva_barra():
    ok = EstadoCpeUisp(
        login="x", encontrado=True, online=True, signal_dbm=-55, calidad_senal="buena"
    )
    msg = mensaje_abonado_uisp(ok, es_radio=True)
    assert msg
    assert "Señal de tu antena" in msg
    assert "-55 dBm" in msg
    assert msg.index("Señal") < msg.index("¿")


def test_canal_radius_ok_anexa_potencia_onu(monkeypatch):
    from app.services import canal_pppoe as cp
    from app.services import conexion_bcm as cb
    from app.services import conexion_pppoe as cpp
    from app.services import conexion_uisp as cu

    estado = EstadoConexionPPPoE(
        servicio=ServicioConectividad(
            login="4640854",
            service_type_label="Fibra Optica",
            service_type_code="INTFO",
        ),
        sesion=SesionPPPoE(
            username="4640854",
            online=True,
            public_ip="181.41.252.68",
            uptime="19d4h",
        ),
    )
    onu = EstadoOnuBcm(
        numero_cliente="12345",
        encontrado=True,
        online=True,
        rx_dbm=-18.0,
        calidad_optica="buena",
    )
    monkeypatch.setattr(cpp, "consultar_conexion_pppoe", lambda **kw: estado)
    monkeypatch.setattr(cu, "resolve_uisp_client", lambda db=None: None)
    monkeypatch.setattr(cb, "resolve_bcm_client", lambda db=None: object())
    monkeypatch.setattr(cb, "consultar_onu_bcm", lambda *a, **k: onu)

    abonado = SimpleNamespace(
        dni="30111222",
        client_number="12345",
        servicio="internet",
        estado="activo",
        deuda_monto=None,
    )
    ctx: dict = {}
    msg = cp._talvez_mensaje_pppoe(MagicMock(), abonado, ctx, "internet")
    assert msg
    assert "181.41.252.68" in msg
    assert "activa" in msg.lower()
    assert "Potencia de tu ONT" in msg
    assert "-18.0 dBm" in msg
    assert "zona verde" in msg
    assert msg.index("Potencia") < msg.index("¿")
    assert ctx.get("pppoe_rama") == "wifi_lan"


def test_canal_potencia_mala_gana_sobre_radius(monkeypatch):
    from app.services import canal_pppoe as cp
    from app.services import conexion_bcm as cb
    from app.services import conexion_pppoe as cpp
    from app.services import conexion_uisp as cu

    estado = EstadoConexionPPPoE(
        servicio=ServicioConectividad(
            login="4640854",
            service_type_label="Fibra Optica",
            service_type_code="INTFO",
        ),
        sesion=SesionPPPoE(
            username="4640854",
            online=True,
            public_ip="1.2.3.4",
            uptime="2d",
        ),
    )
    onu = EstadoOnuBcm(
        numero_cliente="12345",
        encontrado=True,
        online=True,
        rx_dbm=-29.0,
        calidad_optica="mala",
    )
    monkeypatch.setattr(cpp, "consultar_conexion_pppoe", lambda **kw: estado)
    monkeypatch.setattr(cu, "resolve_uisp_client", lambda db=None: None)
    monkeypatch.setattr(cb, "resolve_bcm_client", lambda db=None: object())
    monkeypatch.setattr(cb, "consultar_onu_bcm", lambda *a, **k: onu)

    abonado = SimpleNamespace(
        dni="30111222",
        client_number="12345",
        servicio="internet",
        estado="activo",
        deuda_monto=None,
    )
    msg = cp._talvez_mensaje_pppoe(MagicMock(), abonado, {}, "internet")
    assert msg
    assert "potencia óptica" in msg.lower()
    assert "baja" in msg.lower()
    assert "-29.0 dBm" in msg
    assert "1.2.3.4" not in msg


def test_canal_radius_ok_anexa_senal_antena(monkeypatch):
    from app.services import canal_pppoe as cp
    from app.services import conexion_bcm as cb
    from app.services import conexion_pppoe as cpp
    from app.services import conexion_uisp as cu

    estado = EstadoConexionPPPoE(
        servicio=ServicioConectividad(
            login="4640854",
            service_type_label="Internet Inalambrico",
            service_type_code="INTBA",
        ),
        sesion=SesionPPPoE(
            username="4640854",
            online=True,
            public_ip="10.1.2.3",
            uptime="3d",
        ),
    )
    cpe = EstadoCpeUisp(
        login="4640854",
        encontrado=True,
        online=True,
        signal_dbm=-55,
        calidad_senal="buena",
    )
    monkeypatch.setattr(cpp, "consultar_conexion_pppoe", lambda **kw: estado)
    monkeypatch.setattr(cu, "resolve_uisp_client", lambda db=None: object())
    monkeypatch.setattr(cu, "consultar_cpe_uisp", lambda *a, **k: cpe)
    monkeypatch.setattr(cb, "resolve_bcm_client", lambda db=None: None)

    abonado = SimpleNamespace(
        dni="30111222",
        client_number="99",
        servicio="internet",
        estado="activo",
        deuda_monto=None,
    )
    ctx: dict = {}
    msg = cp._talvez_mensaje_pppoe(MagicMock(), abonado, ctx, "internet")
    assert msg
    assert "10.1.2.3" in msg
    assert "Señal de tu antena" in msg
    assert "-55 dBm" in msg
    assert msg.index("Señal") < msg.index("¿")


def test_consulta_mi_senal_es_buena_responde_potencia_onu(monkeypatch):
    from app.services.canal_abonado import _responder_consulta_potencia_onu

    onu = EstadoOnuBcm(
        numero_cliente="12345",
        encontrado=True,
        online=True,
        rx_dbm=-18.0,
        calidad_optica="buena",
    )
    sent: list[str] = []
    abo = SimpleNamespace(dni="30111222", client_number="12345")
    conv = SimpleNamespace(id="c1", estado="bot")
    ctx: dict = {"tecnologia_acceso": "internet_ftth", "diag_turnos": 1}

    monkeypatch.setattr(
        "app.services.conexion_bcm.resolve_bcm_client",
        lambda _db=None: object(),
    )
    monkeypatch.setattr(
        "app.services.conexion_bcm.consultar_onu_bcm",
        lambda *_a, **_k: onu,
    )
    monkeypatch.setattr(
        "app.services.billtrack.lookup_servicios_conectividad_por_dni",
        lambda **_k: [],
    )

    def _captura(_db, _org, _conv, resp, **_k):
        sent.append(resp)

    monkeypatch.setattr("app.services.canal_abonado._enviar_respuesta", _captura)
    monkeypatch.setattr(
        "app.services.canal_abonado.crepo.set_contexto",
        lambda _c, new_ctx: ctx.update(new_ctx),
    )

    out = _responder_consulta_potencia_onu(
        MagicMock(),
        "org",
        conv,  # type: ignore[arg-type]
        abo,  # type: ignore[arg-type]
        "mi señal es buena?",
        canal="whatsapp",
        ctx=ctx,
        intencion="internet",
    )
    assert out is not None
    assert sent
    assert "📊" in sent[0]
    assert "-18.0 dBm" in sent[0]
    assert "zona verde" in sent[0]
    wifi = _responder_consulta_potencia_onu(
        MagicMock(),
        "org",
        conv,  # type: ignore[arg-type]
        abo,  # type: ignore[arg-type]
        "tengo todas las rayitas del wifi",
        canal="whatsapp",
        ctx=ctx,
        intencion="internet",
    )
    assert wifi is None


def test_confirmacion_eso_es_bueno_no_escala(monkeypatch):
    from app.domain.flujos_abonado import cliente_pide_confirmar_lectura_enlace
    from app.services.canal_abonado import _responder_confirmacion_lectura_acceso

    assert cliente_pide_confirmar_lectura_enlace("bien eso es bueno?") is True
    assert cliente_pide_confirmar_lectura_enlace("tengo todas las rayitas del wifi") is False
    assert cliente_pide_confirmar_lectura_enlace("pero me dijiste que la señal esta bien") is True

    sent: list[str] = []
    conv = SimpleNamespace(id="c1", estado="bot")
    ctx = {"bcm_rx_dbm": "-21", "bcm_calidad_optica": "buena", "diag_turnos": 3}

    monkeypatch.setattr(
        "app.services.canal_abonado._enviar_respuesta",
        lambda *_a, **_k: sent.append(_a[3]),
    )
    monkeypatch.setattr(
        "app.services.canal_abonado.crepo.set_contexto",
        lambda _c, new_ctx: ctx.update(new_ctx),
    )
    out = _responder_confirmacion_lectura_acceso(
        MagicMock(),
        "org",
        conv,  # type: ignore[arg-type]
        "bien eso es bueno?",
        canal="whatsapp",
        ctx=ctx,
        intencion="internet_ftth",
    )
    assert out is not None
    assert sent and "ticket" not in sent[0].lower()
    assert "agente" not in sent[0].lower()
    assert "Sí:" in sent[0]
    assert "-21.0 dBm" in sent[0]
    assert "zona verde" in sent[0]
    assert "Wi‑Fi" in sent[0]


def test_confirmacion_me_dijiste_no_repite_barra(monkeypatch):
    from app.services.canal_abonado import _responder_confirmacion_lectura_acceso

    sent: list[str] = []
    conv = SimpleNamespace(id="c1", estado="bot")
    ctx = {"bcm_rx_dbm": "-21", "bcm_calidad_optica": "buena", "diag_turnos": 3}

    monkeypatch.setattr(
        "app.services.canal_abonado._enviar_respuesta",
        lambda *_a, **_k: sent.append(_a[3]),
    )
    monkeypatch.setattr(
        "app.services.canal_abonado.crepo.set_contexto",
        lambda _c, new_ctx: ctx.update(new_ctx),
    )
    out = _responder_confirmacion_lectura_acceso(
        MagicMock(),
        "org",
        conv,  # type: ignore[arg-type]
        "pero me dijiste que la señal esta bien",
        canal="whatsapp",
        ctx=ctx,
        intencion="internet_ftth",
    )
    assert out is not None
    assert ctx.get("wifi_rama_activada") is True
    assert sent
    low = sent[0].lower()
    assert "📊" not in sent[0]
    assert "no hace falta tocar la ont" in low
    assert "todos los equipos" in low
    assert "ticket" not in low
