"""H17 fix B: ``usuario_confirmo_ticket`` solo confirma con afirmación corta o frase explícita, nunca por substring."""

from __future__ import annotations

import pytest

from app.domain.conversacion import IntencionPendiente, usuario_confirmo_ticket
from app.services.eko_action_bridge import resolve_user_confirmation

XF = pytest.mark.xfail(strict=True, reason="H17-B: usuario_confirmo_ticket matchea 'si'/'dale' por substring")
CONFIRMAR = IntencionPendiente.CONFIRMAR_TICKET.value
# (texto, pendiente) que fallan hoy; el resto ya pasa y queda como regresión.
FALLAN_NO = {
    "dale pero no entendí", "si no anda te aviso", "si, pero antes decime el saldo", "dale, cuánto cuesta el plan",
    "sí, el problema es otro", "si querés, después",
}
FALLAN_SI = {"derivame", "abrí el ticket"}


def _marca(texto: str, pend: str, fallan: set[str], extra: set[tuple[str, str]] = frozenset()):
    id_ = f"{texto}-{pend}"
    if texto in fallan or (texto, pend) in extra:
        return pytest.param(texto, pend, marks=XF, id=id_)
    return pytest.param(texto, pend, id=id_)

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
]


def _hist(texto: str) -> list[dict]:
    return [{"rol": "asistente", "contenido": "¿Querés que te derive con un agente?"}, {"rol": "usuario", "contenido": texto}]


@pytest.mark.parametrize(
    "texto,pendiente",
    [_marca(t, p, FALLAN_NO, {("no necesito agente", CONFIRMAR)}) for t in NO_CONFIRMA for p in ("", CONFIRMAR)],
)
def test_no_confirma_ticket(texto, pendiente):
    assert not usuario_confirmo_ticket(_hist(texto), pendiente)


@pytest.mark.parametrize("texto,pendiente", [_marca(t, p, FALLAN_SI) for t in CONFIRMA for p in ("", CONFIRMAR)])
def test_si_confirma_ticket(texto, pendiente):
    assert usuario_confirmo_ticket(_hist(texto), pendiente)


@pytest.mark.parametrize("texto", [pytest.param(t, marks=XF) if t in FALLAN_NO else t for t in NO_CONFIRMA])
def test_runtime_no_confirma_por_historial(texto):
    rec, _rej = resolve_user_confirmation(historial=_hist(texto), action="create_ticket", texto=texto)
    assert not rec


@pytest.mark.parametrize("texto", ["sí", "dale", "creá el ticket", pytest.param("derivame", marks=XF)])
def test_runtime_confirma_por_historial(texto):
    rec, _rej = resolve_user_confirmation(historial=_hist(texto), action="create_ticket", texto=texto)
    assert rec
