"""Tests de variantes conversacionales — operadores técnicos e informales."""

import pytest

from app.domain.flujos_operativos import evaluar_flujo
from app.services.interprete_conversacional import (
    aplicar_interpretacion,
    detectar_intencion_normalizada,
    extraer_hechos_normalizados,
    necesita_interpretacion_ia,
    perfil_operador,
)
from app.services.intenciones_seguimiento import detectar_intencion_seguimiento, extraer_hechos_conversacion


@pytest.mark.parametrize(
    "mensaje,tipo_esperado",
    [
        ("creaste el ticket?", "estado_ticket"),
        ("lo cargaste?", "estado_ticket"),
        ("quedó reclamo?", "estado_ticket"),
        ("pasame el número", "estado_ticket"),
        ("esto va a NOC?", "estado_ticket"),
        ("gracias", "agradecimiento"),
        ("no es así, el usuario sigue con problemas", "correccion"),
        ("te pregunté si creaste el ticket", "estado_ticket"),
        ("hice lo que me dijiste y sigue igual", "persistencia"),
        ("APN ok, roaming habilitado", "confirmacion_paso"),
    ],
)
def test_intencion_variantes(mensaje, tipo_esperado):
    norm = detectar_intencion_normalizada(mensaje, tiene_ticket=True, hechos={})
    assert norm["tipo"] == tipo_esperado


def test_hechos_tecnico_llamada_datos_no():
    hechos = extraer_hechos_normalizados("APN ok, roaming habilitado, llamada sale pero datos no")
    assert hechos.get("apn_configurado") is True
    assert hechos.get("roaming_verificado") is True
    assert hechos.get("llamadas_ok") is True
    assert hechos.get("datos_ok") is False


def test_hechos_informal_afuera_internet():
    hechos = extraer_hechos_normalizados("el cliente está afuera y no le anda internet")
    assert hechos.get("alcance_confirmado") is True
    assert hechos.get("datos_ok") is False


def test_hechos_whatsapp_no_carga():
    hechos = extraer_hechos_normalizados("puede llamar pero whatsapp no carga")
    assert hechos.get("llamadas_ok") is True
    assert hechos.get("datos_ok") is False


def test_hechos_no_funciona_no_marca_ok():
    hechos = extraer_hechos_normalizados("sigue sin andar, no funciona")
    assert hechos.get("datos_ok") is False
    assert hechos.get("resuelto") is not True


def test_reclamo_vago_uruguay_flujo_roaming():
    hist = [
        {"rol": "usuario", "contenido": "tengo un problema con la linea 2235402692"},
        {"rol": "asistente", "contenido": "Confirmar zona, alcance del problema y si afecta señal, datos o solo llamadas."},
        {"rol": "usuario", "contenido": "está en uruguay y no le anda internet"},
    ]
    hechos = extraer_hechos_conversacion(hist)
    flujo = evaluar_flujo(hechos, "uruguay no le anda internet linea 2235402692")
    assert hechos.get("categoria_flujo") == "roaming"
    assert hechos.get("alcance_confirmado") is True
    assert flujo["paso_id"] == "roaming_datos_moviles"


def test_perfil_operador_tecnico_vs_informal():
    hist_tec = [{"rol": "usuario", "contenido": "APN ok, roaming habilitado en JSC"}]
    hist_inf = [{"rol": "usuario", "contenido": "el cliente está afuera y no le anda internet"}]
    assert perfil_operador(hist_tec) == "tecnico"
    assert perfil_operador(hist_inf) == "informal"


def test_necesita_ia_mensaje_ambiguo():
    msg = "bueno no se como explicarlo todavía"
    norm = detectar_intencion_normalizada(msg, tiene_ticket=False, hechos={})
    assert norm["confianza"] < 0.7
    assert necesita_interpretacion_ia(msg, norm, {}) is True


def test_necesita_ia_no_en_confirmacion_corta():
    msg = "ok"
    norm = detectar_intencion_normalizada(msg, tiene_ticket=True, hechos={})
    assert necesita_interpretacion_ia(msg, norm, {}) is False


def test_aplicar_interpretacion_ia_fusiona_hechos():
    hechos = {"categoria_flujo": "roaming"}
    intencion = {"tipo": "continuar", "confianza": 0.4}
    interp = {
        "intencion": "informe_prueba",
        "hechos": {"llamadas_ok": True, "datos_ok": False},
        "confianza": 0.82,
        "fuente": "ia",
    }
    h2, i2 = aplicar_interpretacion(hechos, intencion, interp)
    assert h2["llamadas_ok"] is True
    assert h2["datos_ok"] is False
    assert i2["tipo"] == "informe_prueba"


def test_detectar_intencion_seguimiento_con_hechos():
    hist = [
        {"rol": "usuario", "contenido": "Cliente sin datos en Brasil"},
        {"rol": "usuario", "contenido": "lo cargaste?"},
    ]
    hechos = extraer_hechos_conversacion(hist)
    intencion = detectar_intencion_seguimiento(
        hist,
        caso={"ticket_id": "JSC-1"},
        ticket={"id": "JSC-1"},
        hechos=hechos,
    )
    assert intencion["tipo"] == "estado_ticket"
