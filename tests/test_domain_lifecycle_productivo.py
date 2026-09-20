"""Fase 8B: lifecycle en el flujo productivo (canal_abonado)."""

from __future__ import annotations

from sqlalchemy import select

from app.domain.conversation_motor import USER_ASK_CAUSE, apply_cs_to_legacy, interpret_turn
from app.domain.conversation_state import (
    KIND_ADMIN,
    KIND_COMERCIAL,
    KIND_TECNICO,
    LastBotAct,
    PendingBot,
    hydrate_conversation_state,
    project_legacy,
    sync_from_legacy,
)
from app.domain.domain_adapter import apply_turn_domain
from app.domain.domain_lifecycle import (
    apply_domain_signal,
    close_domain,
    cover_and_note,
    create_domain,
    new_conversation_state,
    resume_domain,
    set_slot_pending,
)
from app.estate import canal_repo as crepo
from app.estate.database import get_session_factory
from app.estate.models import Abonado, ConversacionCanal, Organization
from app.services.canal_abonado import procesar_mensaje_entrante

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


def _msg(org_id: str, tel: str, texto: str) -> dict:
    Session = get_session_factory()
    with Session() as db:
        return procesar_mensaje_entrante(
            db, org_id, telefono=tel, texto=texto, canal=_CANAL, usar_llama=False
        )


def _load_ctx(conv_id: str) -> dict:
    Session = get_session_factory()
    with Session() as db:
        conv = db.get(ConversacionCanal, conv_id)
        assert conv is not None
        return crepo.get_contexto(conv)


def _seed_tec_ftth(*, pending_step: str = "cable_fibra") -> dict:
    cs = new_conversation_state(turn=6)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet_ftth")
    cover_and_note(
        cs,
        steps=["energia_ont", "luces_los", "reinicio_ont"],
        facts={
            "luces_ont": "pon_verde",
            "accion_reinicio_ont": "realizada_sin_mejora",
            "alcance_wifi": "uno",
        },
    )
    set_slot_pending(
        cs,
        pending_bot=PendingBot(
            act="ASK_ACTION", step_id=pending_step, referent=pending_step
        ),
        last_bot_act=LastBotAct(
            act="ASK_ACTION", step_id=pending_step, referent=pending_step
        ),
    )
    ctx: dict = {
        "intencion": "internet_ftth",
        "paso_idx": 3,
        "pasos_cubiertos": ["energia_ont", "luces_los", "reinicio_ont"],
        "hechos": {
            "luces_ont": "pon_verde",
            "accion_reinicio_ont": "realizada_sin_mejora",
            "alcance_wifi": "uno",
        },
    }
    apply_cs_to_legacy(ctx, cs)
    return ctx


def _tec_adm_from_seed(ctx: dict) -> tuple:
    cs = hydrate_conversation_state(ctx)
    return cs.slot("tec-1"), cs.slot("adm-1"), cs


# ---------------------------------------------------------------------------
# B1 technical → administrative
# ---------------------------------------------------------------------------


def test_b1_cuanto_debo_pauses_tec_activates_adm():
    org_id, conv_id = _abrir("5492235612001", extra=_seed_tec_ftth())
    out = _msg(org_id, "5492235612001", "¿Cuánto debo?")
    assert out.get("ok") is not False
    ctx = _load_ctx(conv_id)
    tec, adm, cs = _tec_adm_from_seed(ctx)
    assert tec is not None and tec.status == "paused"
    assert adm is not None and adm.status == "active"
    assert "energia_ont" in tec.covered_steps
    assert "luces_los" in tec.covered_steps
    facts = {f.key: f.value for f in cs.facts if f.domain_id == "tec-1" and f.status == "active"}
    assert facts.get("luces_ont") == "pon_verde"


# ---------------------------------------------------------------------------
# B2 administrative → technical
# ---------------------------------------------------------------------------


def test_b2_sigo_sin_internet_resumes_tec():
    org_id, conv_id = _abrir("5492235612002", extra=_seed_tec_ftth())
    _msg(org_id, "5492235612002", "¿Cuánto debo?")
    _msg(org_id, "5492235612002", "Sigo sin internet.")
    ctx = _load_ctx(conv_id)
    tec, adm, cs = _tec_adm_from_seed(ctx)
    assert tec is not None and tec.status == "active"
    assert adm is not None and adm.status == "paused"
    assert "energia_ont" in tec.covered_steps
    facts = {f.key: f.value for f in cs.facts if f.domain_id == "tec-1" and f.status == "active"}
    assert facts.get("luces_ont") == "pon_verde"


