"""Tests de contexto SMS en tickets y respuesta proactiva."""

import pytest

from app.services.ticket_contexto import (
    enriquecer_clasificacion_con_hechos,
    lineas_contexto_sms,
    respuesta_ticket_creado_proactivo,
)


def test_lineas_contexto_sms():
    hechos = {
        "sms_remitente_ejemplo": "Apple, Netflix",
        "sms_horario_incidente": "hoy 14hs",
    }
    lineas = lineas_contexto_sms(hechos)
    assert any("Apple" in l for l in lineas)
    assert any("14hs" in l for l in lineas)


def test_enriquecer_clasificacion_con_hechos_sms():
    clasif = {"accion": "crear_ticket_n2", "evidencia": []}
    datos = {
        "hechos": {
            "sms_remitente_ejemplo": "remitente Apple",
            "pasos_realizados": ["JSC verificado", "Alcance SMS"],
        }
    }
    out = enriquecer_clasificacion_con_hechos(clasif, datos)
    assert any("Apple" in e for e in out["evidencia"])
    assert "JSC verificado" in out["acciones_n1_realizadas"]


def test_respuesta_proactiva_incluye_ticket_y_sms():
    msg = respuesta_ticket_creado_proactivo(
        {"id": "JSC-1005", "linea": "2234567890", "nivel": "N2", "destino": "carrier", "estado": "Abierto"},
        {
            "linea": "2234567890",
            "sintoma": "no recibe sms de confirmacion apple",
            "hechos": {
                "categoria_flujo": "sms",
                "sms_remitente_ejemplo": "Apple",
                "sms_horario_incidente": "hoy 10hs",
            },
        },
    )
    assert "JSC-1005" in msg
    assert "2234567890" in msg
    assert "Apple" in msg
    assert "carrier" in msg.lower()
