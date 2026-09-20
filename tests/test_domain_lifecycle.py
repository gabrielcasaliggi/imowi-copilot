"""Fase 8A: contrato de lifecycle y resume de dominios.

No ejercita canal_abonado. Las operaciones viven en domain_lifecycle.
"""

from __future__ import annotations

import pytest

from app.domain.conversation_state import (
    KIND_ADMIN,
    KIND_COMERCIAL,
    KIND_TECNICO,
    ConversationState,
    LastBotAct,
    PendingBot,
    hydrate_conversation_state,
    project_legacy,
)
from app.domain.domain_lifecycle import (
    DomainCapacityError,
    DomainClosedError,
    DomainExistsError,
    DomainKindError,
    activate_domain,
    active_facts_map,
    apply_domain_signal,
    close_domain,
    cover_and_note,
    create_domain,
    facts_for,
    invalidate_pending,
    invalidate_pending_from_text,
    kind_from_user_signal,
    new_conversation_state,
    pause_domain,
    refine_playbook,
    resume_domain,
    set_slot_pending,
)


def _tec_ftth() -> ConversationState:
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet_ftth")
    return cs


# ---------------------------------------------------------------------------
# D1 create
# ---------------------------------------------------------------------------


def test_d1_create_technical_domain_active():
    cs = new_conversation_state()
    slot = create_domain(cs, kind=KIND_TECNICO, playbook="internet_ftth")
    assert slot.id == "tec-1"
    assert slot.kind == KIND_TECNICO
    assert slot.status == "active"
    assert cs.active_domain_id == "tec-1"
    assert cs.slot("tec-1") is slot


# ---------------------------------------------------------------------------
# D2 pause
# ---------------------------------------------------------------------------


def test_d2_pause_preserves_facts_and_covers():
    cs = _tec_ftth()
    cover_and_note(
        cs,
        steps=["energia_ont", "luces_los"],
        facts={"luces_ont": "pon_verde"},
    )
    slot = pause_domain(cs, "tec-1")
    assert slot.status == "paused"
    assert slot.covered_steps == ["energia_ont", "luces_los"]
    assert active_facts_map(cs, "tec-1")["luces_ont"] == "pon_verde"
    assert cs.active_slot() is None


# ---------------------------------------------------------------------------
# D3 resume
# ---------------------------------------------------------------------------


def test_d3_resume_same_facts_and_covers():
    cs = _tec_ftth()
    cover_and_note(cs, steps=["energia_ont"], facts={"tecnologia_acceso": "internet_ftth"})
    pause_domain(cs, "tec-1")
    slot = resume_domain(cs, "tec-1")
    assert slot.status == "active"
    assert slot.covered_steps == ["energia_ont"]
    assert active_facts_map(cs, "tec-1")["tecnologia_acceso"] == "internet_ftth"


# ---------------------------------------------------------------------------
# D4 technical → billing
# ---------------------------------------------------------------------------


def test_d4_cuanto_debo_pauses_tec_activates_adm():
    cs = _tec_ftth()
    cover_and_note(cs, steps=["energia_ont"], facts={"luces_ont": "pon_verde"})
    assert kind_from_user_signal("¿Cuánto debo?") == KIND_ADMIN
    slot = apply_domain_signal(cs, "¿Cuánto debo?", playbook="facturacion")
    assert slot is not None
    assert slot.kind == KIND_ADMIN
    assert slot.status == "active"
    tec = cs.slot("tec-1")
    assert tec is not None
    assert tec.status == "paused"
    assert "energia_ont" in tec.covered_steps
    assert active_facts_map(cs, "tec-1")["luces_ont"] == "pon_verde"


# ---------------------------------------------------------------------------
# D5 billing → technical
# ---------------------------------------------------------------------------