# ---------------------------------------------------------------------------
# B3 resume no reinicia
# ---------------------------------------------------------------------------


def test_b3_resume_does_not_restart_ftth():
    org_id, conv_id = _abrir("5492235612003", extra=_seed_tec_ftth())
    _msg(org_id, "5492235612003", "¿Cuánto debo?")
    out = _msg(org_id, "5492235612003", "Sigo sin internet.")
    resp = (out.get("respuesta") or "").lower()
    assert "cajita blanca" not in resp
    assert "luz pon" not in resp
    assert "desenchufá ont" not in resp and "desenchufa ont" not in resp
    ctx = _load_ctx(conv_id)
    tec, _adm, _cs = _tec_adm_from_seed(ctx)
    assert tec.status == "active"
    assert "energia_ont" in tec.covered_steps
    assert "reinicio_ont" in tec.covered_steps


# ---------------------------------------------------------------------------
# B4 pending resume
# ---------------------------------------------------------------------------


def test_b4_resume_restores_valid_pending():
    org_id, conv_id = _abrir("5492235612004", extra=_seed_tec_ftth(pending_step="cable_fibra"))
    _msg(org_id, "5492235612004", "¿Cuánto debo?")
    _msg(org_id, "5492235612004", "Sigo sin internet.")
    ctx = _load_ctx(conv_id)
    cs = hydrate_conversation_state(ctx)
    tec = cs.slot("tec-1")
    pending = cs.pending_bot or (tec.pending_bot if tec else None)
    assert pending is not None
    assert pending.step_id == "cable_fibra"


# ---------------------------------------------------------------------------
# B5 pending ya cubierto
# ---------------------------------------------------------------------------


def test_b5_resume_skips_covered_pending():
    extra = _seed_tec_ftth(pending_step="cable_fibra")
    cs0 = hydrate_conversation_state(extra)
    cover_and_note(cs0, steps=["cable_fibra"])
    apply_cs_to_legacy(extra, cs0)
    org_id, conv_id = _abrir("5492235612005", extra=extra)
    _msg(org_id, "5492235612005", "¿Cuánto debo?")
    _msg(org_id, "5492235612005", "Sigo sin internet.")
    ctx = _load_ctx(conv_id)
    cs = hydrate_conversation_state(ctx)
    pending = cs.pending_bot
    assert pending is not None
    assert pending.step_id != "cable_fibra"


# ---------------------------------------------------------------------------
# B6 facts separados
# ---------------------------------------------------------------------------


def test_b6_facts_isolated_across_switches():
    extra = _seed_tec_ftth()
    org_id, conv_id = _abrir("5492235612006", extra=extra)
    _msg(org_id, "5492235612006", "¿Cuánto debo?")
    Session = get_session_factory()
    with Session() as db:
        conv = db.get(ConversacionCanal, conv_id)
        ctx = crepo.get_contexto(conv)
        cs = hydrate_conversation_state(ctx)
        from app.domain.domain_lifecycle import cover_and_note as _cover

        _cover(cs, steps=[], facts={"saldo": 45000})
        apply_cs_to_legacy(ctx, cs)
        crepo.set_contexto(conv, ctx)
        db.commit()
    _msg(org_id, "5492235612006", "Sigo sin internet.")
    _msg(org_id, "5492235612006", "¿Cuánto debo?")
    ctx = _load_ctx(conv_id)
    cs = hydrate_conversation_state(ctx)
    tec_facts = {
        f.key: f.value for f in cs.facts if f.domain_id == "tec-1" and f.status == "active"
    }
    adm_facts = {
        f.key: f.value for f in cs.facts if f.domain_id == "adm-1" and f.status == "active"
    }
    assert "saldo" not in tec_facts
    assert "alcance_wifi" not in adm_facts
    assert tec_facts.get("alcance_wifi") == "uno"


# ---------------------------------------------------------------------------
# B7 refinement
# ---------------------------------------------------------------------------


