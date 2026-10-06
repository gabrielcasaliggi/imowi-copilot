"""H18: typos de «potencia» (Damerau-Levenshtein <= 1, solo palabras de 7+ letras) llegan al handler de potencia."""

from __future__ import annotations

import pytest

from app.domain.flujos_abonado import cliente_pregunta_potencia_onu


@pytest.mark.parametrize(
    "texto",
    [
        "ok, la potnecia esta bien?",  # transposición
        "la poetncia de la fibra es buena?",
        "la potenccia de la fibra es buena?",  # letra de más
        "la potencai de la fibra es buena?",  # transposición
        "la potenia de la fibra es buena?",  # letra de menos
        "la potencia de la fibra es buena?",  # sin typo
    ],
)
def test_typos_de_potencia_se_reconocen(texto):
    assert cliente_pregunta_potencia_onu(texto)


@pytest.mark.parametrize("palabra", ["presencia", "paciencia", "potencial", "pretencia"])
def test_palabras_parecidas_no_son_potencia(palabra):
    assert not cliente_pregunta_potencia_onu(f"la {palabra} de la fibra es buena?")
    assert not cliente_pregunta_potencia_onu(f"ok, la {palabra} esta bien?")


def test_palabras_cortas_no_se_corrigen():
    # 7+ letras: «potenc» / «pot» no se toman por «potencia»
    assert not cliente_pregunta_potencia_onu("la potenc de la fibra es buena?")
