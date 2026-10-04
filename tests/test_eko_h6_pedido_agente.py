"""H6 — el pedido explícito de agente ES la confirmación (ADR-EKO-TURN-CONTRACT, regla 5)."""

from __future__ import annotations

import pytest

from app.services.eko_journeys import _explicit_agent_request


@pytest.mark.parametrize(
    "texto",
    [
        "quiero hablar con un agente",
        "Necesito hablar con una persona",
        "pasame con un operador",
        "agente",
        "quiero un agente",
        "prefiero hablar con alguien",
    ],
)
def test_pedidos_explicitos(texto):
    assert _explicit_agent_request(texto)


@pytest.mark.parametrize(
    "texto",
    [
        "no quiero hablar con un agente",
        "no necesito un agente",
        "¿necesito hablar con un agente?",
        "ya no hace falta el agente",
        "no, gracias, sin agente",
        "sí",
        "ya anda, gracias",
        "decime algo",
        "tengo un agente de seguros que me dijo",
        "",
    ],
)
def test_no_son_pedidos(texto):
    assert not _explicit_agent_request(texto)
