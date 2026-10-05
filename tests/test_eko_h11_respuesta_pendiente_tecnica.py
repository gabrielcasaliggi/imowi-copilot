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


# ---- H11b / RC-3 acotado: negar un tema no lo activa
from app.domain.flujos_abonado import niega_tema  # noqa: E402
from app.services.eko_journeys import detect_journey_name  # noqa: E402


@pytest.mark.parametrize("texto", ["no te pregunte por la factura", "no te pregunté por la factura", "no es por la factura", "no tiene que ver con la factura"])
def test_niega_tema_no_reclama_el_turno(texto):
    assert niega_tema(texto)
    assert detect_journey_name(texto) is None
    cs = _cs(pending=True)
    activo = cs.active_domain_id
    assert not apply_turn_domain(cs, texto).changed and cs.active_domain_id == activo


@pytest.mark.parametrize(
    "texto",
    ["no es por internet, es por la factura", "no es por internet sino por la factura", "no tengo internet", "no quiero hablar con un agente", "quiero ver mi factura"],
)
def test_negacion_con_afirmacion_u_otra_frase_no_se_confunde(texto):
    assert not niega_tema(texto)


def test_quiero_ver_mi_factura_sigue_abriendo_facturacion():
    assert detect_journey_name("quiero ver mi factura") == "billing_self_service"


# ---- Tanda 5 F0: paso pendiente cubierto por el Motor en el mismo turno
from app.domain.conversation_state import LastBotAct  # noqa: E402


def _cs_paso_cubierto_en_este_turno():
    """Estado de la 2.ª llamada del lifecycle: el Motor ya cubrió el paso (pending_bot=None)."""
    ctx: dict = {}
    cs = hydrate_conversation_state(ctx)
    apply_turn_domain(cs, "llamadas", playbook_hint="movil_llamadas")
    slot = cs.active_slot()
    cs.turn = 4
    cs.last_bot_act = LastBotAct(act="ASK_FACT", step_id="tipo_problema_llamada", domain_id=cs.active_domain_id, turn=3)
    slot.last_bot_act = cs.last_bot_act
    slot.covered_steps = ["tipo_problema_llamada"]
    cs.pending_bot = None
    slot.pending_bot = None
    return cs


def test_respuesta_con_paso_cubierto_en_el_mismo_turno_sigue_en_tecnico():
    cs = _cs_paso_cubierto_en_este_turno()
    activo = cs.active_domain_id
    assert not apply_turn_domain(cs, "no las recibo").changed and cs.active_domain_id == activo


@pytest.mark.parametrize(
    "texto",
    ["quiero pagar mi factura", "tengo una duda con la factura", "necesito el recibo de pago", "quiero mi recibo", "cuánto debo"],
)
@pytest.mark.parametrize("estado", ["pendiente_abierto", "cubierto_en_el_turno"])
def test_pedido_real_de_facturacion_tras_una_pregunta_sigue_cambiando(texto, estado):
    cs = _cs(pending=True) if estado == "pendiente_abierto" else _cs_paso_cubierto_en_este_turno()
    assert apply_turn_domain(cs, texto).changed, (estado, texto)


def test_paso_cubierto_viejo_no_protege():
    """El último acto del bot es de hace 3 turnos: ya no es «la pregunta anterior»."""
    cs = _cs_paso_cubierto_en_este_turno()
    cs.turn = 6
    assert apply_turn_domain(cs, "no las recibo").changed
