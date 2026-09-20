"""Gate 12: covered_steps canónico; legacy pasos_cubiertos es proyección."""

from __future__ import annotations

from app.domain.conversation_motor import (
    BOT_ASK_ACTION,
    USER_CONFIRM_ACTION,
    apply_cs_to_legacy,
    classify_step_act,
    cover_step,
    interpret_turn,
    process_turn,
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


def _cs_with_covers(steps: list[str]):
    cs = new_conversation_state(turn=2)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet_ftth")
    if steps:
        cover_and_note(cs, steps=steps)
    return cs


# ---------------------------------------------------------------------------
# C12-01..06 canonicidad / shadow
# ---------------------------------------------------------------------------


def test_c12_01_legacy_no_sobrescribe_canonico_vacio():
    cs = _cs_with_covers([])
    ctx = {
        "intencion": "internet_ftth",
        "pasos_cubiertos": ["wifi_1", "zona_wifi"],
        "paso_idx": 0,
        CS_KEY: cs.to_dict(),
    }
    cs2 = hydrate_conversation_state(ctx)
    assert list(cs2.active_slot().covered_steps) == []
    sync_from_legacy(cs2, ctx)
    assert list(cs2.active_slot().covered_steps) == []


def test_c12_02_shadow_proyecta_canonico():
    cs = _cs_with_covers(["zona_wifi"])
    ctx = {
        "intencion": "internet_ftth",
        "pasos_cubiertos": [],
        "paso_idx": 0,
        CS_KEY: cs.to_dict(),
    }
    write_shadow_into_ctx(ctx)
    assert ctx["pasos_cubiertos"] == ["zona_wifi"]
    assert list(hydrate_conversation_state(ctx).active_slot().covered_steps) == [
        "zona_wifi"
    ]


def test_c12_03_no_resurrection_tras_decision_motor():
    cs = _cs_with_covers([])
    # Stale legacy tras Motor que dejó covers vacíos.
    ctx = {
        "intencion": "internet_ftth",
        "pasos_cubiertos": ["wifi_1"],
        "paso_idx": 1,
        CS_KEY: cs.to_dict(),
    }
    write_shadow_into_ctx(ctx)
    assert list(hydrate_conversation_state(ctx).active_slot().covered_steps) == []
    assert ctx.get("pasos_cubiertos") == []


def test_c12_04_cover_motor_permanece():
    cs = _cs_with_covers([])
    cover_step(cs, "reinicio_ont")
    ctx = {"intencion": "internet_ftth", "pasos_cubiertos": [], CS_KEY: cs.to_dict()}
    apply_cs_to_legacy(ctx, cs)
    assert "reinicio_ont" in (ctx.get("pasos_cubiertos") or [])
    write_shadow_into_ctx(ctx)
    assert "reinicio_ont" in hydrate_conversation_state(ctx).active_slot().covered_steps


def test_c12_05_cover_b_mark_covers_permanece():
    cs = _cs_with_covers(["energia_ont"])
    ctx = {
        "intencion": "internet_ftth",
        "pasos_cubiertos": ["energia_ont"],
        CS_KEY: cs.to_dict(),
    }
    mark_covers(ctx, "luces_los")
    assert "luces_los" in (ctx.get("pasos_cubiertos") or [])
    write_shadow_into_ctx(ctx)
    cub = hydrate_conversation_state(ctx).active_slot().covered_steps
    assert "energia_ont" in cub
    assert "luces_los" in cub


def test_c12_06_divergencia_gana_conversation_state():
    cs = _cs_with_covers(["energia_ont"])
    ctx = {
        "intencion": "internet_ftth",
        "pasos_cubiertos": ["energia_ont", "wifi_fantasma", "zona_wifi"],
        CS_KEY: cs.to_dict(),
    }
    write_shadow_into_ctx(ctx)
    assert ctx["pasos_cubiertos"] == ["energia_ont"]
    assert list(hydrate_conversation_state(ctx).active_slot().covered_steps) == [
        "energia_ont"
    ]


def test_c12_07_active_domain_id_inalterado():
    cs = _cs_with_covers([])
    ctx = {
        "intencion": "internet_ftth",
        "pasos_cubiertos": ["zona_wifi"],
        CS_KEY: cs.to_dict(),
    }
    before = hydrate_conversation_state(ctx).active_domain_id
    write_shadow_into_ctx(ctx)
    sync_from_legacy(hydrate_conversation_state(ctx), ctx)
    assert hydrate_conversation_state(ctx).active_domain_id == before == "tec-1"


def test_c12_08_resolved_suite_importable():
    from tests import test_resolved_authority as tr

    assert callable(tr.test_r2_llm_resolved_allow_cierra)


def test_c12_09_escalate_suite_importable():
    from tests import test_escalate_authority as te

    assert callable(te.test_e1_policy_deny_llm_sin_turnos)


def test_c12_10_pending_act_suite_importable():
    from tests import test_pending_act_authority as tp

    assert callable(tp.test_pa1_llm_copy_no_crea_ask_action)
    assert classify_step_act("luces_los", "Reiniciemos el equipo ahora.") != BOT_ASK_ACTION


def test_c12_11_confirm_action_sigue():
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
    interp = interpret_turn("listo", cs, {})
    assert interp.user_act == USER_CONFIRM_ACTION
    process_turn(cs, interp, {})
    assert "reinicio_ont" in (cs.active_slot().covered_steps or [])


def test_c12_12_copy_llm_no_crea_covers():
    cs = _cs_with_covers(["energia_ont"])
    ctx = {
        "intencion": "internet_ftth",
        "pasos_cubiertos": ["energia_ont"],
        CS_KEY: cs.to_dict(),
        "ia_suggested_step": "reinicio_ont",
    }
    # Solo sync/shadow: el hint LLM no escribe covers.
    write_shadow_into_ctx(ctx)
    assert "reinicio_ont" not in (
        hydrate_conversation_state(ctx).active_slot().covered_steps or []
    )
    assert "reinicio_ont" not in (ctx.get("pasos_cubiertos") or [])
