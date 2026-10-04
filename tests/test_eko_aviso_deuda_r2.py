"""Tanda 3 RC-6/7 (R2): aviso de saldo informativo y la señal «seguir / no seguir con el diagnóstico»."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.domain.flujos_abonado import responde_seguir_diagnostico
from app.services.canal_abonado import _texto_aviso_deuda_tecnico


def test_texto_del_aviso_es_informativo_y_no_pregunta():
    txt = _texto_aviso_deuda_tecnico(SimpleNamespace(deuda_monto="15000.00"), "internet")
    assert "saldo pendiente" in txt and "15.000,00" in txt and "Oficina Virtual" in txt
    assert "?" not in txt and "primero a pagar" not in txt


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("seguimos con el diagnóstico", "seguir"),
        ("seguí con el diagnóstico", "seguir"),
        ("continuemos con el diagnostico", "seguir"),
        ("no sigamos con el diagnóstico", "no_seguir"),
        ("no sigas con el diagnóstico", "no_seguir"),
        ("sigue igual", None),
        ("quiero pagar", None),
    ],
)
def test_responde_seguir_diagnostico(texto, esperado):
    assert responde_seguir_diagnostico(texto) == esperado