def test_d5_sigo_sin_internet_resumes_tec():
    cs = _tec_ftth()
    cover_and_note(cs, steps=["energia_ont", "luces_los"], facts={"luces_ont": "pon_verde"})
    apply_domain_signal(cs, "¿Cuánto debo?", playbook="facturacion")
    slot = apply_domain_signal(cs, "Sigo sin internet.")
    assert slot is not None
    assert slot.id == "tec-1"
    assert slot.status == "active"
    adm = cs.slot("adm-1")
    assert adm is not None
    assert adm.status == "paused"
    assert slot.covered_steps == ["energia_ont", "luces_los"]
    assert active_facts_map(cs, "tec-1")["luces_ont"] == "pon_verde"


# ---------------------------------------------------------------------------
# D6 resume is not restart
# ---------------------------------------------------------------------------


def test_d6_resume_is_not_restart():
    cs = _tec_ftth()
    cover_and_note(
        cs,
        steps=["energia_ont", "luces_los", "reinicio_ont"],
        facts={"luces_ont": "pon_verde", "accion_reinicio_ont": "realizada"},
    )
    prev_facts = dict(active_facts_map(cs, "tec-1"))
    prev_cov = list(cs.slot("tec-1").covered_steps)
    pause_domain(cs, "tec-1")
    create_domain(cs, kind=KIND_ADMIN, playbook="facturacion")
    resume_domain(cs, "tec-1")
    assert active_facts_map(cs, "tec-1") == prev_facts
    assert cs.slot("tec-1").covered_steps == prev_cov
    assert cs.slot("tec-1").playbook == "internet_ftth"


# ---------------------------------------------------------------------------
# D7 pending preserved on pause
# ---------------------------------------------------------------------------


def test_d7_pending_stays_on_tec_slot():
    cs = _tec_ftth()
    set_slot_pending(
        cs,
        pending_bot=PendingBot(
            act="ASK_ACTION",
            step_id="reinicio_ont",
            referent="reinicio_ont",
            turn=cs.turn,
        ),
        last_bot_act=LastBotAct(
            act="ASK_ACTION",
            step_id="reinicio_ont",
            referent="reinicio_ont",
            turn=cs.turn,
        ),
    )
    apply_domain_signal(cs, "¿Cuánto debo?", playbook="facturacion")
    tec = cs.slot("tec-1")
    assert tec is not None
    assert tec.pending_bot is not None
    assert tec.pending_bot.step_id == "reinicio_ont"
    assert tec.pending_bot.domain_id == "tec-1"
    adm = cs.active_slot()
    assert adm is not None
    assert adm.kind == KIND_ADMIN
    assert adm.pending_bot is None or adm.pending_bot.step_id != "reinicio_ont"


# ---------------------------------------------------------------------------
# D8 admin pending independent
# ---------------------------------------------------------------------------


def test_d8_admin_pending_independent_of_tec():
    cs = _tec_ftth()
    set_slot_pending(
        cs,
        pending_bot=PendingBot(act="ASK_ACTION", step_id="reinicio_ont", referent="reinicio_ont"),
    )
    apply_domain_signal(cs, "¿Cuánto debo?", playbook="facturacion")
    set_slot_pending(
        cs,
        pending_bot=PendingBot(act="ASK_FACT", step_id="triaje_motivo", referent="saldo"),
    )
    tec = cs.slot("tec-1")
    adm = cs.slot("adm-1")
    assert tec.pending_bot.step_id == "reinicio_ont"
    assert adm.pending_bot.step_id == "triaje_motivo"
    assert tec.pending_bot.step_id != adm.pending_bot.step_id
    assert cs.pending_bot is not None
    assert cs.pending_bot.step_id == "triaje_motivo"
    assert cs.pending_bot.domain_id == "adm-1"


# ---------------------------------------------------------------------------
# D9 resume pending
# ---------------------------------------------------------------------------


def test_d9_resume_restores_valid_pending():
    cs = _tec_ftth()
    set_slot_pending(
        cs,
        pending_bot=PendingBot(act="ASK_ACTION", step_id="reinicio_ont", referent="reinicio_ont"),
    )
    apply_domain_signal(cs, "¿Cuánto debo?", playbook="facturacion")
    resume_domain(cs, "tec-1")
    assert cs.pending_bot is not None
    assert cs.pending_bot.step_id == "reinicio_ont"
    assert cs.pending_bot.status == "open"


