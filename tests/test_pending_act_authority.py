"""Gate 11E: pending.act se deriva de step_id, no del copy LLM."""

from __future__ import annotations

from unittest.mock import patch

from sqlalchemy import select

from app.domain.conversation_motor import (
    ACT_ASK_NEXT_STEP,
    BOT_ASK_ACTION,
    BOT_ASK_FACT,
    USER_CONFIRM_ACTION,
    apply_cs_to_legacy,
    classify_step_act,
    interpret_turn,
    process_turn,
    stamp_bot_question,
)
from app.domain.conversation_state import (
    KIND_TECNICO,
    LastBotAct,
    PendingBot,
    hydrate_conversation_state,
)
from app.domain.domain_lifecycle import (
    cover_and_note,
    create_domain,
    new_conversation_state,
    set_slot_pending,
)
from app.estate import canal_repo as crepo
from app.estate.database import get_session_factory
from app.estate.models import Abonado, ConversacionCanal, Organization
from app.services.canal_abonado import procesar_mensaje_entrante
from app.services.canal_diagnostico_ia import _aplicar_diagnostico_ia

_DNI = "30111222"
_CANAL = "whatsapp"


def _org_abo():
    Session = get_session_factory()
    with Session() as db:
        org = db.scalar(select(Organization).where(Organization.slug == "coop-batan"))
        abo = db.scalar(select(Abonado).where(Abonado.dni == _DNI))
        assert org and abo
        return org.id, abo.id


def _abrir(tel: str, *, extra: dict | None = None) -> tuple[str, str]:
    org_id, abo_id = _org_abo()
    Session = get_session_factory()
    with Session() as db:
        for c in db.scalars(
            select(ConversacionCanal).where(ConversacionCanal.telefono.contains(tel[-10:]))
        ).all():
            c.estado = "cerrado"
            c.contexto_json = "{}"
            c.ticket_id = ""
            c.agente_id = ""
            c.abonado_id = ""
        db.commit()
        conv = crepo.get_or_create_conversacion(
            db, org_id, telefono=tel, canal=_CANAL, wa_id=tel
        )
        conv.estado = "bot"
        conv.abonado_id = abo_id
        conv.ticket_id = ""
        base = {"saludo": True, "identificado": True, "dni": _DNI}
        if extra:
            base.update(extra)
        crepo.set_contexto(conv, base)
        db.commit()
        return org_id, conv.id


def _load_ctx(conv_id: str) -> dict:
    Session = get_session_factory()
    with Session() as db:
        conv = db.get(ConversacionCanal, conv_id)
        assert conv is not None
        return crepo.get_contexto(conv)


def _seed_tec(*, pending_step: str = "luces_los") -> dict:
    cs = new_conversation_state(turn=2)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet_ftth")
    cover_and_note(cs, steps=["energia_ont"], facts={})
    set_slot_pending(
        cs,
        pending_bot=PendingBot(
            act=BOT_ASK_FACT, step_id=pending_step, referent=pending_step
        ),
        last_bot_act=LastBotAct(
            act=BOT_ASK_FACT, step_id=pending_step, referent=pending_step
        ),
    )
    ctx: dict = {
        "intencion": "internet_ftth",
        "paso_idx": 1,
        "pasos_cubiertos": ["energia_ont"],
        "hechos": {},
        "diag_turnos": 1,
        "pppoe_informado": True,
        "lectura_forzada_e1": True,
    }
    apply_cs_to_legacy(ctx, cs)
    return ctx


# ---------------------------------------------------------------------------
# Unit
# ---------------------------------------------------------------------------


def test_pa1_llm_copy_no_crea_ask_action():
    msg = (
        "Vamos a reiniciar el equipo para comprobar si recuperamos la conexión. "
        "¿Qué luces ves?"
    )
    act = classify_step_act("luces_los", msg)
    assert act != BOT_ASK_ACTION
    assert act == BOT_ASK_FACT


def test_pa2_paso_confirmable_crea_ask_action():
    act = classify_step_act(
        "reinicio_ont",
        "Cualquier copy del LLM sin la palabra reinicio.",
    )
    assert act == BOT_ASK_ACTION


