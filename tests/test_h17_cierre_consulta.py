"""H17 fix C: los detectores de cierre (CSAT) exigen cierre puro; una pregunta o un «pero» no cierran la consulta."""

from __future__ import annotations

import pytest

from app.domain.conversacion import mensaje_indica_resolucion_real, usuario_confirmo_resolucion
from app.domain.flujos_abonado import indica_resuelto
from app.services.canal_abonado import _cliente_desiste_o_resuelto
from app.services.diagnostico_n1 import _cierra_consulta_facturacion

XF = pytest.mark.xfail(strict=True, reason="H17-C: los detectores de cierre matchean 'listo'/'gracias'/'ya está' por substring")
FALLAN_CIERRE = {
    "listo, ahora decime la deuda", "gracias, y la factura?", "listo, pero no mejoró", "no, ya funciona mal",
    "ya está caído hace rato", "ya esta? no me anda", "ya está fallando de nuevo",
}
FALLAN_RESOLUCION = {"listo, ahora decime la deuda", "no, ya funciona mal", "ok pero sigue igual", "ok, y el ticket anterior?"}

NO_CIERRA = [
    "listo, ahora decime la deuda",
    "gracias, y la factura?",
    "listo, pero no mejoró",
    "no, ya funciona mal",
    "ya está caído hace rato",
    "ya esta? no me anda",
    "ya está fallando de nuevo",
    "ok pero sigue igual",
    "ok, y el ticket anterior?",
    "gracias pero sigue sin andar",
    "bueno, y el precio?",
]

CIERRA = [
    "gracias",
    "listo gracias",
    "ya funciona",
    "ya quedó, gracias",
    "muchas gracias",
    "perfecto, gracias",
    "ya anda",
    "no necesito nada más",
]


def _cierra(texto: str) -> bool:
    """Lo que decide cerrar la consulta (y mandar CSAT) en los sitios de llamada del canal."""
    return bool(indica_resuelto(texto) or _cliente_desiste_o_resuelto(texto) or _cierra_consulta_facturacion(texto))


@pytest.mark.parametrize("texto", [pytest.param(t, marks=XF) if t in FALLAN_CIERRE else t for t in NO_CIERRA])
def test_no_cierra_consulta(texto):
    assert not _cierra(texto)
    assert not _cierra_consulta_facturacion(texto)
    assert not _cliente_desiste_o_resuelto(texto)


@pytest.mark.parametrize("texto", CIERRA)
def test_si_cierra_consulta(texto):
    assert _cierra(texto)


@pytest.mark.parametrize(
    "texto",
    [pytest.param(t, marks=XF) if t in FALLAN_RESOLUCION else t for t in NO_CIERRA if not t.startswith(("gracias", "bueno"))],
)
def test_no_hay_resolucion_real(texto):
    assert not mensaje_indica_resolucion_real(texto)
    assert not usuario_confirmo_resolucion([{"rol": "usuario", "contenido": texto}], "")


@pytest.mark.parametrize("texto", ["ya funciona", "ya anda", "gracias ya anda", "problema resuelto", "listo"])
def test_si_hay_resolucion_real(texto):
    assert mensaje_indica_resolucion_real(texto)
    assert usuario_confirmo_resolucion([{"rol": "usuario", "contenido": texto}], "")