def test_b7_internet_refines_to_ftth_same_slot():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet")
    cover_and_note(cs, steps=["tipo_acceso"], facts={"sintoma": "sin_enlace"})
    ctx = {"intencion": "internet", "pasos_cubiertos": ["tipo_acceso"], "hechos": {"sintoma": "sin_enlace"}}
    apply_cs_to_legacy(ctx, cs)
    org_id, conv_id = _abrir("5492235612007", extra=ctx)
    _msg(org_id, "5492235612007", "es fibra")
    loaded = _load_ctx(conv_id)
    cs2 = hydrate_conversation_state(loaded)
    tecs = [d for d in cs2.domains if d.kind == KIND_TECNICO]
    assert len(tecs) == 1
    assert tecs[0].id == "tec-1"
    assert tecs[0].playbook in ("internet_ftth", "internet")
    facts = {f.key: f.value for f in cs2.facts if f.domain_id == "tec-1" and f.status == "active"}
    assert facts.get("sintoma") == "sin_enlace"


# ---------------------------------------------------------------------------
# B8 no tec-2
# ---------------------------------------------------------------------------


def test_b8_technical_signals_reuse_single_slot():
    org_id, conv_id = _abrir("5492235612008")
    tel = "5492235612008"
    _msg(org_id, tel, "No tengo internet")
    _msg(org_id, tel, "es fibra")
    _msg(org_id, tel, "no me anda el wifi en la tablet")
    ctx = _load_ctx(conv_id)
    cs = hydrate_conversation_state(ctx)
    tecs = [d for d in cs.domains if d.kind == KIND_TECNICO]
    assert len(tecs) == 1
    assert tecs[0].id == "tec-1"


# ---------------------------------------------------------------------------
# B9 closed
# ---------------------------------------------------------------------------


def test_b9_closed_adm_does_not_reopen():
    extra = _seed_tec_ftth()
    cs = hydrate_conversation_state(extra)
    apply_domain_signal(cs, "¿Cuánto debo?", playbook="facturacion")
    close_domain(cs, "adm-1")
    apply_cs_to_legacy(extra, cs)
    org_id, conv_id = _abrir("5492235612009", extra=extra)
    _msg(org_id, "5492235612009", "¿Cuánto debo?")
    ctx = _load_ctx(conv_id)
    cs2 = hydrate_conversation_state(ctx)
    adm = cs2.slot("adm-1")
    assert adm is not None
    assert adm.status == "closed"
    adms = [d for d in cs2.domains if d.kind == KIND_ADMIN]
    assert len(adms) == 1


# ---------------------------------------------------------------------------
# B10 SWITCH-01 completo
# ---------------------------------------------------------------------------


def test_b10_switch_01_resume_ftth_without_restart():
    tel = "5492235612010"
    org_id, conv_id = _abrir(tel)
    bots = []
    for texto in (
        "No tengo internet",
        "es fibra",
        "la PON está verde",
        "la LOS está apagada",
        "reinicié",
        "sigue igual",
        "¿Cuánto debo?",
        "ya pagué",
        "Sigo sin internet.",
    ):
        out = _msg(org_id, tel, texto)
        bots.append(str(out.get("respuesta") or ""))
    ctx = _load_ctx(conv_id)
    cs = hydrate_conversation_state(ctx)
    tec = cs.slot("tec-1")
    adm = cs.slot("adm-1")
    assert tec is not None and tec.status == "active"
    assert adm is not None and adm.status == "paused"
    assert "energia_ont" in tec.covered_steps or "luces_los" in tec.covered_steps
    last = (bots[-1] or "").lower()
    assert "cajita blanca" not in last
    assert "luz pon" not in last
    pending = cs.pending_bot or tec.pending_bot
    assert pending is None or pending.step_id not in ("energia_ont",)
    facts = {f.key: f.value for f in cs.facts if f.domain_id == "tec-1" and f.status == "active"}
    assert facts or tec.covered_steps


def test_replay_switch_02_keeps_both_domains():
    tel = "5492235612011"
    org_id, conv_id = _abrir(tel)
    for texto in (
        "Me vino más cara la factura",
        "además no me anda el wifi en la tablet",
        "en el baño",
        "volvamos a la factura, por qué subió?",
    ):
        _msg(org_id, tel, texto)
    ctx = _load_ctx(conv_id)
    cs = hydrate_conversation_state(ctx)
    kinds = {d.kind for d in cs.domains}
    assert KIND_ADMIN in kinds
    assert KIND_TECNICO in kinds
    assert cs.active_slot() is not None
    assert cs.active_slot().kind == KIND_ADMIN
    assert cs.slot("tec-1").status == "paused"


