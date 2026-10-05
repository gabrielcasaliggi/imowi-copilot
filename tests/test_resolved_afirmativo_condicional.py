"""F3b: la política de «resuelto» no acepta promesas de probar («ok si funciona») como confirmación."""

from __future__ import annotations

import pytest

from app.domain.action_proposal import ACTION_ASK, SOURCE_LLM, ActionProposal, evaluate_resolved

_PROPUESTA = ActionProposal(action="resolved", source=SOURCE_LLM, reason="ia", message="¡Genial!")


@pytest.mark.parametrize(
    "texto",
    ["ok si funciona", "ok, aviso si funciona", "dale, te aviso si anda", "cuando pruebe te cuento", "voy a probar y te digo"],
)
def test_afirmativo_condicional_no_resuelve_y_pide_confirmar(texto):
    d = evaluate_resolved(_PROPUESTA, texto)
    assert not d.allow and d.demote_to == ACTION_ASK
    assert d.reason == "bloqueado_resolved_afirmativo_condicional"
    assert "?" in d.message and "prueba" in d.message.lower()


@pytest.mark.parametrize("texto", ["ya funciona", "sí, ya anda", "ahora funciona, gracias", "ya se arregló", "quedó bien"])
def test_confirmacion_real_sigue_resolviendo(texto):
    assert evaluate_resolved(_PROPUESTA, texto).allow, texto