def test_d9_resume_skips_covered_pending():
    cs = _tec_ftth()
    set_slot_pending(
        cs,
        pending_bot=PendingBot(act="ASK_ACTION", step_id="reinicio_ont", referent="reinicio_ont"),
    )
    cover_and_note(cs, steps=["energia_ont", "luces_los", "reinicio_ont"])
    pause_domain(cs, "tec-1")
    create_domain(cs, kind=KIND_ADMIN, playbook="facturacion")
    resume_domain(cs, "tec-1")
    assert cs.pending_bot is not None
    assert cs.pending_bot.step_id != "reinicio_ont"
    assert cs.pending_bot.step_id == "cable_fibra"


# ---------------------------------------------------------------------------
# D10 pending obsolete
# ---------------------------------------------------------------------------


def test_d10_pending_invalidated_when_ont_replaced():
    cs = _tec_ftth()
    set_slot_pending(
        cs,
        pending_bot=PendingBot(act="ASK_ACTION", step_id="reinicio_ont", referent="reinicio_ont"),
    )
    assert invalidate_pending_from_text(cs, "Ya vino un técnico y cambió la ONT.")
    # El pending anterior no se reutiliza: se reconcilia al primer paso real.
    assert cs.pending_bot is not None
    assert cs.pending_bot.step_id != "reinicio_ont"
    assert cs.pending_bot.status == "open"
    assert active_facts_map(cs, "tec-1").get("ont_reemplazada") is True


def test_d10_invalidate_explicit():
    cs = _tec_ftth()
    set_slot_pending(
        cs,
        pending_bot=PendingBot(act="ASK_ACTION", step_id="reinicio_ont", referent="reinicio_ont"),
    )
    pause_domain(cs, "tec-1")
    invalidate_pending(cs, "tec-1")
    assert cs.slot("tec-1").pending_bot.status == "invalidated"


# ---------------------------------------------------------------------------
# D11 facts isolated
# ---------------------------------------------------------------------------


def test_d11_facts_isolated_by_domain():
    cs = _tec_ftth()
    cover_and_note(cs, steps=[], facts={"alcance_wifi": "uno"})
    apply_domain_signal(cs, "¿Cuánto debo?", playbook="facturacion")
    cover_and_note(cs, steps=[], facts={"saldo": 50000})
    tec_facts = active_facts_map(cs, "tec-1")
    adm_facts = active_facts_map(cs, "adm-1")
    assert tec_facts.get("alcance_wifi") == "uno"
    assert "saldo" not in tec_facts
    assert adm_facts.get("saldo") == 50000
    assert "alcance_wifi" not in adm_facts
    assert all(f.domain_id != "adm-1" for f in facts_for(cs, "tec-1"))


# ---------------------------------------------------------------------------
# D12 refine
# ---------------------------------------------------------------------------


def test_d12_refine_keeps_domain_id_and_facts():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet")
    cover_and_note(cs, steps=["tipo_acceso"], facts={"sintoma": "sin_enlace"})
    slot = refine_playbook(cs, "internet_ftth")
    assert slot.id == "tec-1"
    assert slot.playbook == "internet_ftth"
    assert active_facts_map(cs, "tec-1")["sintoma"] == "sin_enlace"
    with pytest.raises(DomainKindError):
        refine_playbook(cs, "facturacion")


# ---------------------------------------------------------------------------
# D13 two domains / stack
# ---------------------------------------------------------------------------


def test_d13_two_domains_unique_ids_valid_stack():
    cs = _tec_ftth()
    create_domain(cs, kind=KIND_ADMIN, playbook="facturacion")
    ids = [d.id for d in cs.domains]
    assert ids == list(dict.fromkeys(ids))
    assert set(ids) == {"tec-1", "adm-1"}
    assert all(i in {d.id for d in cs.domains} for i in cs.domain_stack)
    assert cs.domain_stack[0] == "adm-1"


# ---------------------------------------------------------------------------
# D14 max three / fourth rejected
# ---------------------------------------------------------------------------