def test_replay_ftth_t70_t46_single_domain_ok():
    cases = (
        (
            "5492235612012",
            [
                "Internet anda mal",
                "es fibra",
                "la PON está verde",
                "la LOS está apagada",
                "reinicié",
                "sigue igual",
            ],
            KIND_TECNICO,
        ),
        (
            "5492235612013",
            [
                "no me anda el wifi en la tablet",
                "baño",
                "en los otros equipos funciona",
                "como conecto la tablet por cable de red?",
            ],
            KIND_TECNICO,
        ),
        (
            "5492235612014",
            [
                "Quiero contratar internet fibra en Batán",
                "Alta nueva de internet fibra en Batán",
                "Batán centro",
                "Sí, pasame con comercial por favor",
            ],
            KIND_COMERCIAL,
        ),
    )
    for tel, msgs, kind in cases:
        org_id, conv_id = _abrir(tel)
        last = ""
        for texto in msgs:
            last = str(_msg(org_id, tel, texto).get("respuesta") or "")
        ctx = _load_ctx(conv_id)
        cs = hydrate_conversation_state(ctx)
        assert len([d for d in cs.domains if d.kind == kind]) <= 1
        assert last.strip()
        proj = project_legacy(cs)
        assert proj.get("intencion")


def _seed_tec_wifi_adm_paused(*, pending_step: str = "reinicio_router_wifi") -> dict:
    cs = new_conversation_state(turn=5)
    create_domain(cs, kind=KIND_ADMIN, playbook="facturacion")
    create_domain(cs, kind=KIND_TECNICO, playbook="wifi")
    cover_and_note(
        cs,
        steps=["zona_wifi"],
        facts={"alcance_wifi": "uno", "zona_wifi": "baño"},
    )
    set_slot_pending(
        cs,
        pending_bot=PendingBot(
            act="ASK_ACTION", step_id=pending_step, referent=pending_step
        ),
        last_bot_act=LastBotAct(
            act="ASK_ACTION", step_id=pending_step, referent=pending_step
        ),
    )
    ctx: dict = {
        "intencion": "wifi",
        "paso_idx": 3,
        "pasos_cubiertos": ["zona_wifi"],
        "hechos": {"alcance_wifi": "uno", "zona_wifi": "baño"},
    }
    apply_cs_to_legacy(ctx, cs)
    return ctx


def _seed_adm_active_tec_paused() -> dict:
    ctx = _seed_tec_wifi_adm_paused()
    cs = hydrate_conversation_state(ctx)
    apply_domain_signal(cs, "¿Cuánto debo?", playbook="facturacion")
    apply_cs_to_legacy(ctx, cs)
    return ctx


# ---------------------------------------------------------------------------
# Fase 9B — Domain Selection DS1–DS10
# ---------------------------------------------------------------------------


def test_ds1_switch_02_resume_adm_ask_cause():
    tel = "5492235612201"
    org_id, conv_id = _abrir(tel, extra=_seed_tec_wifi_adm_paused())
    out = _msg(org_id, tel, "Volvamos a la factura, por qué subió?")
    resp = (out.get("respuesta") or "").lower()
    ctx = _load_ctx(conv_id)
    cs = hydrate_conversation_state(ctx)
    tec, adm, _ = _tec_adm_from_seed(ctx)
    assert adm is not None and adm.status == "active"
    assert tec is not None and tec.status == "paused"
    pending_u = cs.pending_user or (adm.pending_user if adm else None)
    assert pending_u is not None
    assert pending_u.act == USER_ASK_CAUSE
    assert pending_u.domain_id == "adm-1"
    assert "reiniciaste el router" not in resp
    assert "reiniciar el router" not in resp
    if cs.pending_bot:
        assert cs.pending_bot.step_id != "reinicio_router_wifi"
        assert cs.pending_bot.domain_id != "tec-1"


def test_ds2_resume_technical_keeps_pending():
    tel = "5492235612202"
    extra = _seed_adm_active_tec_paused()
    org_id, conv_id = _abrir(tel, extra=extra)
    out = _msg(org_id, tel, "Volvamos al problema de internet")
    resp = (out.get("respuesta") or "").lower()
    ctx = _load_ctx(conv_id)
    tec, adm, cs = _tec_adm_from_seed(ctx)
    assert tec is not None and tec.status == "active"
    assert adm is not None and adm.status == "paused"
    assert len([d for d in cs.domains if d.kind == KIND_TECNICO]) == 1
    pending = cs.pending_bot or tec.pending_bot
    assert pending is None or pending.step_id == "reinicio_router_wifi"
    assert "cajita blanca" not in resp
    assert "luz pon" not in resp


