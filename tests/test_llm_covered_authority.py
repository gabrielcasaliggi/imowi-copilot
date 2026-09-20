"""Fase 10B: el LLM / diagnosticar_turno no puede mutar covered_steps.

Contrato R1: si diagnosticar_turno devuelve paso_cubierto, NO debe
terminar en ctx["pasos_cubiertos"] ni en ConversationState.covered_steps.

Todos los casos usan usar_llama=True. Se mockea diagnosticar_turno (salida
completa del diagnóstico IA, incl. JSON del LLM) para aislar el consumidor.
"""

from __future__ import annotations

from unittest.mock import patch

from sqlalchemy import select

from app.domain.conversation_motor import apply_cs_to_legacy
from app.domain.conversation_state import (
    KIND_ADMIN,
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


def _msg_llama_diag(org_id: str, tel: str, texto: str, *, ia: dict) -> dict:
    """Ruta productiva con usar_llama=True; diagnosticar_turno controlado.

    Se anulan atajos previos (PPPoE / rama wifi post-acceso) para llegar al
    consumidor del JSON IA — el objeto de esta fase.
    """
    with (
        patch(
            "app.services.canal_abonado.resolve_canal_diagnostico_ia",
            return_value=True,
        ),
        patch(
            "app.services.diagnostico_n1.diagnosticar_turno",
            return_value=dict(ia),
        ),
        patch(
            "app.services.canal_pppoe._talvez_mensaje_pppoe",
            return_value=None,
        ),
        patch(
            "app.services.canal_abonado._linea_acceso_ok_ctx",
            return_value=False,
        ),
    ):
        Session = get_session_factory()
        with Session() as db:
            return procesar_mensaje_entrante(
                db,
                org_id,
                telefono=tel,
                texto=texto,
                canal=_CANAL,
                usar_llama=True,
            )


def _seed_tec_wifi_pending() -> dict:
    cs = new_conversation_state(turn=8)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet_ftth")
    prev = [
        "energia_ont",
        "luces_los",
        "reinicio_ont",
        "cable_fibra",
        "servicio_tras_optica",
    ]
    cover_and_note(
        cs,
        steps=prev,
        facts={"luces_ont": "pon_verde"},
    )
    set_slot_pending(
        cs,
        pending_bot=PendingBot(
            act="ASK_FACT",
            step_id="wifi_vs_cable_ftth",
            referent="wifi_vs_cable_ftth",
        ),
        last_bot_act=LastBotAct(
            act="ASK_FACT",
            step_id="wifi_vs_cable_ftth",
            referent="wifi_vs_cable_ftth",
        ),
    )
    ctx: dict = {
        "intencion": "internet_ftth",
        "paso_idx": 5,
        "pasos_cubiertos": list(prev),
        "hechos": {"luces_ont": "pon_verde"},
        "diag_turnos": 2,
        "pppoe_informado": True,
    }
    apply_cs_to_legacy(ctx, cs)
    return ctx


def _seed_adm_with_paused_tec() -> dict:
    cs = new_conversation_state(turn=4)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet_ftth")
    cover_and_note(cs, steps=["energia_ont"], facts={"luces_ont": "pon_verde"})
    create_domain(cs, kind=KIND_ADMIN, playbook="facturacion_reclamo")
    set_slot_pending(
        cs,
        pending_bot=PendingBot(
            act="ASK_FACT",
            step_id="detalle_importe",
            referent="detalle_importe",
        ),
        last_bot_act=LastBotAct(
            act="ASK_FACT",
            step_id="detalle_importe",
            referent="detalle_importe",
        ),
    )
    tec = cs.slot("tec-1")
    assert tec is not None
    tec.status = "paused"
    ctx: dict = {
        "intencion": "facturacion_reclamo",
        "paso_idx": 0,
        "pasos_cubiertos": [],
        "hechos": {},
        "intencion_tecnica_pendiente": "internet_ftth",
        "diag_turnos": 1,
        "pppoe_informado": True,
    }
    apply_cs_to_legacy(ctx, cs)
    return ctx


def test_ia01_llm_no_cubre_paso_incorrecto():
    tel = "5492235613110"
    seed = _seed_tec_wifi_pending()
    org_id, conv_id = _abrir(tel, extra=seed)
    paso_idx_antes = int(_load_ctx(conv_id).get("paso_idx") or 0)
    out = _msg_llama_diag(
        org_id,
        tel,
        "Dale, seguimos con el diagnóstico.",
        ia={
            "accion": "ask",
            "mensaje": "Probemos reiniciar la ONT.",
            "paso_cubierto": "reinicio_ont",
            "motivo": "ia_abuso",
        },
    )
    assert out.get("diagnostico_ia") is True
    ctx = _load_ctx(conv_id)
    cs = hydrate_conversation_state(ctx)
    tec = cs.slot("tec-1")
    assert tec is not None
    assert cs.active_domain_id == "tec-1"
    # El JSON IA no puede agregar covers nuevos: wifi sigue pendiente.
    assert "wifi_vs_cable_ftth" not in (tec.covered_steps or [])
    assert "wifi_vs_cable_ftth" not in (ctx.get("pasos_cubiertos") or [])
    # reinicio_ont ya estaba cubierto; no debe reintroducirse como efecto IA
    # ni mover el pending.
    pending = cs.pending_bot or tec.pending_bot
    assert pending is not None
    assert pending.step_id == "wifi_vs_cable_ftth"
    assert int(ctx.get("paso_idx") or 0) == paso_idx_antes
    assert ctx.get("ia_suggested_step") == "reinicio_ont"


def test_ia01b_llm_no_agrega_cover_nuevo():
    tel = "5492235613111"
    seed = _seed_tec_wifi_pending()
    org_id, conv_id = _abrir(tel, extra=seed)
    out = _msg_llama_diag(
        org_id,
        tel,
        "Contame qué más necesitás.",
        ia={
            "accion": "ask",
            "mensaje": "Abramos visita técnica.",
            "paso_cubierto": "turno_campo_ftth",
            "motivo": "ia_abuso",
        },
    )
    assert out.get("diagnostico_ia") is True
    ctx = _load_ctx(conv_id)
    cs = hydrate_conversation_state(ctx)
    tec = cs.slot("tec-1")
    assert tec is not None
    assert "turno_campo_ftth" not in (tec.covered_steps or [])
    assert "turno_campo_ftth" not in (ctx.get("pasos_cubiertos") or [])
    assert cs.active_domain_id == "tec-1"
    pending = cs.pending_bot or tec.pending_bot
    assert pending is not None
    assert pending.step_id == "wifi_vs_cable_ftth"


def test_ia02_llm_paso_otro_dominio_no_contamina():
    """ADM activo: diagnosticar_turno sugiere paso TEC → no contamina adm ni tec.

    Se invoca el consumidor productivo `_aplicar_diagnostico_ia` con ADM fijo
    para no mezclar con Domain Selection (fuera de alcance 10B).
    """
    from app.services.canal_diagnostico_ia import _aplicar_diagnostico_ia

    tel = "5492235613112"
    org_id, conv_id = _abrir(tel, extra=_seed_adm_with_paused_tec())
    tec_antes = list(
        hydrate_conversation_state(_load_ctx(conv_id)).slot("tec-1").covered_steps or []
    )
    ia = {
        "accion": "ask",
        "mensaje": "Revisemos el router.",
        "paso_cubierto": "reinicio_router_wifi",
        "motivo": "ia_abuso",
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
        patch(
            "app.services.canal_pppoe._talvez_mensaje_pppoe",
            return_value=None,
        ),
        patch(
            "app.services.canal_abonado._linea_acceso_ok_ctx",
            return_value=False,
        ),
    ):
        Session = get_session_factory()
        with Session() as db:
            conv = db.get(ConversacionCanal, conv_id)
            assert conv is not None
            abo = db.get(Abonado, conv.abonado_id) if conv.abonado_id else None
            ctx = crepo.get_contexto(conv)
            out = _aplicar_diagnostico_ia(
                db,
                org_id,
                conv,
                abo,
                "Es de marzo, el monto es 18500 pesos.",
                canal=_CANAL,
                ctx=ctx,
                intencion="facturacion_reclamo",
                usar_llama=True,
            )
    assert out is not None
    assert out.get("diagnostico_ia") is True
    ctx = _load_ctx(conv_id)
    cs = hydrate_conversation_state(ctx)
    adm = cs.slot("adm-1")
    tec = cs.slot("tec-1")
    assert adm is not None
    assert cs.active_domain_id == "adm-1"
    assert "reinicio_router_wifi" not in (adm.covered_steps or [])
    assert "reinicio_router_wifi" not in (ctx.get("pasos_cubiertos") or [])
    assert list(tec.covered_steps or []) == tec_antes
    pending = cs.pending_bot or adm.pending_bot
    assert pending is not None
    assert pending.domain_id == "adm-1"
    assert pending.step_id == "detalle_importe"
    assert ctx.get("ia_suggested_step") == "reinicio_router_wifi"


def test_ia03_paso_cubierto_no_mueve_cursor():
    tel = "5492235613113"
    seed = _seed_tec_wifi_pending()
    org_id, conv_id = _abrir(tel, extra=seed)
    ctx0 = _load_ctx(conv_id)
    paso_idx_antes = int(ctx0.get("paso_idx") or 0)
    _msg_llama_diag(
        org_id,
        tel,
        "Seguimos cuando puedas.",
        ia={
            "accion": "ask",
            "mensaje": "¿Reiniciaste la ONT?",
            "paso_cubierto": "reinicio_ont",
            "motivo": "ia",
        },
    )
    ctx = _load_ctx(conv_id)
    assert int(ctx.get("paso_idx") or 0) == paso_idx_antes
    # El cover sugerido por IA no se agrega (ya estaba o no: no mueve cursor).
    assert ctx.get("ia_suggested_step") == "reinicio_ont"
    cs = hydrate_conversation_state(ctx)
    pending = cs.pending_bot or (cs.slot("tec-1").pending_bot if cs.slot("tec-1") else None)
    assert pending is not None
    assert pending.step_id == "wifi_vs_cable_ftth"


def test_ia04_sin_confirmacion_usuario_no_cubre():
    tel = "5492235613114"
    seed = _seed_tec_wifi_pending()
    seed["pasos_cubiertos"] = ["energia_ont", "luces_los"]
    seed["paso_idx"] = 2
    cs = hydrate_conversation_state(seed)
    tec = cs.active_slot()
    assert tec is not None
    tec.covered_steps = ["energia_ont", "luces_los"]
    set_slot_pending(
        cs,
        pending_bot=PendingBot(
            act="ASK_ACTION",
            step_id="reinicio_ont",
            referent="reinicio_ont",
        ),
        last_bot_act=LastBotAct(
            act="ASK_ACTION",
            step_id="reinicio_ont",
            referent="reinicio_ont",
        ),
    )
    apply_cs_to_legacy(seed, cs)
    org_id, conv_id = _abrir(tel, extra=seed)
    _msg_llama_diag(
        org_id,
        tel,
        "Estoy en casa ahora.",
        ia={
            "accion": "ask",
            "mensaje": "Perfecto, doy por hecho el reinicio.",
            "paso_cubierto": "reinicio_ont",
            "motivo": "ia_inferencia",
        },
    )
    ctx = _load_ctx(conv_id)
    cs2 = hydrate_conversation_state(ctx)
    tec2 = cs2.slot("tec-1")
    assert tec2 is not None
    assert "reinicio_ont" not in (tec2.covered_steps or [])
    assert "reinicio_ont" not in (ctx.get("pasos_cubiertos") or [])


def test_ia05_pending_bot_estable_ante_paso_invalido():
    tel = "5492235613115"
    org_id, conv_id = _abrir(tel, extra=_seed_tec_wifi_pending())
    _msg_llama_diag(
        org_id,
        tel,
        "Decime el próximo chequeo.",
        ia={
            "accion": "ask",
            "mensaje": "¿Cómo está la fibra?",
            "paso_cubierto": "energia_ont",
            "motivo": "ia_invalido",
        },
    )
    ctx = _load_ctx(conv_id)
    cs = hydrate_conversation_state(ctx)
    tec = cs.slot("tec-1")
    pending = cs.pending_bot or (tec.pending_bot if tec else None)
    assert pending is not None
    assert pending.step_id == "wifi_vs_cable_ftth"


def test_integracion_llama_on_no_muta_covered_en_ruta_productiva():
    tel = "5492235613116"
    org_id, conv_id = _abrir(tel, extra=_seed_tec_wifi_pending())
    out = _msg_llama_diag(
        org_id,
        tel,
        "Dale, seguí vos.",
        ia={
            "accion": "ask",
            "mensaje": "¿El fallo es solo por Wi‑Fi o también por cable?",
            "paso_cubierto": "turno_campo_ftth",
            "motivo": "ia",
        },
    )
    assert out.get("ok") is True
    assert out.get("diagnostico_ia") is True
    ctx = _load_ctx(conv_id)
    cs = hydrate_conversation_state(ctx)
    assert cs.active_domain_id == "tec-1"
    tec = cs.slot("tec-1")
    assert tec is not None
    assert "turno_campo_ftth" not in tec.covered_steps
    assert "turno_campo_ftth" not in (ctx.get("pasos_cubiertos") or [])
    pending = cs.pending_bot or tec.pending_bot
    assert pending is not None
    assert pending.step_id == "wifi_vs_cable_ftth"


def test_integracion_adm_llama_on_no_contamina_tec():
    tel = "5492235613117"
    org_id, conv_id = _abrir(tel, extra=_seed_adm_with_paused_tec())
    out = _msg_llama_diag(
        org_id,
        tel,
        "Quiero entender el aumento.",
        ia={
            "accion": "ask",
            "mensaje": "Reiniciá el router Wi‑Fi.",
            "paso_cubierto": "reinicio_router_wifi",
            "motivo": "ia",
        },
    )
    assert out.get("ok") is True
    assert out.get("diagnostico_ia") is True
    ctx = _load_ctx(conv_id)
    cs = hydrate_conversation_state(ctx)
    assert cs.active_slot() is not None
    assert cs.active_slot().kind == KIND_ADMIN
    assert "reinicio_router_wifi" not in (cs.slot("adm-1").covered_steps or [])
    tec = cs.slot("tec-1")
    assert tec is not None
    assert "reinicio_router_wifi" not in (tec.covered_steps or [])


def test_defense_sync_no_importa_covers_desde_legacy():
    """Gate 12: sync_from_legacy no copia covers legacy al CS canónico."""
    from app.domain.conversation_state import sync_from_legacy

    cs = new_conversation_state(turn=2)
    create_domain(cs, kind=KIND_ADMIN, playbook="facturacion_reclamo")
    before = list(cs.active_slot().covered_steps)
    ctx = {
        "intencion": "facturacion_reclamo",
        "pasos_cubiertos": ["detalle_importe", "reinicio_router_wifi"],
        "paso_idx": 0,
        "hechos": {},
    }
    sync_from_legacy(cs, ctx)
    adm = cs.active_slot()
    assert adm is not None
    assert adm.kind == KIND_ADMIN
    assert list(adm.covered_steps) == before
    assert "reinicio_router_wifi" not in adm.covered_steps
    assert "detalle_importe" not in adm.covered_steps
