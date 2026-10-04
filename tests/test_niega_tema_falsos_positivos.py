"""H11b: ``niega_tema`` solo debe disparar con la negación pura de un tema, no con cualquier «no»."""

from __future__ import annotations

import pytest

from app.domain.conversation_state import PendingBot, hydrate_conversation_state
from app.domain.domain_adapter import apply_turn_domain
from app.domain.flujos_abonado import clasificar_intencion, niega_tema
from app.services.eko_journeys import detect_journey_name

# 15 frases con «no» que NO niegan un tema: no deben cambiar la clasificación.
NO_NIEGAN = [
    "no es por internet, es por la factura",
    "no es por internet sino por la factura",
    "no hablo de internet, hablo de la factura",
    "no es por el wifi, la factura vino mal",
    "no entiendo mi factura",
    "no me llegó el recibo",
    "no me llegó la factura",
    "no puedo pagar la factura",
    "no quiero pagar la factura ahora",
    "no sé por qué me cobraron de más",
    "no es mi factura, es de mi vecino",
    "no tengo internet",
    "no me anda el wifi",
    "no puedo hacer llamadas",
    "no necesito un agente, necesito ver mi factura",
]

# Subconjunto que además debe seguir clasificando a facturación (no a «general»).
SIGUEN_FACTURACION = [
    "no es por internet, es por la factura",
    "no entiendo mi factura",
    "no me llegó el recibo",
    "no me llegó la factura",
    "no puedo pagar la factura",
]

# 5 negaciones puras del tema: vuelven al dominio activo.
SI_NIEGAN = [
    "no te pregunte por la factura",
    "no te pregunté por la factura",
    "no es por la factura",
    "no tiene que ver con la factura",
    "no te pregunté nada de la factura",
]


@pytest.mark.parametrize("texto", NO_NIEGAN)
def test_no_es_negacion_de_tema(texto):
    assert not niega_tema(texto), texto


@pytest.mark.parametrize("texto", SIGUEN_FACTURACION)
def test_sigue_clasificando_a_facturacion(texto):
    assert clasificar_intencion(texto) != "general", texto


def _cs_tecnico():
    ctx: dict = {}
    cs = hydrate_conversation_state(ctx)
    apply_turn_domain(cs, "no puedo hacer llamadas", playbook_hint="movil_llamadas")
    cs.pending_bot = PendingBot(act="ASK_FACT", step_id="reiniciar", domain_id=cs.active_domain_id, turn=cs.turn)
    return cs


@pytest.mark.parametrize("texto", SI_NIEGAN)
def test_negacion_pura_vuelve_al_dominio_activo(texto):
    assert niega_tema(texto), texto
    assert detect_journey_name(texto) is None
    cs = _cs_tecnico()
    activo = cs.active_domain_id
    assert not apply_turn_domain(cs, texto).changed and cs.active_domain_id == activo
