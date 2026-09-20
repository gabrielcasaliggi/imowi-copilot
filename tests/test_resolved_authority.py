"""Gate 11A etapa 1: autoridad de resolved (LLM propone, Motor autoriza)."""

from __future__ import annotations

from unittest.mock import patch

from sqlalchemy import select

from app.domain.action_proposal import (
    ACTION_RESOLVED,
    SOURCE_HEURISTIC,
    SOURCE_LLM,
    ActionProposal,
    evaluate_resolved,
    proposal_from_diag_result,
)
from app.domain.conversation_motor import (
    ACT_ASK_NEXT_STEP,
    ACT_CLOSE,
    apply_cs_to_legacy,
    authorize_resolved,
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


def _seed_tec() -> dict:
    cs = new_conversation_state(turn=4)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet_ftth")
    cover_and_note(cs, steps=["energia_ont", "luces_los"], facts={"luces_ont": "pon_verde"})
    set_slot_pending(
        cs,
        pending_bot=PendingBot(
            act="ASK_ACTION", step_id="reinicio_ont", referent="reinicio_ont"
        ),
        last_bot_act=LastBotAct(
            act="ASK_ACTION", step_id="reinicio_ont", referent="reinicio_ont"
        ),
    )
    ctx: dict = {
        "intencion": "internet_ftth",
        "paso_idx": 2,
        "pasos_cubiertos": ["energia_ont", "luces_los"],
        "hechos": {"luces_ont": "pon_verde"},
        "diag_turnos": 2,
        "pppoe_informado": True,
    }
    apply_cs_to_legacy(ctx, cs)
    return ctx


def _patches_diag(ia: dict, *, encuesta: list | None = None):
    """Evita early-close léxico para forzar proposal → Motor → efecto."""
    enc = encuesta if encuesta is not None else []

    def _enc(*_a, **_k):
        enc.append(True)

    return (
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
        patch(
            "app.services.canal_abonado.enviar_encuesta_cierre",
            side_effect=_enc,
        ),
    )


def _aplicar(org_id: str, conv_id: str, texto: str, *, ia: dict, enc: list) -> dict:
    patches = _patches_diag(ia, encuesta=enc)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
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
                texto,
                canal=_CANAL,
                ctx=ctx,
                intencion=str(ctx.get("intencion") or "internet_ftth"),
                usar_llama=True,
            )
            db.commit()
            return out or {}


# ---------------------------------------------------------------------------
# Unit
# ---------------------------------------------------------------------------


def test_r1_policy_deny_contacto_sin_servicio():
    p = ActionProposal(
        action=ACTION_RESOLVED,
        source=SOURCE_LLM,
        reason="ia",
        message="Cierro entonces.",
        step_hint="reinicio_ont",
    )
    d = evaluate_resolved(p, "sí me contestó el técnico")
    assert d.allow is False
    assert d.reason == "bloqueado_resolved_solo_contacto"


def test_r1_motor_deny_no_close():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet_ftth")
    auth = authorize_resolved(
        cs,
        ActionProposal(
            action=ACTION_RESOLVED,
            source=SOURCE_LLM,
            reason="ia",
            message="Listo, cerrado.",
            step_hint="reinicio_ont",
        ),
        "me contestaron",
        {},
    )
    assert auth.allow is False
    assert auth.action.type != ACT_CLOSE
    assert auth.action.type == ACT_ASK_NEXT_STEP


def test_r2_motor_allow_close():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet_ftth")
    auth = authorize_resolved(
        cs,
        ActionProposal(
            action=ACTION_RESOLVED,
            source=SOURCE_LLM,
            reason="ia",
            message="¡Qué bueno!",
        ),
        "confirmado todo en orden",
        {},
    )
    assert auth.allow is True
    assert auth.action.type == ACT_CLOSE


def test_r5_step_hint_no_cover_in_authorize():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet_ftth")
    before = list(cs.active_slot().covered_steps)
    authorize_resolved(
        cs,
        ActionProposal(
            action=ACTION_RESOLVED,
            source=SOURCE_LLM,
            reason="ia",
            message="ok",
            step_hint="reinicio_ont",
        ),
        "confirmado todo en orden",
        {},
    )
    assert list(cs.active_slot().covered_steps) == before


# ---------------------------------------------------------------------------
# Productivo
# ---------------------------------------------------------------------------


def test_r1_llm_resolved_deny_no_cierra():
    tel = "5492235614020"
    org_id, conv_id = _abrir(tel, extra=_seed_tec())
    enc: list = []
    out = _aplicar(
        org_id,
        conv_id,
        "sí me contestó el técnico",
        ia={
            "accion": "resolved",
            "mensaje": "Perfecto, cerramos.",
            "paso_cubierto": "reinicio_ont",
            "motivo": "ia",
        },
        enc=enc,
    )
    Session = get_session_factory()
    with Session() as db:
        assert db.get(ConversacionCanal, conv_id).estado != "cerrado"
    assert out.get("modo") != "cerrado"
    assert out.get("resolved_authorized") is not True
    assert not enc