def test_ds3_create_admin_from_ademas():
    tel = "5492235612203"
    extra = _seed_tec_ftth()
    org_id, conv_id = _abrir(tel, extra=extra)
    _msg(org_id, tel, "Además quiero saber cuánto debo")
    ctx = _load_ctx(conv_id)
    tec, adm, cs = _tec_adm_from_seed(ctx)
    assert tec is not None and tec.status == "paused"
    assert adm is not None and adm.status == "active"
    assert adm.id == "adm-1"
    assert len([d for d in cs.domains if d.kind == KIND_ADMIN]) == 1
    assert "energia_ont" in tec.covered_steps


def test_ds4_resume_adm_never_adm2():
    tel = "5492235612204"
    extra = _seed_tec_wifi_adm_paused()
    cs0 = hydrate_conversation_state(extra)
    from app.domain.domain_lifecycle import pause_domain

    pause_domain(cs0, "tec-1")
    apply_cs_to_legacy(extra, cs0)
    org_id, conv_id = _abrir(tel, extra=extra)
    _msg(org_id, tel, "Quiero seguir con la factura")
    ctx = _load_ctx(conv_id)
    cs = hydrate_conversation_state(ctx)
    adms = [d for d in cs.domains if d.kind == KIND_ADMIN]
    assert len(adms) == 1
    assert adms[0].id == "adm-1"
    assert adms[0].status == "active"


def test_ds5_cause_stays_on_active_admin():
    tel = "5492235612205"
    org_id, conv_id = _abrir(tel, extra=_seed_adm_active_tec_paused())
    _msg(org_id, tel, "¿Por qué subió?")
    ctx = _load_ctx(conv_id)
    tec, adm, cs = _tec_adm_from_seed(ctx)
    assert adm is not None and adm.status == "active"
    assert tec is not None and tec.status == "paused"
    pending_u = cs.pending_user or (adm.pending_user if adm else None)
    assert pending_u is not None
    assert pending_u.act == USER_ASK_CAUSE
    assert pending_u.domain_id == "adm-1"


def test_ds6_porque_does_not_assume_admin():
    tel = "5492235612206"
    org_id, conv_id = _abrir(tel, extra=_seed_tec_wifi_adm_paused())
    _msg(org_id, tel, "¿Por qué?")
    ctx = _load_ctx(conv_id)
    tec, adm, cs = _tec_adm_from_seed(ctx)
    assert tec is not None and tec.status == "active"
    assert adm is not None and adm.status == "paused"
    interp = interpret_turn("¿Por qué?", cs, ctx)
    assert interp.domain_signal is None
    pending_u = cs.pending_user
    assert pending_u is None or pending_u.domain_id != "adm-1"


def test_ds7_howto_after_domain_switch_stays_admin():
    tel = "5492235612207"
    org_id, conv_id = _abrir(tel, extra=_seed_tec_wifi_adm_paused())
    _msg(org_id, tel, "Volvamos a la factura")
    out = _msg(org_id, tel, "¿Cómo la pago?")
    resp = (out.get("respuesta") or "").lower()
    ctx = _load_ctx(conv_id)
    tec, adm, cs = _tec_adm_from_seed(ctx)
    assert adm is not None and adm.status == "active"
    assert tec is not None and tec.status == "paused"
    pending_u = cs.pending_user or (adm.pending_user if adm else None)
    assert pending_u is not None
    assert pending_u.act in ("ASK_HOW_TO", "ASK_CAUSE")
    assert pending_u.domain_id == "adm-1"
    assert "reiniciaste el router" not in resp


def test_ds8_canal_compound_one_semantic_turn():
    tel = "5492235612208"
    extra = _seed_tec_wifi_adm_paused()
    cs0 = hydrate_conversation_state(extra)
    interp = interpret_turn("Volvamos a la factura, ¿por qué subió?", cs0, extra)
    assert interp.domain_signal == "administrativo"
    assert interp.user_act == USER_ASK_CAUSE
    org_id, conv_id = _abrir(tel, extra=extra)
    _msg(org_id, tel, "Volvamos a la factura, ¿por qué subió?")
    ctx = _load_ctx(conv_id)
    tec, adm, cs = _tec_adm_from_seed(ctx)
    assert adm is not None and adm.status == "active"
    assert tec is not None and tec.status == "paused"


