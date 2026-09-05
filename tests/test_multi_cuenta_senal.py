"""Multi-cuenta BillTrack + consulta señal antena UISP."""

from __future__ import annotations

from types import SimpleNamespace

from app.domain.flujos_abonado import cliente_pregunta_senal_antena
from app.radius.contract import ServicioConectividad
from app.services import billtrack as bt
from app.services.conexion_uisp import mensaje_informe_senal_antena
from app.uisp.contract import EstadoCpeUisp


def _servicios_tupacireta() -> list[ServicioConectividad]:
    return [
        ServicioConectividad(
            login="lemuramatiBAI",
            service_type_code="INTBA",
            service_type_label="ACCESO INTERNET INALAMBRICO",
            product="Internet acceso Bai Hogar 10MB",
            locality="Paraje los Ortiz - BATAN",
            service_on=True,
        ),
        ServicioConectividad(
            login="tupaciretacuidaBAI",
            service_type_code="INTBA",
            service_type_label="ACCESO INTERNET INALAMBRICO",
            product="Internet acceso Bai Hogar 10MB",
            locality="RUTA 226 KM 16 CAMINO A LOS HORTIZ - MAR DEL PLATA",
            service_on=True,
        ),
        ServicioConectividad(
            login="tupaciretaBAI",
            service_type_code="INTBA",
            service_type_label="ACCESO INTERNET INALAMBRICO",
            product="Internet acceso Bai Hogar 15MB",
            locality="PARAJE LOS ORTIZ - BATAN",
            service_on=True,
        ),
    ]


def test_extraer_login_en_texto_multi_cuenta():
    svcs = _servicios_tupacireta()
    assert bt.extraer_login_en_texto("problemas con tupaciretacuidaBAI", svcs) == "tupaciretacuidaBAI"
    assert bt.extraer_login_en_texto("  tupaciretacuidaBAI ", svcs) == "tupaciretacuidaBAI"
    assert bt.extraer_login_en_texto("internet", svcs) == ""
    assert bt.extraer_login_en_texto("la de mar del plata", svcs) == "tupaciretacuidaBAI"
    assert bt.extraer_login_en_texto("los ortiz", svcs) == ""


def test_mensaje_seleccion_cuenta_con_domicilio():
    msg = bt.mensaje_seleccion_cuenta_internet(_servicios_tupacireta())
    assert "3 cuentas" in msg
    assert "tupaciretacuidaBAI" in msg
    assert "Mar Del Plata" in msg or "Mar del Plata" in msg
    assert "Paraje Los Ortiz" in msg or "Paraje los Ortiz" in msg
    assert "dirección" in msg.lower() or "direccion" in msg.lower()
    rep = bt.mensaje_seleccion_cuenta_internet(_servicios_tupacireta(), repregunta=True)
    assert "Cuál de estas cuentas" in rep


def test_mensaje_seleccion_cuenta():
    msg = bt.mensaje_seleccion_cuenta_internet(_servicios_tupacireta())
    assert "•" in msg
    svcs = [ServicioConectividad(login="soloBAI", service_type_code="INTBA", service_on=True)]
    assert bt.resolver_login_consulta("que señal tengo", svcs) == "soloBAI"


def test_cliente_pregunta_senal_typo_y_antena():
    from app.domain.flujos_abonado import cliente_pregunta_calidad_enlace

    assert cliente_pregunta_senal_antena("me podes de cir que señak tengo?") is True
    assert cliente_pregunta_senal_antena("pero que señal tengo en la antena?") is True
    assert cliente_pregunta_senal_antena("anda lento") is False
    assert cliente_pregunta_calidad_enlace("mi señal es buena?") is True
    assert cliente_pregunta_calidad_enlace("está bien la señal?") is True
    assert cliente_pregunta_calidad_enlace("tengo todas las rayitas del wifi") is False
    assert cliente_pregunta_calidad_enlace("la señal en la pieza es floja") is False
    assert cliente_pregunta_calidad_enlace("pero me dijiste que la señal esta bien") is False


def test_informe_senal_incluye_dbm():
    cpe = EstadoCpeUisp(
        login="tupaciretacuidaBAI",
        encontrado=True,
        online=True,
        signal_dbm=-58,
        calidad_senal="buena",
    )
    msg = mensaje_informe_senal_antena(cpe)
    assert "-58" in msg
    assert "excelente" in msg


