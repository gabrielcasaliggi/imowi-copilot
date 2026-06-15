"""Tests de intenciones de seguimiento conversacional."""

import pytest

from app.services.intenciones_seguimiento import (
    construir_resumen,
    detectar_intencion_seguimiento,
    extraer_hechos_conversacion,
    siguiente_paso_sugerido,
)


def test_detecta_novedad_ticket():
    hist = [
        {"rol": "usuario", "contenido": "problema señal línea 2235402698"},
        {"rol": "asistente", "contenido": "ticket creado"},
        {"rol": "usuario", "contenido": "tenes alguna novedad del ticket?"},
    ]
    r = detectar_intencion_seguimiento(hist, caso={"ticket_id": "JSC-1005"})
    assert r["tipo"] == "novedad_ticket"


def test_detecta_pregunta_recomendacion_no_hecho():
    hist = [{"rol": "usuario", "contenido": "Entonces lo que me recomendas es que le cambiemos la sim al cliente"}]
    r = detectar_intencion_seguimiento(hist, caso={"ticket_id": "JSC-1005"})
    assert r["tipo"] == "pregunta_recomendacion"


def test_sin_solucion_no_es_resuelto():
    hechos = extraer_hechos_conversacion(
        [{"rol": "usuario", "contenido": "lo hicimos sin solución"}]
    )
    assert hechos.get("resuelto") is False


def test_resumen_incluye_pasos():
    hechos = extraer_hechos_conversacion(
        [
            {"rol": "usuario", "contenido": "cambiamos la sim"},
            {"rol": "usuario", "contenido": "llamadas si pero no puede navegar"},
            {"rol": "usuario", "contenido": "configuramos apn y funciono"},
        ]
    )
    texto = construir_resumen(hechos, {"linea": "2235402698", "sintoma": "sin señal"}, {"id": "JSC-1005", "estado": "Abierto", "nivel": "N2"})
    assert "2235402698" in texto
    assert "JSC-1005" in texto
    assert "SIM" in texto or "APN" in texto


def test_datos_no_recomienda_sim_como_primer_paso():
    paso = siguiente_paso_sugerido({}, "no puede usar datos para navegar")
    assert "SIM" not in paso
    assert "datos móviles" in paso


def test_apn_antes_que_sim_para_datos():
    paso = siguiente_paso_sugerido(
        {"datos_moviles_activos": True, "datos_ok": False},
        "no puede navegar",
    )
    assert "APN" in paso
    assert "SIM" not in paso


def test_sim_solo_ultimo_descarte():
    paso = siguiente_paso_sugerido(
        {
            "datos_moviles_activos": True,
            "apn_configurado": True,
            "reinicio_o_modo_avion": True,
                "llamadas_ok": True,
            "datos_ok": False,
        },
        "no puede navegar",
    )
    assert "último descarte" in paso


def test_confirmacion_aplica_al_paso_anterior():
    hechos = extraer_hechos_conversacion(
        [
            {
                "rol": "asistente",
                "contenido": "Verificar que datos móviles e itinerancia de datos estén activos en el equipo.",
            },
            {"rol": "usuario", "contenido": "ya lo verificamos"},
        ]
    )
    assert hechos["datos_moviles_activos"] is True
    assert not hechos.get("roaming_verificado")


@pytest.mark.parametrize(
    "respuesta",
    ["verificado", "correcto", "eso esta bien", "ok"],
)
def test_confirmaciones_cortas_avanzan_paso(respuesta: str):
    hechos = extraer_hechos_conversacion(
        [
            {
                "rol": "asistente",
                "contenido": "Verificar que datos móviles e itinerancia de datos estén activos en el equipo.",
            },
            {"rol": "usuario", "contenido": respuesta},
        ]
    )
    assert hechos["datos_moviles_activos"] is True


def test_confirmacion_jsc_marca_roaming():
    hechos = extraer_hechos_conversacion(
        [
            {
                "rol": "asistente",
                "contenido": "Verificar en JSC que la línea tenga roaming internacional y datos roaming habilitados.",
            },
            {"rol": "usuario", "contenido": "verificado en jsc"},
        ]
    )
    assert hechos["roaming_verificado"] is True


