"""Tanda 3 F0: «no necesito un agente» / «¿necesito hablar con un agente?» no son pedidos de agente."""

from __future__ import annotations

import pytest

from app.services.eko_journeys import _agent_declined_or_questioned, _explicit_agent_request


@pytest.mark.parametrize(
    "texto",
    [
        "no necesito un agente",
        "no quiero hablar con un agente",
        "No, no necesito hablar con una persona",
        "¿necesito hablar con un agente?",
        "¿tengo que hablar con un operador?",
        "¿hace falta que me atienda una persona?",
    ],
)
def test_nombrar_agente_sin_pedirlo(texto):
    assert _agent_declined_or_questioned(texto)
    assert not _explicit_agent_request(texto)


@pytest.mark.parametrize(
    "texto",
    [
        "quiero hablar con un agente",
        "sí quiero un agente",
        "quiero hablar con una persona",
        "pasame con un operador",
        "agente",
        "¿me pasás con un agente?",
        "no tengo internet",
    ],
)
def test_pedido_real_o_ajeno_no_es_negacion(texto):
    assert not _agent_declined_or_questioned(texto)
