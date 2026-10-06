"""H17 fix B: ``usuario_confirmo_ticket`` solo confirma con afirmación corta o frase explícita, nunca por substring."""

from __future__ import annotations

import pytest

from app.domain.conversacion import IntencionPendiente, usuario_confirmo_ticket
from app.services.eko_action_bridge import resolve_user_confirmation

CONFIRMAR = IntencionPendiente.CONFIRMAR_TICKET.value

NO_CONFIRMA = [
    "dale pero no entendí",
    "si no anda te aviso",
    "si, pero antes decime el saldo",
    "dale, cuánto cuesta el plan",
    "sí, el problema es otro",
    "si querés, después",
    "no necesito agente",
    "ok, y el ticket anterior?",
    "gracias",
    "no quiero que generes el ticket",
    "dale?",
    "¿me derivás con un agente?",
    "no, dale igual",
    "sí, pero antes decime el saldo y el vencimiento",
    "ok vamos a ver cómo sigue",
    "abri ticket",
]

CONFIRMA = [
    "sí",
    "si",
    "dale",
    "confirmo",
    "adelante",
    "hacelo",
    "sí quiero",
    "si quiero",
    "sí, dale",
    "dale sí",
    "creá el ticket",
    "generá el ticket",
    "registralo",
    "derivame",
    "sí derivame",
    "abrí el ticket",
    "si por favor",
    "dale, derivame",
    "sí, generá el ticket",
    "ok dale",
    "dale, creá el ticket por favor",
]

# Texto tal como llega por canal (portal, mobile, whatsapp): mayúsculas, espacios, signos, tildes.
CONFIRMA_POR_CANAL = ["Sí.", "SI", "  Sí  ", "Si!", "SÍ", "Dale.", "DALE!!", "sí,", "Sí, dale.", "Sí\n", "SI POR FAVOR", "Derivame."]
NO_CONFIRMA_POR_CANAL = ["No.", "NO", "Si?", "Sí, pero no entendí", "DALE PERO NO ENTENDÍ", "Si no anda te aviso."]


def _hist(texto: str) -> list[dict]:
    return [{"rol": "asistente", "contenido": "¿Querés que te derive con un agente?"}, {"rol": "usuario", "contenido": texto}]


@pytest.mark.parametrize("pendiente", ["", CONFIRMAR])
@pytest.mark.parametrize("texto", NO_CONFIRMA)
def test_no_confirma_ticket(texto, pendiente):
    assert not usuario_confirmo_ticket(_hist(texto), pendiente)


@pytest.mark.parametrize("pendiente", ["", CONFIRMAR])
@pytest.mark.parametrize("texto", CONFIRMA)
def test_si_confirma_ticket(texto, pendiente):
    assert usuario_confirmo_ticket(_hist(texto), pendiente)


@pytest.mark.parametrize("canal", ["portal", "mobile", "whatsapp"])
@pytest.mark.parametrize("texto", CONFIRMA_POR_CANAL)
def test_confirma_ticket_texto_tal_como_llega_por_canal(texto, canal):
    assert usuario_confirmo_ticket(_hist(texto), CONFIRMAR)
    assert usuario_confirmo_ticket(_hist(texto))


@pytest.mark.parametrize("canal", ["portal", "mobile", "whatsapp"])
@pytest.mark.parametrize("texto", NO_CONFIRMA_POR_CANAL)
def test_no_confirma_ticket_texto_tal_como_llega_por_canal(texto, canal):
    assert not usuario_confirmo_ticket(_hist(texto), CONFIRMAR)


@pytest.mark.parametrize("texto", NO_CONFIRMA)
def test_runtime_no_confirma_por_historial(texto):
    rec, _rej = resolve_user_confirmation(historial=_hist(texto), action="create_ticket", texto=texto)
    assert not rec


@pytest.mark.parametrize("texto", ["sí", "dale", "creá el ticket", "derivame"])
def test_runtime_confirma_por_historial(texto):
    rec, _rej = resolve_user_confirmation(historial=_hist(texto), action="create_ticket", texto=texto)
    assert rec