def test_r2_llm_resolved_allow_cierra():
    tel = "5492235614021"
    org_id, conv_id = _abrir(tel, extra=_seed_tec())
    enc: list = []
    out = _aplicar(
        org_id,
        conv_id,
        "confirmado todo en orden",
        ia={
            "accion": "resolved",
            "mensaje": "¡Qué bueno que volvió!",
            "paso_cubierto": "",
            "motivo": "ia",
        },
        enc=enc,
    )
    Session = get_session_factory()
    with Session() as db:
        assert db.get(ConversacionCanal, conv_id).estado == "cerrado"
    assert out.get("modo") == "cerrado"
    assert out.get("resolved_authorized") is True
    assert out.get("resolved_source") == SOURCE_LLM
    assert enc


def test_r3_resolved_json_alone_insufficient_without_auth():
    tel = "5492235614022"
    org_id, conv_id = _abrir(tel, extra=_seed_tec())
    enc: list = []
    out = _aplicar(
        org_id,
        conv_id,
        "quiero consultar otra vez",
        ia={
            "accion": "resolved",
            "mensaje": "Cerrado.",
            "paso_cubierto": "",
            "motivo": "ia",
        },
        enc=enc,
    )
    Session = get_session_factory()
    with Session() as db:
        assert db.get(ConversacionCanal, conv_id).estado != "cerrado"
    assert out.get("modo") != "cerrado"
    assert not enc


def test_r4_resolved_no_cubre_paso():
    tel = "5492235614023"
    seed = _seed_tec()
    cub_antes = list(seed["pasos_cubiertos"])
    org_id, conv_id = _abrir(tel, extra=seed)
    enc: list = []
    _aplicar(
        org_id,
        conv_id,
        "confirmado todo en orden",
        ia={
            "accion": "resolved",
            "mensaje": "Listo.",
            "paso_cubierto": "reinicio_ont",
            "motivo": "ia",
        },
        enc=enc,
    )
    ctx2 = _load_ctx(conv_id)
    assert "reinicio_ont" not in (ctx2.get("pasos_cubiertos") or [])
    assert list(ctx2.get("pasos_cubiertos") or []) == cub_antes
    cs = hydrate_conversation_state(ctx2)
    assert "reinicio_ont" not in (cs.slot("tec-1").covered_steps or [])


def test_r6_resolved_no_cambia_active_domain():
    tel = "5492235614024"
    seed = _seed_tec()
    org_id, conv_id = _abrir(tel, extra=seed)
    before = hydrate_conversation_state(_load_ctx(conv_id)).active_domain_id
    enc: list = []
    _aplicar(
        org_id,
        conv_id,
        "confirmado todo en orden",
        ia={
            "accion": "resolved",
            "mensaje": "Cierro.",
            "paso_cubierto": "wifi_vs_cable_ftth",
            "motivo": "ia",
        },
        enc=enc,
    )
    after = hydrate_conversation_state(_load_ctx(conv_id)).active_domain_id
    assert after == before == "tec-1"


def test_r7_heuristica_b_resolved_sigue_cerrando():
    tel = "5492235614025"
    org_id, conv_id = _abrir(tel, extra=_seed_tec())
    enc: list = []
    out = _aplicar(
        org_id,
        conv_id,
        "confirmado todo en orden",
        ia={
            "accion": "resolved",
            "mensaje": "Dale, quedamos así.",
            "paso_cubierto": "consumo_paquete",
            "motivo": "cierre_tras_bono",
        },
        enc=enc,
    )
    Session = get_session_factory()
    with Session() as db:
        assert db.get(ConversacionCanal, conv_id).estado == "cerrado"
    assert out.get("resolved_authorized") is True
    assert out.get("resolved_source") == SOURCE_HEURISTIC
    assert (
        proposal_from_diag_result(
            {"accion": "resolved", "motivo": "cierre_tras_bono"}
        ).source
        == SOURCE_HEURISTIC
    )
    assert enc
    # paso_cubierto heurístico tampoco cubre vía resolved
    ctx = _load_ctx(conv_id)
    assert "consumo_paquete" not in (ctx.get("pasos_cubiertos") or [])


def test_integracion_productiva_procesar_mensaje_resolved_deny():
    tel = "5492235614026"
    org_id, conv_id = _abrir(tel, extra=_seed_tec())
    cub_antes = list(_load_ctx(conv_id).get("pasos_cubiertos") or [])
    with (
        patch(
            "app.services.canal_abonado.resolve_canal_diagnostico_ia",
            return_value=True,
        ),
        patch(
            "app.services.diagnostico_n1.diagnosticar_turno",
            return_value={
                "accion": "resolved",
                "mensaje": "Cerrado.",
                "paso_cubierto": "reinicio_ont",
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
    ):
        Session = get_session_factory()
        with Session() as db:
            out = procesar_mensaje_entrante(
                db,
                org_id,
                telefono=tel,
                texto="me contestaron del soporte",
                canal=_CANAL,
                usar_llama=True,
            )
            assert db.get(ConversacionCanal, conv_id).estado != "cerrado"
    assert out.get("modo") != "cerrado"
    ctx = _load_ctx(conv_id)
    assert list(ctx.get("pasos_cubiertos") or []) == cub_antes
