"""H11: con un diagnóstico técnico y su pregunta pendiente, «recibo» suelto no cambia a facturación."""

from __future__ import annotations

import pytest

from app.domain.conversation_state import PendingBot, hydrate_conversation_state
from app.domain.domain_adapter import apply_turn_domain


def _cs(*, pending: bool):
    ctx: dict = {}
    cs = hydrate_conversation_state(ctx)
    apply_turn_domain(cs, "no puedo hacer llamadas", playbook_hint="movil_llamadas")
    if pending:
        cs.pending_bot = PendingBot(act="ASK_FACT", step_id="reiniciar", domain_id=cs.active_domain_id, turn=cs.turn)
    else:
        cs.pending_bot = None
        cs.active_slot().pending_bot = None
    return cs


@pytest.mark.parametrize("texto", ["no las recibo", "no recibo llamadas", "tampoco las recibo"])
def test_respuesta_con_recibo_sigue_en_tecnico(texto):
    cs = _cs(pending=True)
    activo = cs.active_domain_id
    trans = apply_turn_domain(cs, texto)
    assert not trans.changed and cs.active_domain_id == activo


@pytest.mark.parametrize("texto", ["quiero ver mi factura", "cuánto debo", "el recibo de la factura"])
def test_terminos_fuertes_si_cambian_a_facturacion(texto):
    cs = _cs(pending=True)
    assert apply_turn_domain(cs, texto).changed


def test_sin_pregunta_pendiente_no_se_protege():
    cs = _cs(pending=False)
    assert apply_turn_domain(cs, "no las recibo").changed