def test_d14_three_kinds_ok_fourth_rejected():
    cs = new_conversation_state()
    create_domain(cs, kind=KIND_TECNICO, playbook="wifi")
    create_domain(cs, kind=KIND_ADMIN, playbook="facturacion")
    create_domain(cs, kind=KIND_COMERCIAL, playbook="alta_plan")
    assert len(cs.domains) == 3
    with pytest.raises(DomainKindError):
        create_domain(cs, kind="otro")
    with pytest.raises(DomainExistsError):
        create_domain(cs, kind=KIND_TECNICO, playbook="internet_ftth")
    paused = [d for d in cs.domains if d.status == "paused"]
    assert len(paused) == 2
    assert all(d.id in ("tec-1", "adm-1", "com-1") for d in cs.domains)


def test_d14_capacity_guard():
    cs = new_conversation_state()
    create_domain(cs, kind=KIND_TECNICO)
    create_domain(cs, kind=KIND_ADMIN)
    create_domain(cs, kind=KIND_COMERCIAL)
    # no hay 4º kind válido; el guard de capacidad queda cubierto por exists/kind
    with pytest.raises((DomainCapacityError, DomainKindError, DomainExistsError)):
        create_domain(cs, kind=KIND_TECNICO)


# ---------------------------------------------------------------------------
# D15 one slot per kind
# ---------------------------------------------------------------------------


def test_d15_tech_signal_reuses_tec1_never_tec2():
    cs = _tec_ftth()
    apply_domain_signal(cs, "¿Cuánto debo?", playbook="facturacion")
    apply_domain_signal(cs, "Sigo sin internet.")
    tecs = [d for d in cs.domains if d.kind == KIND_TECNICO]
    assert len(tecs) == 1
    assert tecs[0].id == "tec-1"
    with pytest.raises(DomainExistsError):
        create_domain(cs, kind=KIND_TECNICO, playbook="wifi")


# ---------------------------------------------------------------------------
# D16 close
# ---------------------------------------------------------------------------


def test_d16_closed_does_not_resume():
    cs = _tec_ftth()
    apply_domain_signal(cs, "¿Cuánto debo?", playbook="facturacion")
    closed = close_domain(cs, "adm-1")
    assert closed.status == "closed"
    with pytest.raises(DomainClosedError):
        resume_domain(cs, "adm-1")
    with pytest.raises(DomainClosedError):
        apply_domain_signal(cs, "¿Cuánto debo?", playbook="facturacion")


# ---------------------------------------------------------------------------
# D17 legacy projection
# ---------------------------------------------------------------------------


def test_d17_project_legacy_active_admin_keeps_paused_tec():
    cs = _tec_ftth()
    cover_and_note(cs, steps=["energia_ont"], facts={"luces_ont": "pon_verde"})
    apply_domain_signal(cs, "¿Cuánto debo?", playbook="facturacion")
    proj = project_legacy(cs)
    assert proj["intencion"] in ("facturacion", "facturacion_reclamo") or proj["intencion"].startswith(
        "facturacion"
    )
    assert "luces_ont" not in (proj.get("hechos") or {})
    assert cs.slot("tec-1") is not None
    assert cs.slot("tec-1").status == "paused"
    assert "energia_ont" in cs.slot("tec-1").covered_steps
    assert proj.get("intencion_tecnica_pendiente") == "internet_ftth"


# ---------------------------------------------------------------------------
# D18 FTTH → factura → FTTH
# ---------------------------------------------------------------------------


