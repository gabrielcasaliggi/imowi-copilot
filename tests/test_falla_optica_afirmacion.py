"""Un «sí» suelto no confirma una alarma óptica cuando la pregunta ofrece también la opción sana (mismo tipo que H17:
afirmación suelta leída fuera de contexto)."""

from __future__ import annotations

import pytest

from app.services.diagnostico_n1 import detectar_falla_optica_escalar

MIXTA = "¿La luz PON está verde fija y la LOS apagada, o ves alguna en rojo?"
SOLO_ALARMA = "¿La luz LOS está en rojo?"
CHEQUEO_FIBRA = "¿El cable de fibra tiene dobleces o daños visibles?"


def _bot(texto: str) -> dict:
    return {"autor": "bot", "texto": texto}


@pytest.mark.parametrize("si", ["si", "sí", "si, ya lo hice, sigue igual"])
def test_si_suelto_ante_pregunta_mixta_no_confirma(si):
    assert detectar_falla_optica_escalar(si, [_bot(MIXTA)]) is None
    # Ni siquiera con el chequeo de fibra posterior: el «sí» no era la alarma.
    assert detectar_falla_optica_escalar("no sé", [_bot(MIXTA), {"autor": "cliente", "texto": si}, _bot(CHEQUEO_FIBRA)]) is None


def test_la_los_esta_en_rojo_confirma():
    assert detectar_falla_optica_escalar("la LOS está en rojo", [_bot(MIXTA)]) == "los_confirmada"


def test_no_esta_verde_no_confirma():
    assert detectar_falla_optica_escalar("no, está verde", [_bot(MIXTA)]) is None


def test_pregunta_solo_de_alarma_mas_si_confirma():
    historial = [_bot(SOLO_ALARMA), {"autor": "cliente", "texto": "sí"}, _bot(CHEQUEO_FIBRA)]
    assert detectar_falla_optica_escalar("no veo nada raro", historial) == "los_con_chequeo_fibra"
