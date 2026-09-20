"""Gate 12B: writers B legacy migrados a mark_covers / replace_covers."""

from __future__ import annotations

from types import SimpleNamespace

from app.domain.conversation_motor import cover_step
from app.domain.conversation_state import (
    CS_KEY,
    KIND_TECNICO,
    hydrate_conversation_state,
    mark_covers,
    replace_covers,
    sync_from_legacy,
    write_shadow_into_ctx,
)
from app.domain.domain_lifecycle import cover_and_note, create_domain, new_conversation_state
from app.services.canal_abonado import (
    _enriquecer_cubiertos_luces,
    _note_pasos_cubiertos,
    _preservar_cubiertos_subplaybook,
    _reset_pasos_cubiertos,
)


def _ctx_ftth(covers: list[str] | None = None) -> dict:
    cs = new_conversation_state(turn=2)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet_ftth")
    if covers:
        cover_and_note(cs, steps=covers)
    return {
        "intencion": "internet_ftth",
        "pasos_cubiertos": list(covers or []),
        "paso_idx": 0,
        CS_KEY: cs.to_dict(),
    }


# ---------------------------------------------------------------------------
# C12B-01..08
# ---------------------------------------------------------------------------


def test_c12b_01_b_writer_canonico():
    """B que antes escribía legacy ahora produce CS.covered_steps."""
    ctx = _ctx_ftth(["energia_ont"])
    _note_pasos_cubiertos(ctx, "luces_los")
    cub = hydrate_conversation_state(ctx).active_slot().covered_steps
    assert "energia_ont" in cub
    assert "luces_los" in cub


def test_c12b_02_shadow_actualizado():
    ctx = _ctx_ftth(["energia_ont"])
    mark_covers(ctx, "luces_los")
    write_shadow_into_ctx(ctx)
    assert "luces_los" in (ctx.get("pasos_cubiertos") or [])
    assert "luces_los" in hydrate_conversation_state(ctx).active_slot().covered_steps


def test_c12b_03_no_perdida_por_shadow():
    ctx = _ctx_ftth([])
    mark_covers(ctx, "reinicio_ont")
    write_shadow_into_ctx(ctx)
    assert "reinicio_ont" in (ctx.get("pasos_cubiertos") or [])
    assert list(hydrate_conversation_state(ctx).active_slot().covered_steps) == [
        "reinicio_ont"
    ]


def test_c12b_04_no_resurrection():
    cs = new_conversation_state(turn=2)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet_ftth")
    ctx = {
        "intencion": "internet_ftth",
        "pasos_cubiertos": ["old_step"],
        "paso_idx": 0,
        CS_KEY: cs.to_dict(),
    }
    assert list(hydrate_conversation_state(ctx).active_slot().covered_steps) == []
    sync_from_legacy(hydrate_conversation_state(ctx), ctx)
    write_shadow_into_ctx(ctx)
    assert list(hydrate_conversation_state(ctx).active_slot().covered_steps) == []
    assert ctx.get("pasos_cubiertos") == []


def test_c12b_05_reset():
    ctx = _ctx_ftth(["energia_ont", "luces_los"])
    _reset_pasos_cubiertos(ctx)
    assert hydrate_conversation_state(ctx).active_slot().covered_steps == []
    assert ctx.get("pasos_cubiertos") == []


def test_c12b_06_motor_cover_step():
    cs = new_conversation_state(turn=2)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet_ftth")
    cover_step(cs, "cable_fibra")
    assert "cable_fibra" in (cs.active_slot().covered_steps or [])


def test_c12b_07_llm_hint_no_crea_cover():
    ctx = _ctx_ftth(["energia_ont"])
    ctx["ia_suggested_step"] = "reinicio_ont"
    ctx["paso_cubierto"] = "reinicio_ont"
    write_shadow_into_ctx(ctx)
    sync_from_legacy(hydrate_conversation_state(ctx), ctx)
    cub = hydrate_conversation_state(ctx).active_slot().covered_steps
    assert "reinicio_ont" not in cub
    assert "reinicio_ont" not in (ctx.get("pasos_cubiertos") or [])


def test_c12b_08_active_domain_id_inalterado():
    ctx = _ctx_ftth(["energia_ont"])
    before = hydrate_conversation_state(ctx).active_domain_id
    _note_pasos_cubiertos(ctx, "luces_los")
    replace_covers(ctx, ["energia_ont", "luces_los"])
    write_shadow_into_ctx(ctx)
    assert hydrate_conversation_state(ctx).active_domain_id == before


def test_c12b_preservar_subplaybook_replace_canonico():
    """Filter keep → replace_covers (antes asignaba ctx legacy)."""
    ctx = _ctx_ftth(["energia_ont", "luces_los", "zona_wifi"])
    pasos = [
        SimpleNamespace(id="energia_ont"),
        SimpleNamespace(id="luces_los"),
        SimpleNamespace(id="cable_fibra"),
    ]
    out = _preservar_cubiertos_subplaybook(ctx, pasos, "hola")
    cs = hydrate_conversation_state(ctx)
    assert "zona_wifi" not in (cs.active_slot().covered_steps or [])
    assert "energia_ont" in out
    assert "luces_los" in out
    assert ctx["pasos_cubiertos"] == list(cs.active_slot().covered_steps)


def test_c12b_enriquecer_luces_mark_covers():
    ctx = _ctx_ftth(["energia_ont"])
    pasos = [
        SimpleNamespace(id="energia_ont"),
        SimpleNamespace(id="luces_los"),
        SimpleNamespace(id="luces_ont"),
    ]
    out = _enriquecer_cubiertos_luces(ctx, pasos, "pon verde")
    cs = hydrate_conversation_state(ctx)
    assert "luces_los" in out
    assert "luces_ont" in out
    assert "luces_los" in (cs.active_slot().covered_steps or [])
    assert "luces_ont" in (cs.active_slot().covered_steps or [])
    assert ctx["pasos_cubiertos"] == list(cs.active_slot().covered_steps)