def test_d18_ftth_billing_ftth_full_resume():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet")
    refine_playbook(cs, "internet_ftth")
    cover_and_note(
        cs,
        steps=["energia_ont", "luces_los"],
        facts={"luces_ont": "pon_verde", "tecnologia_acceso": "internet_ftth"},
    )
    set_slot_pending(
        cs,
        pending_bot=PendingBot(act="ASK_ACTION", step_id="reinicio_ont", referent="reinicio_ont"),
        last_bot_act=LastBotAct(act="ASK_ACTION", step_id="reinicio_ont", referent="reinicio_ont"),
    )
    cover_and_note(
        cs,
        steps=["reinicio_ont"],
        facts={"accion_reinicio_ont": "realizada_sin_mejora", "resultado_accion": "sin_mejora"},
    )
    apply_domain_signal(cs, "¿Cuánto debo?", playbook="facturacion")
    cover_and_note(cs, steps=["triaje_motivo"], facts={"saldo": 0})
    close_domain(cs, "adm-1")
    resume_domain(cs, "tec-1")
    tec = cs.slot("tec-1")
    assert tec.status == "active"
    assert tec.playbook == "internet_ftth"
    assert "energia_ont" in tec.covered_steps
    assert "luces_los" in tec.covered_steps
    assert "reinicio_ont" in tec.covered_steps
    facts = active_facts_map(cs, "tec-1")
    assert facts["luces_ont"] == "pon_verde"
    assert facts["accion_reinicio_ont"] == "realizada_sin_mejora"
    assert "saldo" not in facts
    assert cs.pending_bot is not None
    assert cs.pending_bot.step_id != "reinicio_ont"
    tecs = [d for d in cs.domains if d.kind == KIND_TECNICO]
    assert len(tecs) == 1


# ---------------------------------------------------------------------------
# last_bot_act ligado al dominio activo
# ---------------------------------------------------------------------------


def test_last_bot_act_follows_active_domain():
    cs = _tec_ftth()
    set_slot_pending(
        cs,
        last_bot_act=LastBotAct(act="ASK_ACTION", step_id="reinicio_ont", referent="reinicio_ont"),
    )
    apply_domain_signal(cs, "¿Cuánto debo?", playbook="facturacion")
    set_slot_pending(
        cs,
        last_bot_act=LastBotAct(act="ASK_FACT", step_id="triaje_motivo", referent="saldo"),
    )
    assert cs.last_bot_act is not None
    assert cs.last_bot_act.domain_id == "adm-1"
    assert cs.last_bot_act.step_id == "triaje_motivo"
    assert cs.slot("tec-1").last_bot_act.step_id == "reinicio_ont"
    resume_domain(cs, "tec-1")
    assert cs.last_bot_act.domain_id == "tec-1"
    assert cs.last_bot_act.step_id == "reinicio_ont"


def test_multi_tema_does_not_destroy_either_domain():
    cs = _tec_ftth()
    cover_and_note(cs, steps=["energia_ont"], facts={"luces_ont": "pon_rojo"})
    apply_domain_signal(cs, "no tengo internet y además cuánto debo", playbook="facturacion")
    assert cs.slot("tec-1") is not None
    assert cs.slot("adm-1") is not None
    assert {d.status for d in cs.domains} <= {"active", "paused"}
    assert len([d for d in cs.domains if d.status == "active"]) == 1


# ---------------------------------------------------------------------------
# Replay histórico como contrato de cs (sin canal_abonado — eso es Fase 8B)
# ---------------------------------------------------------------------------


def test_replay_switch_01_lifecycle_resumes_ftth():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet")
    refine_playbook(cs, "internet_ftth")
    cover_and_note(cs, steps=["energia_ont"], facts={"tecnologia_acceso": "internet_ftth"})
    apply_domain_signal(cs, "¿cuánto debo?", playbook="facturacion")
    cover_and_note(cs, steps=["triaje_motivo"], facts={"pago_informado": True})
    apply_domain_signal(cs, "sigue sin internet")
    tec = cs.slot("tec-1")
    adm = cs.slot("adm-1")
    assert tec.status == "active"
    assert adm.status == "paused"
    assert "energia_ont" in tec.covered_steps
    assert active_facts_map(cs, "tec-1")["tecnologia_acceso"] == "internet_ftth"
    assert "pago_informado" not in active_facts_map(cs, "tec-1")