def test_flujo_roaming_avanza_tras_confirmaciones():
    hist = [
        {"rol": "usuario", "contenido": "Cliente sin datos en Brasil, linea 2235482690, Samsung A22."},
        {
            "rol": "asistente",
            "contenido": "Verificar que datos móviles e itinerancia de datos estén activos en el equipo.",
        },
        {"rol": "usuario", "contenido": "verificado"},
    ]
    hechos = extraer_hechos_conversacion(hist)
    paso = siguiente_paso_sugerido(hechos, "Cliente sin datos en Brasil")
    assert paso is not None
    assert "APN" in paso


def test_replay_historial_sin_memoria_previa():
    hist = [
        {"rol": "usuario", "contenido": "Cliente sin datos en Brasil, linea 2235482690, Samsung A22."},
        {"rol": "asistente", "contenido": "Verificar que datos móviles e itinerancia de datos estén activos en el equipo."},
        {"rol": "usuario", "contenido": "verificado"},
        {"rol": "asistente", "contenido": 'Revisar el APN de datos para roaming (ej. "internet.coopbatan.ar") y probar navegación.'},
        {"rol": "usuario", "contenido": "ok"},
        {"rol": "asistente", "contenido": "Verificar en JSC que la línea tenga roaming internacional y datos roaming habilitados."},
        {"rol": "usuario", "contenido": "no estaba activado el servicio de roaming"},
    ]
    hechos = extraer_hechos_conversacion(hist, {})
    assert hechos.get("datos_moviles_activos")
    assert hechos.get("apn_configurado")
    assert hechos.get("roaming_verificado")
    assert hechos.get("roaming_jsc_inactivo")
    paso = siguiente_paso_sugerido(hechos, "Cliente sin datos en Brasil")
    assert paso is not None
    assert "Activar roaming" in paso


def test_porque_repetis_es_correccion():
    hist = [
        {"rol": "usuario", "contenido": "problema roaming"},
        {"rol": "asistente", "contenido": "Verificar en JSC que la línea tenga roaming internacional y datos roaming habilitados."},
        {"rol": "usuario", "contenido": "porque te repetis"},
    ]
    r = detectar_intencion_seguimiento(hist, caso={"ticket_id": "JSC-1006"})
    assert r["tipo"] == "correccion"


def test_roaming_no_deriva_a_dni_ni_datos_extra():
    hechos = {
        "datos_moviles_activos": True,
        "apn_configurado": True,
        "roaming_verificado": True,
        "reinicio_o_modo_avion": True,
        "llamadas_ok": False,
    }
    paso = siguiente_paso_sugerido(hechos, "sin datos en Brasil roaming")
    assert "DNI" not in paso
    assert "privado" not in paso
    assert "ticket" in paso


def test_roaming_sigue_orden_operativo():
    paso1 = siguiente_paso_sugerido({}, "sin datos en Brasil")
    assert "itinerancia" in paso1
    paso2 = siguiente_paso_sugerido({"datos_moviles_activos": True}, "sin datos en Brasil")
    assert "APN" in paso2
    paso3 = siguiente_paso_sugerido(
        {"datos_moviles_activos": True, "apn_configurado": True},
        "sin datos en Brasil",
    )
    assert "JSC" in paso3


def test_seguimiento_activo_siempre_responde():
    from app.domain.conversacion import EstadoConversacion
    from app.services.respuestas_conversacion import respuesta_por_estado

    hechos = {
        "datos_moviles_activos": True,
        "apn_configurado": True,
        "roaming_verificado": True,
        "reinicio_o_modo_avion": True,
        "llamadas_ok": False,
    }
    texto = respuesta_por_estado(
        EstadoConversacion.TICKET_CREADO,
        datos={"sintoma": "sin datos en Brasil", "hechos": hechos},
        clasificacion={"accion": "seguimiento_activo"},
        diagnostico={},
        ticket={"id": "JSC-1006", "estado": "Abierto"},
        hechos=hechos,
        intencion_seguimiento={"tipo": "seguimiento_activo"},
    )
    assert texto
    assert "DNI" not in texto
    assert "privado" not in texto.lower()
    assert "ticket" in texto.lower()


def test_extraer_datos_usa_primer_sintoma():
    from app.agents.triaje import extraer_datos

    hist = [
        {"rol": "usuario", "contenido": "Cliente sin datos en Brasil, linea 2235551234, Samsung A54."},
        {"rol": "asistente", "contenido": "Verificá itinerancia"},
        {"rol": "usuario", "contenido": "solo le pasa saliendo de argentina"},
    ]
    datos = extraer_datos(hist)
    assert "Brasil" in datos["sintoma"]
    assert "saliendo de argentina" not in datos["sintoma"]