def test_cliente_indica_multi_cuenta():
    from app.domain.flujos_abonado import cliente_indica_multi_cuenta_internet

    assert cliente_indica_multi_cuenta_internet(
        "el problema lo tengo con una de mis cuentas, porque son varias"
    )
    assert not cliente_indica_multi_cuenta_internet("lentitud")


def test_responder_seleccion_cuenta_internet(monkeypatch):
    from unittest.mock import MagicMock

    from app.services.canal_abonado import _responder_seleccion_cuenta_internet

    abo = SimpleNamespace(dni="30111222", client_number="2677")
    conv = SimpleNamespace(id="c1", estado="bot", canal="whatsapp", telefono="5491", wa_id="5491")
    ctx: dict = {}
    db = MagicMock()
    sent: list[str] = []

    monkeypatch.setattr(
        "app.services.canal_abonado._servicios_conectividad_abonado",
        lambda _db, _abo: _servicios_tupacireta(),
    )
    monkeypatch.setattr(
        "app.services.canal_abonado._enviar_respuesta",
        lambda _db, _org, _conv, resp, **_k: sent.append(resp),
    )
    monkeypatch.setattr(
        "app.services.canal_abonado.crepo.set_contexto",
        lambda _c, new_ctx: ctx.update(new_ctx),
    )

    out = _responder_seleccion_cuenta_internet(
        db,
        "org",
        conv,
        abo,
        "el problema lo tengo con una de mis cuentas, porque son varias",
        canal="whatsapp",
        ctx=ctx,
        intencion="internet",
    )
    assert out is not None
    assert out.get("seleccion_cuenta_internet") is True
    assert "tupaciretacuidaBAI" in sent[0]
    assert "Mar Del Plata" in sent[0] or "Mar del Plata" in sent[0]
    assert ctx.get("multi_cuenta_pendiente") is True

    out2 = _responder_seleccion_cuenta_internet(
        db,
        "org",
        conv,
        abo,
        "lentitud",
        canal="whatsapp",
        ctx=ctx,
        intencion="internet_lento",
    )
    assert out2 is not None
    assert "Cuál de estas cuentas" in sent[1]


def test_responder_consulta_senal_antena_mock_uisp(monkeypatch):
    from unittest.mock import MagicMock

    from app.services.canal_abonado import _responder_consulta_senal_antena

    abo = SimpleNamespace(dni="30111222", client_number="2677")
    conv = SimpleNamespace(id="c1", estado="bot", canal="whatsapp", telefono="5491", wa_id="5491")
    ctx: dict = {"login_seleccionado": "tupaciretacuidaBAI", "diag_turnos": 2}
    db = MagicMock()
    sent: list[str] = []

    svcs = _servicios_tupacireta()

    monkeypatch.setattr(
        "app.services.canal_abonado._servicios_conectividad_abonado",
        lambda _db, _abo: svcs,
    )
    monkeypatch.setattr(
        "app.services.conexion_uisp.resolve_uisp_client",
        lambda _db=None: object(),
    )
    cpe = EstadoCpeUisp(
        login="tupaciretacuidaBAI",
        encontrado=True,
        online=True,
        signal_dbm=-58,
        calidad_senal="buena",
    )
    monkeypatch.setattr(
        "app.services.conexion_uisp.sincronizar_servicio_login_en_ctx",
        lambda _db, _abo, _ctx, login: cpe,
    )
    monkeypatch.setattr(
        "app.services.canal_abonado._enviar_respuesta",
        lambda _db, _org, _conv, resp, **_k: sent.append(resp),
    )
    monkeypatch.setattr(
        "app.services.canal_abonado.crepo.set_contexto",
        lambda _c, new_ctx: ctx.update(new_ctx),
    )

    out = _responder_consulta_senal_antena(
        db,
        "org",
        conv,
        abo,
        "pero que señal tengo en la antena?",
        canal="whatsapp",
        ctx=ctx,
        intencion="internet_lento",
    )
    assert out is not None
    assert out["modo"] == "bot"
    assert sent
    assert "tupaciretacuidaBAI" in sent[0]
    assert "-58" in sent[0]
    assert "ticket" not in sent[0].lower()