def test_replay_switch_02_lifecycle_resumes_billing():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_ADMIN, playbook="facturacion_reclamo")
    cover_and_note(cs, steps=["triaje_motivo"], facts={"mes_facturacion": "agosto"})
    apply_domain_signal(cs, "no me anda el wifi en la tablet", playbook="wifi")
    cover_and_note(cs, steps=["zona_wifi"], facts={"alcance_wifi": "uno"})
    apply_domain_signal(cs, "volvamos a la factura, por qué subió?")
    assert cs.active_slot().id == "adm-1"
    assert cs.slot("tec-1").status == "paused"
    assert active_facts_map(cs, "adm-1")["mes_facturacion"] == "agosto"
    assert active_facts_map(cs, "tec-1")["alcance_wifi"] == "uno"


def test_replay_ftth_01_stays_in_same_technical_slot():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet")
    refine_playbook(cs, "internet_ftth")
    cover_and_note(
        cs,
        steps=["energia_ont", "luces_los", "reinicio_ont"],
        facts={"luces_ont": "pon_verde", "accion_reinicio_ont": "realizada_sin_mejora"},
    )
    assert len(cs.domains) == 1
    assert cs.domains[0].id == "tec-1"
    assert cs.domains[0].playbook == "internet_ftth"
    assert "reinicio_ont" in cs.domains[0].covered_steps


def test_replay_t70_howto_does_not_spawn_second_tech_domain():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="wifi")
    cover_and_note(
        cs, steps=["zona_wifi", "alcance_wifi"], facts={"dispositivo_afectado": "tablet"}
    )
    apply_domain_signal(cs, "como conecto la tablet por cable de red?")
    tecs = [d for d in cs.domains if d.kind == KIND_TECNICO]
    assert len(tecs) == 1
    assert tecs[0].id == "tec-1"
    assert active_facts_map(cs, "tec-1")["dispositivo_afectado"] == "tablet"


def test_replay_t46_comercial_single_slot():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_COMERCIAL, playbook="alta_plan")
    cover_and_note(cs, steps=["cobertura_zona"], facts={"localidad": "batan"})
    assert len(cs.domains) == 1
    assert cs.domains[0].id == "com-1"
    assert cs.domains[0].kind == KIND_COMERCIAL


def test_json_model_tec_paused_adm_active():
    cs = _tec_ftth()
    cover_and_note(
        cs,
        steps=["energia_ont", "luces_los", "reinicio_ont"],
        facts={"luces_ont": "pon_verde", "accion_reinicio_ont": "realizada"},
    )
    set_slot_pending(
        cs,
        pending_bot=PendingBot(act="ASK_ACTION", step_id="cable_fibra", referent="cable_fibra"),
        last_bot_act=LastBotAct(act="ASK_ACTION", step_id="cable_fibra", referent="cable_fibra"),
    )
    apply_domain_signal(cs, "¿Cuánto debo?", playbook="facturacion")
    set_slot_pending(
        cs,
        pending_bot=PendingBot(act="ASK_FACT", step_id="triaje_motivo", referent="saldo"),
        last_bot_act=LastBotAct(act="ASK_FACT", step_id="triaje_motivo", referent="saldo"),
    )
    cover_and_note(cs, steps=[], facts={"saldo": 45000, "mes_facturacion": "agosto"})
    blob = cs.to_dict()
    restored = hydrate_conversation_state({"cs": blob})
    assert restored.slot("tec-1").status == "paused"
    assert restored.slot("adm-1").status == "active"
    assert restored.slot("tec-1").pending_bot.step_id == "cable_fibra"
    assert restored.slot("adm-1").pending_bot.step_id == "triaje_motivo"
    assert restored.last_bot_act.domain_id == "adm-1"
    assert restored.slot("tec-1").last_bot_act.step_id == "cable_fibra"
    proj = project_legacy(restored)
    assert proj["intencion"] == "facturacion"
    assert proj["intencion_tecnica_pendiente"] == "internet_ftth"
    assert "luces_ont" not in proj["hechos"]
    assert proj["hechos"]["saldo"] == 45000


def test_d3_activate_alias_of_resume():
    cs = _tec_ftth()
    pause_domain(cs, "tec-1")
    slot = activate_domain(cs, "tec-1")
    assert slot.status == "active"
    assert cs.active_domain_id == "tec-1"