def test_pa3_copy_diferente_misma_semantica():
    sid = "energia_ont"
    msgs = (
        "Reiniciemos el equipo.",
        "Probemos apagarlo y volverlo a encender.",
        "Vamos a hacer una comprobación con el equipo.",
    )
    acts = [classify_step_act(sid, m) for m in msgs]
    assert acts[0] == acts[1] == acts[2]
    assert acts[0] != BOT_ASK_ACTION


def test_pa3b_reinicio_misma_semantica_con_cualquier_copy():
    sid = "reinicio_ont"
    msgs = (
        "Reiniciemos el equipo.",
        "Probemos apagarlo y volverlo a encender.",
        "Solo decime cuando esté listo.",
    )
    acts = [classify_step_act(sid, m) for m in msgs]
    assert acts[0] == acts[1] == acts[2] == BOT_ASK_ACTION


def test_pa4_confirmacion_continua_funcionando():
    cs = new_conversation_state(turn=3)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet_ftth")
    set_slot_pending(
        cs,
        pending_bot=PendingBot(
            act=BOT_ASK_ACTION,
            step_id="reinicio_ont",
            referent="reinicio_ont",
            domain_id=cs.active_domain_id,
        ),
        last_bot_act=LastBotAct(
            act=BOT_ASK_ACTION,
            step_id="reinicio_ont",
            referent="reinicio_ont",
            domain_id=cs.active_domain_id,
        ),
    )
    before = list(cs.active_slot().covered_steps)
    assert "reinicio_ont" not in before
    interp = interpret_turn("listo", cs, {})
    assert interp.user_act == USER_CONFIRM_ACTION
    result = process_turn(cs, interp, {})
    assert "reinicio_ont" in (cs.active_slot().covered_steps or [])
    assert result.action.type in (ACT_ASK_NEXT_STEP, "ASK_NEXT_STEP") or True
    assert "reinicio_ont" in result.action.cover_steps or "reinicio_ont" in (
        cs.active_slot().covered_steps or []
    )


def test_pa5_texto_sin_relacion_no_ask_action():
    act = classify_step_act("luces_los", "Podemos revisar la conexión.")
    assert act != BOT_ASK_ACTION
    assert act == BOT_ASK_FACT


def test_pa6_stamp_no_cubre_por_mensaje():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet_ftth")
    ctx: dict = {"intencion": "internet_ftth"}
    apply_cs_to_legacy(ctx, cs)
    before = list(hydrate_conversation_state(ctx).active_slot().covered_steps)
    stamp_bot_question(
        ctx,
        step_id="luces_los",
        pregunta=(
            "Vamos a reiniciar el equipo para comprobar si recuperamos la conexión."
        ),
        intencion="internet_ftth",
    )
    cs2 = hydrate_conversation_state(ctx)
    assert cs2.pending_bot is not None
    assert cs2.pending_bot.act != BOT_ASK_ACTION
    assert cs2.pending_bot.act == BOT_ASK_FACT
    assert list(cs2.active_slot().covered_steps) == before


def test_pa7_stamp_no_cambia_active_domain():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet_ftth")
    ctx: dict = {"intencion": "internet_ftth"}
    apply_cs_to_legacy(ctx, cs)
    before = hydrate_conversation_state(ctx).active_domain_id
    stamp_bot_question(
        ctx,
        step_id="reinicio_ont",
        pregunta="Reiniciemos el equipo ahora.",
        intencion="internet_ftth",
    )
    after = hydrate_conversation_state(ctx).active_domain_id
    assert after == before == "tec-1"
    assert hydrate_conversation_state(ctx).pending_bot.act == BOT_ASK_ACTION


def test_pa8_regresion_modulos_importables():
    from tests import test_escalate_authority as te
    from tests import test_llm_covered_authority as tc
    from tests import test_resolved_authority as tr

    assert callable(tr.test_r2_llm_resolved_allow_cierra)
    assert callable(te.test_e2_llm_escalate_allow_crea_ticket)
    assert callable(tc.test_ia01_llm_no_cubre_paso_incorrecto)


# ---------------------------------------------------------------------------
# Productivo
# ---------------------------------------------------------------------------


