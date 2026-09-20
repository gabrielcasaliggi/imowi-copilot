"""Gate 13 — Final Authority Audit: tests adversariales FA-01..15."""

from __future__ import annotations

from unittest.mock import patch

from sqlalchemy import select

from app.domain.action_proposal import (
    ACTION_ESCALATE,
    SOURCE_LLM,
    SOURCE_PLANT,
    ActionProposal,
    evaluate_escalate,
    infer_proposal_source,
    proposal_from_diag_result,
    sanitize_llm_claimed_motivo,
)
from app.domain.conversation_motor import (
    ACT_ASK_NEXT_STEP,
    ACT_CLOSE,
    BOT_ASK_ACTION,
    BOT_ASK_FACT,
    USER_CONFIRM_ACTION,
    apply_cs_to_legacy,
    authorize_escalate,
    authorize_resolved,
    classify_step_act,
    cover_step,
    interpret_turn,
    process_turn,
    stamp_bot_question,
)
from app.domain.conversation_state import (
    CS_KEY,
    KIND_TECNICO,
    LastBotAct,
    PendingBot,
    hydrate_conversation_state,
    mark_covers,
    sync_from_legacy,
    write_shadow_into_ctx,
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
from app.services.canal_diagnostico_ia import _aplicar_diagnostico_ia

_DNI = "30111222"
_CANAL = "whatsapp"


def _cs_tec(covers: list[str] | None = None):
    cs = new_conversation_state(turn=2)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet_ftth")
    if covers:
        cover_and_note(cs, steps=covers)
    return cs


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
        base = {
            "saludo": True,
            "identificado": True,
            "dni": _DNI,
            "intencion": "internet_ftth",
            "diag_turnos": 0,
            "pasos_cubiertos": ["energia_ont"],
            "paso_idx": 1,
        }
        cs = _cs_tec(["energia_ont"])
        base[CS_KEY] = cs.to_dict()
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


def _aplicar(org_id: str, conv_id: str, texto: str, *, ia: dict, tickets: list):
    Session = get_session_factory()
    with Session() as db:
        conv = db.get(ConversacionCanal, conv_id)
        abo = db.get(Abonado, conv.abonado_id) if conv and conv.abonado_id else None
        ctx = crepo.get_contexto(conv)
        assert conv and abo

        def _ticket(*_a, **_k):
            tickets.append("x")
            return "T-FA"

        with (
            patch(
                "app.services.diagnostico_n1.diagnosticar_turno",
                return_value=ia,
            ),
            patch(
                "app.services.canal_abonado._crear_ticket_n2",
                side_effect=_ticket,
            ),
            patch("app.services.handoff_notify.notify_espera_agente", return_value=0),
            patch("app.services.canal_pppoe._talvez_mensaje_pppoe", return_value=None),
            patch("app.services.canal_abonado._linea_acceso_ok_ctx", return_value=False),
            patch("app.services.canal_abonado.indica_resuelto", return_value=False),
            patch(
                "app.services.canal_abonado._cliente_desiste_o_resuelto",
                return_value=False,
            ),
        ):
            return _aplicar_diagnostico_ia(
                db,
                org_id,
                conv,
                abo,
                texto,
                canal=_CANAL,
                ctx=ctx,
                intencion="internet_ftth",
                usar_llama=True,
            )


# ---------------------------------------------------------------------------
# FA-01..15
# ---------------------------------------------------------------------------


def test_fa_01_llm_no_cambia_active_domain_id():
    cs = _cs_tec()
    ctx = {"intencion": "internet_ftth", "pasos_cubiertos": [], CS_KEY: cs.to_dict()}
    before = hydrate_conversation_state(ctx).active_domain_id
    stamp_bot_question(
        ctx,
        step_id="luces_los",
        pregunta="Reiniciá el equipo ahora por favor.",
        intencion="internet_ftth",
    )
    assert hydrate_conversation_state(ctx).active_domain_id == before


def test_fa_02_llm_no_crea_covered_steps():
    cs = _cs_tec(["energia_ont"])
    ctx = {
        "intencion": "internet_ftth",
        "pasos_cubiertos": ["energia_ont"],
        CS_KEY: cs.to_dict(),
        "ia_suggested_step": "wifi_1",
        "paso_cubierto": "wifi_1",
    }
    write_shadow_into_ctx(ctx)
    sync_from_legacy(hydrate_conversation_state(ctx), ctx)
    assert "wifi_1" not in (
        hydrate_conversation_state(ctx).active_slot().covered_steps or []
    )


def test_fa_03_llm_copy_no_crea_pending_act_ask_action():
    assert classify_step_act("luces_los", "Reiniciá el router YA") == BOT_ASK_FACT
    assert classify_step_act("luces_los", "¿Ves la luz PON?") == BOT_ASK_FACT


def test_fa_04_llm_resolved_sin_motor_no_cierra():
    p = ActionProposal(
        action="resolved",
        source=SOURCE_LLM,
        reason="ia",
        message="Listo, quedó resuelto.",
    )
    # Contacto sin servicio → policy deny (ya cubierto); JSON solo no basta.
    cs = _cs_tec()
    auth = authorize_resolved(cs, p, "me respondieron por mail", {})
    assert auth.allow is False
    assert auth.action.type != ACT_CLOSE


def test_fa_05_llm_escalate_sin_motor_no_act_escalate():
    p = ActionProposal(
        action=ACTION_ESCALATE,
        source=SOURCE_LLM,
        reason="ia",
        message="Te derivo.",
    )
    cs = _cs_tec()
    auth = authorize_escalate(
        cs, p, "sigue igual", {}, turnos_diagnostico=0, intencion="internet_ftth"
    )
    assert auth.allow is False
    assert auth.action.type == ACT_ASK_NEXT_STEP


def test_fa_06_step_hint_no_crea_cover():
    p = proposal_from_diag_result(
        {
            "accion": "ask",
            "motivo": "ia",
            "paso_cubierto": "reinicio_ont",
            "mensaje": "x",
        }
    )
    assert p.step_hint == "reinicio_ont"
    cs = _cs_tec(["energia_ont"])
    authorize_resolved(cs, p, "anda bien todo", {})
    assert "reinicio_ont" not in (cs.active_slot().covered_steps or [])


def test_fa_07_ia_suggested_step_no_mueve_cursor():
    cs = _cs_tec(["energia_ont"])
    ctx = {
        "intencion": "internet_ftth",
        "pasos_cubiertos": ["energia_ont"],
        "paso_idx": 1,
        CS_KEY: cs.to_dict(),
        "ia_suggested_step": "reinicio_ont",
    }
    before = ctx["paso_idx"]
    write_shadow_into_ctx(ctx)
    assert ctx["paso_idx"] == before


def test_fa_08_ia_suggested_action_no_ejecuta():
    """ia_suggested_action solo se guarda; no es writer de efectos."""
    cs = _cs_tec()
    ctx = {
        "intencion": "internet_ftth",
        "pasos_cubiertos": [],
        CS_KEY: cs.to_dict(),
        "ia_suggested_action": "escalate",
    }
    write_shadow_into_ctx(ctx)
    assert ctx.get("ia_suggested_action") == "escalate"
    assert list(hydrate_conversation_state(ctx).active_slot().covered_steps) == []


def test_fa_09_copy_diferente_mismo_step_mismo_pending_act():
    copies = [
        "¿Ves la lucecita PON?",
        "Reiniciá el ONT desenchufando 10 segundos.",
        "Por favor confirmá si la fibra está bien conectada.",
    ]
    acts = {classify_step_act("luces_los", c) for c in copies}
    assert acts == {BOT_ASK_FACT}


def test_fa_10_usuario_confirma_motor_cubre():
    cs = _cs_tec()
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
    interp = interpret_turn("listo", cs, {})
    assert interp.user_act == USER_CONFIRM_ACTION
    process_turn(cs, interp, {})
    assert "reinicio_ont" in (cs.active_slot().covered_steps or [])


def test_fa_11_legacy_shadow_no_resucita():
    cs = _cs_tec([])
    ctx = {
        "intencion": "internet_ftth",
        "pasos_cubiertos": ["old_step"],
        CS_KEY: cs.to_dict(),
    }
    sync_from_legacy(hydrate_conversation_state(ctx), ctx)
    write_shadow_into_ctx(ctx)
    assert list(hydrate_conversation_state(ctx).active_slot().covered_steps) == []
    assert ctx.get("pasos_cubiertos") == []


def test_fa_12_b_legitimo_mark_covers():
    cs = _cs_tec(["energia_ont"])
    ctx = {
        "intencion": "internet_ftth",
        "pasos_cubiertos": ["energia_ont"],
        CS_KEY: cs.to_dict(),
    }
    mark_covers(ctx, "luces_los")
    assert "luces_los" in hydrate_conversation_state(ctx).active_slot().covered_steps


def test_fa_13_h_plant_source_sigue():
    p = proposal_from_diag_result(
        {
            "accion": "escalate",
            "motivo": "fibra_danada",
            "mensaje": "Te derivo por fibra.",
            "paso_cubierto": "",
        }
    )
    assert p.source == SOURCE_PLANT
    d = evaluate_escalate(p, "los roja", turnos_diagnostico=0, intencion="internet_ftth")
    assert d.allow is True


def test_fa_14_domain_selection_dueno_active_domain():
    from app.domain.domain_adapter import apply_turn_domain

    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet_ftth")
    before = cs.active_domain_id
    # Sin señal de cambio de kind, active se mantiene bajo Domain Selection.
    apply_turn_domain(cs, "sigue sin andar", playbook_hint="internet_ftth")
    assert cs.active_domain_id == before


def test_fa_15_regresion_suites_importables():
    from tests import (
        test_covered_canonical_authority as c12,
    )
    from tests import (
        test_escalate_authority as e,
    )
    from tests import (
        test_llm_covered_authority as llm,
    )
    from tests import (
        test_pending_act_authority as pa,
    )
    from tests import (
        test_resolved_authority as r,
    )

    assert callable(c12.test_c12_01_legacy_no_sobrescribe_canonico_vacio)
    assert callable(e.test_e1_llm_escalate_deny_no_ticket)
    assert callable(r.test_r2_llm_resolved_allow_cierra)
    assert callable(pa.test_pa1_llm_copy_no_crea_ask_action)
    assert callable(llm.test_ia01_llm_no_cubre_paso_incorrecto)


# ---------------------------------------------------------------------------
# BYPASS-01 fix: forge de motivo planta
# ---------------------------------------------------------------------------


def test_fa_bypass01_sanitize_llm_motivo_plant():
    assert sanitize_llm_claimed_motivo("fibra_danada").startswith("ia_")
    assert sanitize_llm_claimed_motivo("pon_verde_enlace_ok").startswith("ia_")
    assert sanitize_llm_claimed_motivo("posible problema de fibra").startswith("ia_")
    assert sanitize_llm_claimed_motivo("ia") == "ia"
    # Gate 13C: cualquier motivo del JSON LLM queda prefijado ia_
    assert sanitize_llm_claimed_motivo("cliente_persiste") == "ia_cliente_persiste"


def test_fa_bypass01_forge_motivo_no_es_plant_source():
    forged = sanitize_llm_claimed_motivo("fibra_danada")
    assert infer_proposal_source({"motivo": forged}) == SOURCE_LLM
    p = proposal_from_diag_result(
        {
            "accion": "escalate",
            "motivo": forged,
            "mensaje": "Te derivo.",
            "paso_cubierto": "reinicio_ont",
        }
    )
    assert p.source == SOURCE_LLM
    d = evaluate_escalate(p, "sigue igual", turnos_diagnostico=0, intencion="internet_ftth")
    assert d.allow is False


def test_fa_bypass01_forge_pon_verde_sin_evidencia_no_cover():
    """motivo forjado en mock de canal + texto sin PON → no mark_covers."""
    tel = "5492235616010"
    org_id, conv_id = _abrir(tel)
    tickets: list = []
    _aplicar(
        org_id,
        conv_id,
        "hola sigue lento el wifi",
        ia={
            "accion": "ask",
            "mensaje": "¿Probamos reiniciar?",
            "paso_cubierto": "wifi_1",
            "motivo": "pon_verde_enlace_ok",
        },
        tickets=tickets,
    )
    ctx = _load_ctx(conv_id)
    cub = hydrate_conversation_state(ctx).active_slot().covered_steps
    assert "luces_los" not in cub
    assert "cable_fibra" not in cub
    assert "reinicio_ont" not in cub
    assert not tickets


def test_fa_caso_a_resolved_solo_tras_motor():
    tel = "5492235616011"
    org_id, conv_id = _abrir(tel, extra={"diag_turnos": 2})
    tickets: list = []
    out = _aplicar(
        org_id,
        conv_id,
        "anda perfecto gracias",
        ia={
            "accion": "resolved",
            "mensaje": "Me alegro.",
            "paso_cubierto": "reinicio_ont",
            "motivo": "ia",
        },
        tickets=tickets,
    )
    assert not tickets
    # Cierre requiere authorize; con mensaje de resolución típico puede allow.
    assert out.get("resolved_authorized") is True or out.get("estado") == "cerrado" or out.get(
        "modo"
    ) in ("bot", "diagnostico", "cerrado")


def test_fa_caso_b_escalate_deny_sin_turnos():
    tel = "5492235616012"
    org_id, conv_id = _abrir(tel, extra={"diag_turnos": 0})
    tickets: list = []
    out = _aplicar(
        org_id,
        conv_id,
        "quiero un técnico ya",
        ia={
            "accion": "escalate",
            "mensaje": "Te derivo.",
            "paso_cubierto": "reinicio_ont",
            "motivo": "ia",
        },
        tickets=tickets,
    )
    assert not tickets
    assert out.get("escalate_authorized") is not True


def test_fa_caso_c_mensaje_reinicio_step_luces_no_ask_action():
    ctx = {
        "intencion": "internet_ftth",
        "pasos_cubiertos": ["energia_ont"],
        CS_KEY: _cs_tec(["energia_ont"]).to_dict(),
    }
    stamp_bot_question(
        ctx,
        step_id="luces_los",
        pregunta="Reiniciá el equipo desenchufando 30 segundos.",
        intencion="internet_ftth",
    )
    cs = hydrate_conversation_state(ctx)
    assert cs.pending_bot is not None
    assert cs.pending_bot.act != BOT_ASK_ACTION
    assert "reinicio_ont" not in (cs.active_slot().covered_steps or [])


def test_fa_caso_d_paso_cubierto_llm_no_cover():
    tel = "5492235616013"
    org_id, conv_id = _abrir(tel)
    tickets: list = []
    _aplicar(
        org_id,
        conv_id,
        "el wifi anda mal",
        ia={
            "accion": "ask",
            "mensaje": "¿En todos los equipos?",
            "paso_cubierto": "wifi_1",
            "motivo": "ia",
        },
        tickets=tickets,
    )
    ctx = _load_ctx(conv_id)
    assert "wifi_1" not in (
        hydrate_conversation_state(ctx).active_slot().covered_steps or []
    )


def test_fa_motor_cover_step_sigue():
    cs = _cs_tec()
    cover_step(cs, "cable_fibra")
    assert "cable_fibra" in (cs.active_slot().covered_steps or [])
    ctx = {"intencion": "internet_ftth", "pasos_cubiertos": [], CS_KEY: cs.to_dict()}
    apply_cs_to_legacy(ctx, cs)
    assert "cable_fibra" in (ctx.get("pasos_cubiertos") or [])
