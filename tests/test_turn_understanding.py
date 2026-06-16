"""Tests del modelo híbrido: intención + contexto del bot, no frases literales."""

import pytest

from app.domain.turn_understanding import IntencionTurno, PreguntaPendiente
from app.services.decision_engine import evaluar_crear_ticket
from app.services.turn_understanding import (
    fusionar_hechos_turno,
    inferir_pregunta_pendiente,
    interpretar_turno_hibrido,
)


@pytest.mark.parametrize(
    "respuesta",
    [
        "si los problemas persisten",
        "sí, persisten",
        "confirmo que sigue igual",
        "si persiste",
        "los problemas persisten",
    ],
)
def test_contexto_persistencia_interpreta_variantes(respuesta):
    hist = [
        {"rol": "asistente", "contenido": "¿Confirmás que el problema persiste después de las verificaciones?"},
        {"rol": "usuario", "contenido": respuesta},
    ]
    u = interpretar_turno_hibrido(hist, hechos_prev={"categoria_flujo": "sms"})
    assert u.intencion == IntencionTurno.CONFIRMAR_PERSISTENCIA
    assert u.confianza >= 0.85
    assert u.hechos.persistencia_confirmada is True


def test_contexto_solicitud_ticket_no_requiere_frase_exacta():
    hist = [
        {"rol": "asistente", "contenido": "Escalar a carrier con remitente y horario."},
        {"rol": "usuario", "contenido": "podes realizar el ticket?"},
    ]
    u = interpretar_turno_hibrido(hist, hechos_prev={"categoria_flujo": "sms", "linea_jsc_verificada": True})
    assert u.intencion == IntencionTurno.SOLICITAR_TICKET
    assert u.hechos.solicita_ticket is True


def test_inferir_pregunta_pendiente_desde_ultimo_bot():
    bot = "Para crear un ticket, necesito confirmar que el problema persiste después de las verificaciones."
    assert inferir_pregunta_pendiente(bot) == PreguntaPendiente.CONFIRMAR_PERSISTENCIA


def test_aportar_datos_sms_en_paso_carrier():
    hist = [
        {
            "rol": "asistente",
            "contenido": "Escalar a carrier con remitente Netflix y horario del incidente.",
        },
        {"rol": "usuario", "contenido": "remitente Apple, hoy 14hs"},
    ]
    u = interpretar_turno_hibrido(
        hist,
        hechos_prev={"categoria_flujo": "sms", "linea_jsc_verificada": True},
        flujo_paso_id="sms_ticket_carrier",
    )
    assert u.intencion in (IntencionTurno.APORTAR_DATO, IntencionTurno.CONTINUAR)
    hechos = fusionar_hechos_turno({"categoria_flujo": "sms", "linea_jsc_verificada": True}, u)
    assert hechos.get("sms_remitente_ejemplo") or hechos.get("sms_horario_incidente")


def test_invariante_sms_crea_ticket_por_persistencia():
    hist = [
        {"rol": "usuario", "contenido": "linea 2233567656 sms apple no llegan"},
        {"rol": "asistente", "contenido": "Confirmar persistencia del problema."},
        {"rol": "usuario", "contenido": "si los problemas persisten"},
    ]
    hechos = {"categoria_flujo": "sms", "linea_jsc_verificada": True, "resuelto": False}
    u = interpretar_turno_hibrido(hist, hechos_prev=hechos, flujo_paso_id="sms_ticket_carrier")
    hechos = fusionar_hechos_turno(hechos, u)
    flujo = {"categoria": "sms", "paso_id": "sms_ticket_carrier"}
    decision = evaluar_crear_ticket(
        historial=hist,
        hechos=hechos,
        flujo_operativo=flujo,
        understanding=u,
    )
    assert decision is not None
    assert decision.crear_ticket is True
    assert decision.destino == "carrier"
    assert decision.auto_confirmado is True
