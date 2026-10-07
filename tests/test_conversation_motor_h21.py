"""H21 (Fix 1): el Motor 2.5 no confunde «ya lo hice»/«sigue igual» fuera de una acción pendiente.

Unitarios de ``interpret_turn`` y de ``_aplicar_discurso_cs``. Retiran los xfails del Paso 0 de H21 Fix 1.
"""

from __future__ import annotations

import pytest

from app.domain.conversation_motor import (
    USER_CONFIRM_ACTION,
    USER_REPORT_PERSISTENCE,
    interpret_turn,
)
from app.domain.conversation_state import ConversationState, DomainSlot, LastBotAct, PendingBot
from tests.test_conversation_motor import _ftth_cs


@pytest.mark.parametrize("texto", ["ya lo hice", "Ya lo hice."])
def test_confirm_action_no_aplica_a_un_pendiente_ask_fact(texto):
    cs = _ftth_cs(pending_step="alcance_dispositivos", pending_act="ASK_FACT", last_act="ASK_FACT")
    assert interpret_turn(texto, cs, {}).user_act != USER_CONFIRM_ACTION


@pytest.mark.parametrize("texto", ["ya lo hice, sigue igual", "si, ya lo hice, sigue igual", "Ya lo hice pero sigue sin andar"])
def test_la_persistencia_gana_a_la_confirmacion(texto):
    cs = _ftth_cs()  # pendiente ASK_ACTION
    assert interpret_turn(texto, cs, {}).user_act == USER_REPORT_PERSISTENCE


def test_confirm_action_sin_pendiente_y_ultimo_acto_ask_fact_no_confirma():
    cs = _ftth_cs()
    cs.pending_bot = None
    cs.last_bot_act = LastBotAct(act="ASK_FACT", referent="alcance_dispositivos", domain_id="tec-1", step_id="alcance_dispositivos", turn=5)
    assert interpret_turn("ya lo hice", cs, {}).user_act != USER_CONFIRM_ACTION


def test_discurso_sin_paso_resuelto_difiere_al_legacy():
    from app.estate import canal_repo as crepo
    from app.estate.database import get_session_factory
    from app.services import canal_abonado as c

    cs = ConversationState(
        v=1, turn=4, active_domain_id="tec-1", domain_stack=["tec-1"],
        domains=[DomainSlot(id="tec-1", kind="tecnico", playbook="internet", status="active", covered_steps=[], cursor=1, opened_turn=1)],
        pending_bot=PendingBot(act="ASK_FACT", step_id=None, referent=None, domain_id="tec-1", turn=4),
        last_bot_act=LastBotAct(act="ASK_FACT", referent=None, domain_id="tec-1", step_id=None, turn=4),
    )
    Session = get_session_factory()
    with Session() as db:
        from sqlalchemy import select

        from app.estate.models import Organization

        org = db.scalar(select(Organization).where(Organization.slug == "coop-batan"))
        conv = crepo.get_or_create_conversacion(db, org.id, telefono="5492231230001", canal="web", wa_id="5492231230001")
        try:
            ctx = {"cs": cs.to_dict()}
            out = c._aplicar_discurso_cs(db, org.id, conv, "si, ya lo hice, sigue igual", canal="web", ctx=ctx, intencion="internet", pasos=[])
            assert out is None, out
        finally:
            conv.estado = "cerrado"
            db.commit()