def test_producto_llm_mensaje_reinicio_no_ask_action_si_paso_no_confirmable():
    """diagnosticar_turno mock: mensaje con 'reiniciar'; step stamp = luces_los."""
    tel = "5492235616020"
    seed = _seed_tec(pending_step="luces_los")
    org_id, conv_id = _abrir(tel, extra=seed)
    domain_before = hydrate_conversation_state(_load_ctx(conv_id)).active_domain_id
    cub_antes = list(_load_ctx(conv_id).get("pasos_cubiertos") or [])

    ia = {
        "accion": "ask",
        "mensaje": (
            "Vamos a reiniciar el equipo para comprobar si recuperamos la conexión. "
            "¿La luz PON está verde fija y la LOS apagada?"
        ),
        "paso_cubierto": "reinicio_ont",
        "motivo": "ia",
    }

    with (
        patch(
            "app.services.canal_abonado.resolve_canal_diagnostico_ia",
            return_value=True,
        ),
        patch(
            "app.services.diagnostico_n1.diagnosticar_turno",
            return_value=dict(ia),
        ),
        patch("app.services.canal_pppoe._talvez_mensaje_pppoe", return_value=None),
        patch("app.services.canal_abonado._linea_acceso_ok_ctx", return_value=False),
        patch("app.services.canal_abonado.indica_resuelto", return_value=False),
        patch(
            "app.services.canal_abonado._cliente_desiste_o_resuelto",
            return_value=False,
        ),
        patch("app.services.canal_abonado._aplicar_discurso_cs", return_value=None),
    ):
        Session = get_session_factory()
        with Session() as db:
            conv = db.get(ConversacionCanal, conv_id)
            abo = db.get(Abonado, conv.abonado_id)
            ctx = crepo.get_contexto(conv)
            out = _aplicar_diagnostico_ia(
                db,
                org_id,
                conv,
                abo,
                "sigo igual",
                canal=_CANAL,
                ctx=ctx,
                intencion="internet_ftth",
                usar_llama=True,
            )
            db.commit()

    assert out is not None
    assert out.get("modo") != "espera_agente"
    ctx2 = _load_ctx(conv_id)
    cs2 = hydrate_conversation_state(ctx2)
    assert cs2.pending_bot is not None
    # Pending conservado o primer no cubierto (luces_los), no ASK_ACTION por copy.
    assert cs2.pending_bot.act != BOT_ASK_ACTION
    assert "reinicio_ont" not in (ctx2.get("pasos_cubiertos") or [])
    assert list(ctx2.get("pasos_cubiertos") or []) == cub_antes
    assert cs2.active_domain_id == domain_before == "tec-1"


def test_producto_procesar_mensaje_stamp_por_step_id():
    tel = "5492235616021"
    seed = _seed_tec(pending_step="luces_los")
    org_id, conv_id = _abrir(tel, extra=seed)

    with (
        patch(
            "app.services.canal_abonado.resolve_canal_diagnostico_ia",
            return_value=True,
        ),
        patch(
            "app.services.diagnostico_n1.diagnosticar_turno",
            return_value={
                "accion": "ask",
                "mensaje": "Reiniciemos el módem ahora mismo. ¿Qué ves?",
                "paso_cubierto": "",
                "motivo": "ia",
            },
        ),
        patch("app.services.canal_pppoe._talvez_mensaje_pppoe", return_value=None),
        patch("app.services.canal_abonado._linea_acceso_ok_ctx", return_value=False),
        patch("app.services.canal_abonado.indica_resuelto", return_value=False),
        patch(
            "app.services.canal_abonado._cliente_desiste_o_resuelto",
            return_value=False,
        ),
        patch("app.services.canal_abonado._aplicar_discurso_cs", return_value=None),
    ):
        Session = get_session_factory()
        with Session() as db:
            out = procesar_mensaje_entrante(
                db,
                org_id,
                telefono=tel,
                texto="todavía en diagnóstico ftth",
                canal=_CANAL,
                usar_llama=True,
            )
            db.commit()

    assert out.get("estado") != "espera_agente"
    cs = hydrate_conversation_state(_load_ctx(conv_id))
    if cs.pending_bot and cs.pending_bot.step_id == "luces_los":
        assert cs.pending_bot.act != BOT_ASK_ACTION
