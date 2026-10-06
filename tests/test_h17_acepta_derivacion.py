"""H17 fix A: ``acepta_derivacion_clara`` no acepta negaciones, preguntas ni menciones de «ticket»/«agente» sin pedido."""

from __future__ import annotations

import pytest

from app.domain.flujos_abonado import acepta_derivacion_clara

NO_ACEPTA = [
    "no quiero ticket",
    "no me derives a un agente",
    "no necesito agente",
    "ya hablé con el agente y no resolvió",
    "el ticket sigue abierto",
    "ok, y el ticket anterior?",
    "me dijeron que abrían un ticket y nunca pasó",
    "no hace falta un agente",
    "sin agente por favor",
    "¿necesito un agente?",
    "me anda lento",
    "gracias, igual no quiero que me deriven",
]

ACEPTA = [
    "sí derivame",
    "quiero hablar con un agente",
    "pasame con un agente",
    "dale generá el ticket",
    "necesito un agente",
    "abrime un ticket",
    "comunicame con un operador",
    "sí",
    "dale",
    "ok",
    "sí, dale",
    "si por favor",
    "quiero que me deriven",
]


@pytest.mark.parametrize("texto", NO_ACEPTA)
def test_no_acepta_derivacion(texto):
    assert not acepta_derivacion_clara(texto)


@pytest.mark.parametrize("texto", ACEPTA)
def test_si_acepta_derivacion(texto):
    assert acepta_derivacion_clara(texto)
