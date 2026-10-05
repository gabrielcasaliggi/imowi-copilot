"""H13: un caso derivado a un agente no se califica en el cierre N1 del bot (helper común de los cierres N1)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services import canal_abonado as ca


@pytest.mark.parametrize(
    ("ticket_id", "estado_previo", "pide"),
    [
        ("", "bot", True),  # resuelto por el bot: se califica
        ("IBOT-1", "bot", False),  # ticket ligado
        ("", "espera_agente", False),
        ("", "con_agente", False),
    ],
)
def test_cierre_n1_pide_calificacion_solo_si_no_esta_derivado(ticket_id, estado_previo, pide):
    conv = SimpleNamespace(ticket_id=ticket_id, canal="whatsapp")
    with patch.object(ca, "enviar_encuesta_cierre") as enviar:
        out = ca._enviar_encuesta_cierre_n1(None, conv, canal="whatsapp", estado_previo=estado_previo)
    assert out is pide and enviar.called is pide