def test_ds9_kind_noun_factura_resumes_or_creates():
    tel = "5492235612209"
    org_id, conv_id = _abrir(tel, extra=_seed_tec_wifi_adm_paused())
    _msg(org_id, tel, "Y la factura?")
    ctx = _load_ctx(conv_id)
    cs = hydrate_conversation_state(ctx)
    adm = cs.slot("adm-1")
    assert adm is not None and adm.status == "active"
    assert cs.slot("tec-1").status == "paused"
    assert len([d for d in cs.domains if d.kind == KIND_ADMIN]) == 1

    tel2 = "5492235612219"
    org_id2, conv_id2 = _abrir(tel2, extra=_seed_tec_ftth())
    _msg(org_id2, tel2, "Y la factura?")
    ctx2 = _load_ctx(conv_id2)
    cs2 = hydrate_conversation_state(ctx2)
    assert cs2.slot("adm-1") is not None
    assert cs2.slot("adm-1").status == "active"
    assert len([d for d in cs2.domains if d.kind == KIND_ADMIN]) == 1


def test_ds10_dual_topic_first_span_is_tech():
    tel = "5492235612210"
    org_id, conv_id = _abrir(tel)
    _msg(org_id, tel, "El WiFi sigue mal y además quiero saber por qué subió la factura.")
    ctx = _load_ctx(conv_id)
    cs = hydrate_conversation_state(ctx)
    tecs = [d for d in cs.domains if d.kind == KIND_TECNICO]
    adms = [d for d in cs.domains if d.kind == KIND_ADMIN]
    assert len(tecs) == 1
    assert len(adms) == 1
    assert cs.active_slot() is not None
    assert cs.active_slot().kind == KIND_TECNICO
    assert adms[0].status == "paused"
    pending_u = cs.pending_user
    assert pending_u is None or pending_u.domain_id != "adm-1"


def test_spans_wifi_then_factura_tech_primary():
    cs = new_conversation_state(turn=1)
    trans = apply_turn_domain(
        cs, "El WiFi sigue mal y además quiero saber por qué subió la factura."
    )
    assert trans.cs.active_slot() is not None
    assert trans.cs.active_slot().kind == KIND_TECNICO
    assert trans.cs.slot("adm-1") is not None
    assert trans.cs.slot("adm-1").status == "paused"


def test_spans_factura_then_wifi_admin_primary():
    cs = new_conversation_state(turn=1)
    trans = apply_turn_domain(
        cs, "La factura subió y además no me anda el wifi en la tablet"
    )
    assert trans.cs.active_slot() is not None
    assert trans.cs.active_slot().kind == KIND_ADMIN
    assert trans.cs.slot("tec-1") is not None
    assert trans.cs.slot("tec-1").status == "paused"


def test_ownership_alcance_wifi_not_reassigned_to_adm():
    cs = new_conversation_state(turn=3)
    create_domain(cs, kind=KIND_TECNICO, playbook="wifi")
    cover_and_note(cs, steps=["zona_wifi"], facts={"alcance_wifi": "uno"})
    apply_domain_signal(cs, "¿Cuánto debo?", playbook="facturacion")
    ctx = {
        "intencion": "facturacion",
        "hechos": {"alcance_wifi": "uno", "saldo": 45000},
        "pasos_cubiertos": [],
        "cs": cs.to_dict(),
    }
    cs2 = hydrate_conversation_state(ctx)
    sync_from_legacy(cs2, ctx)
    tec_facts = {
        f.key: f.value for f in cs2.facts if f.domain_id == "tec-1" and f.status == "active"
    }
    adm_facts = {
        f.key: f.value for f in cs2.facts if f.domain_id == "adm-1" and f.status == "active"
    }
    assert tec_facts.get("alcance_wifi") == "uno"
    assert "alcance_wifi" not in adm_facts
    assert adm_facts.get("saldo") == 45000


def test_closed_admin_compound_signal_does_not_reopen():
    extra = _seed_tec_wifi_adm_paused()
    cs = hydrate_conversation_state(extra)
    apply_domain_signal(cs, "¿Cuánto debo?", playbook="facturacion")
    close_domain(cs, "adm-1")
    resume_domain(cs, "tec-1")
    apply_cs_to_legacy(extra, cs)
    tel = "5492235612211"
    org_id, conv_id = _abrir(tel, extra=extra)
    _msg(org_id, tel, "Volvamos a la factura, por qué subió?")
    ctx = _load_ctx(conv_id)
    cs2 = hydrate_conversation_state(ctx)
    adm = cs2.slot("adm-1")
    assert adm is not None
    assert adm.status == "closed"
    assert len([d for d in cs2.domains if d.kind == KIND_ADMIN]) == 1
    assert cs2.active_slot() is None or cs2.active_slot().id != "adm-1"
