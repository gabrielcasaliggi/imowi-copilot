"""Gate 11C: autoridad de escalate (LLM propone, Motor autoriza)."""

from __future__ import annotations

from unittest.mock import patch

from sqlalchemy import select

from app.domain.action_proposal import (
    ACTION_ESCALATE,
    SOURCE_HEURISTIC,
    SOURCE_LLM,
    SOURCE_PLANT,
    ActionProposal,
    evaluate_escalate,
    proposal_from_diag_result,
)
from app.domain.conversation_motor import (
    ACT_ASK_NEXT_STEP,
    ACT_ESCALATE,
    apply_cs_to_legacy,
    authorize_escalate,
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


def _seed_tec(*, diag_turnos: int = 1) -> dict:
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
        "diag_turnos": diag_turnos,
        "pppoe_informado": True,
        # Evitar lectura forzada E1 cuando diag_turnos >= 3 (ruta B aparte).
        "lectura_forzada_e1": True,
    }
    apply_cs_to_legacy(ctx, cs)
    return ctx


def _patches_diag(ia: dict, *, tickets: list | None = None):
    """Evita early-close léxico y discurso CS; contabiliza ticket sin notify FK."""
    tix = tickets if tickets is not None else []

    def _ticket(*_a, **_k):
        tid = f"T-ESC-{len(tix) + 1}"
        tix.append(tid)
        conv = _a[2]
        conv.estado = "espera_agente"
        conv.ticket_id = tid
        return tid

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
            "app.services.canal_abonado._aplicar_discurso_cs",
            return_value=None,
        ),
        patch(
            "app.services.canal_abonado._crear_ticket_n2",
            side_effect=_ticket,
        ),
        patch(
            "app.services.handoff_notify.notify_espera_agente",
            return_value=0,
        ),
    )


def _aplicar(org_id: str, conv_id: str, texto: str, *, ia: dict, tickets: list) -> dict:
    patches = _patches_diag(ia, tickets=tickets)
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patches[7],
        patches[8],
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


def test_e1_policy_deny_llm_sin_turnos():
    p = ActionProposal(
        action=ACTION_ESCALATE,
        source=SOURCE_LLM,
        reason="ia",
        message="Te derivo con un agente.",
        step_hint="reinicio_ont",
    )
    d = evaluate_escalate(p, "sigue sin andar", turnos_diagnostico=1)
    assert d.allow is False
    assert d.reason == "bloqueado_escalate_min_turnos"
    assert d.demote_to == "ask"


def test_e1_motor_deny_no_act_escalate():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet_ftth")
    auth = authorize_escalate(
        cs,
        ActionProposal(
            action=ACTION_ESCALATE,
            source=SOURCE_LLM,
            reason="ia",
            message="Derivo.",
            step_hint="reinicio_ont",
        ),
        "sigue mal",
        {"diag_turnos": 1},
        turnos_diagnostico=1,
    )
    assert auth.allow is False
    assert auth.action.type != ACT_ESCALATE
    assert auth.action.type == ACT_ASK_NEXT_STEP


def test_e2_motor_allow_llm_con_turnos():
    cs = new_conversation_state(turn=5)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet_ftth")
    auth = authorize_escalate(
        cs,
        ActionProposal(
            action=ACTION_ESCALATE,
            source=SOURCE_LLM,
            reason="ia",
            message="Te paso con un técnico.",
        ),
        "ya probé de todo y sigue igual",
        {"diag_turnos": 5},
        turnos_diagnostico=5,
        intencion="internet_ftth",
    )
    assert auth.allow is True
    assert auth.action.type == ACT_ESCALATE


def test_e4_step_hint_no_cover_in_authorize():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet_ftth")
    before = list(cs.active_slot().covered_steps)
    authorize_escalate(
        cs,
        ActionProposal(
            action=ACTION_ESCALATE,
            source=SOURCE_LLM,
            reason="ia",
            message="ok",
            step_hint="reinicio_ont",
        ),
        "ya probé de todo",
        {"diag_turnos": 5},
        turnos_diagnostico=5,
    )
    assert list(cs.active_slot().covered_steps) == before


def test_e5_active_domain_id_inalterado_en_motor():
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet_ftth")
    before = cs.active_domain_id
    authorize_escalate(
        cs,
        ActionProposal(
            action=ACTION_ESCALATE,
            source=SOURCE_LLM,
            reason="ia",
            message="Derivo.",
        ),
        "ya probé de todo",
        {"diag_turnos": 5},
        turnos_diagnostico=5,
    )
    assert cs.active_domain_id == before


def test_e6_heuristic_source_allow():
    p = proposal_from_diag_result(
        {
            "accion": "escalate",
            "motivo": "agotamiento_checklist",
            "mensaje": "Derivamos.",
        }
    )
    assert p.source == SOURCE_HEURISTIC
    d = evaluate_escalate(p, "sigue igual", turnos_diagnostico=0)
    assert d.allow is True
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet_ftth")
    auth = authorize_escalate(cs, p, "sigue igual", {"diag_turnos": 0})
    assert auth.allow is True
    assert auth.action.type == ACT_ESCALATE
    assert auth.proposal_source == SOURCE_HEURISTIC


def test_e7_plant_source_allow():
    p = proposal_from_diag_result(
        {
            "accion": "escalate",
            "motivo": "fibra_danada",
            "mensaje": "Problema óptico.",
        }
    )
    assert p.source == SOURCE_PLANT
    d = evaluate_escalate(p, "luz los roja", turnos_diagnostico=0)
    assert d.allow is True
    cs = new_conversation_state(turn=1)
    create_domain(cs, kind=KIND_TECNICO, playbook="internet_ftth")
    auth = authorize_escalate(cs, p, "luz los roja", {"diag_turnos": 0})
    assert auth.allow is True
    assert auth.action.type == ACT_ESCALATE
    assert auth.proposal_source == SOURCE_PLANT


# ---------------------------------------------------------------------------
# Productivo / integración
# ---------------------------------------------------------------------------


def test_e1_llm_escalate_deny_no_ticket():
    tel = "5492235615020"
    org_id, conv_id = _abrir(tel, extra=_seed_tec(diag_turnos=1))
    tickets: list = []
    out = _aplicar(
        org_id,
        conv_id,
        "sigue sin andar el wifi",
        ia={
            "accion": "escalate",
            "mensaje": "Te derivo con un agente.",
            "paso_cubierto": "reinicio_ont",
            "motivo": "ia",
        },
        tickets=tickets,
    )
    Session = get_session_factory()
    with Session() as db:
        conv = db.get(ConversacionCanal, conv_id)
        assert conv.estado != "espera_agente"
        assert not (conv.ticket_id or "").strip()
    assert not tickets
    assert out.get("modo") != "espera_agente"
    assert out.get("escalate_authorized") is not True
    assert not out.get("ticket_id")


def test_e2_llm_escalate_allow_crea_ticket():
    tel = "5492235615021"
    org_id, conv_id = _abrir(tel, extra=_seed_tec(diag_turnos=4))
    tickets: list = []
    out = _aplicar(
        org_id,
        conv_id,
        "ya reinicié y cableé y sigue igual",
        ia={
            "accion": "escalate",
            "mensaje": "Te paso con un técnico de planta.",
            "paso_cubierto": "",
            "motivo": "ia",
        },
        tickets=tickets,
    )
    Session = get_session_factory()
    with Session() as db:
        conv = db.get(ConversacionCanal, conv_id)
        assert conv.estado == "espera_agente"
        assert (conv.ticket_id or "").strip()
    assert tickets
    assert out.get("modo") == "espera_agente"
    assert out.get("escalate_authorized") is True
    assert out.get("escalate_source") == SOURCE_LLM
    assert out.get("ticket_id")


def test_e3_llm_json_alone_insufficient():
    """diagnosticar_turno → escalate por sí solo no genera ticket (pocos turnos)."""
    tel = "5492235615022"
    org_id, conv_id = _abrir(tel, extra=_seed_tec(diag_turnos=0))
    tickets: list = []
    out = _aplicar(
        org_id,
        conv_id,
        "hola quiero agente ya",
        ia={
            "accion": "escalate",
            "mensaje": "Escalo.",
            "paso_cubierto": "",
            "motivo": "ia",
        },
        tickets=tickets,
    )
    assert not tickets
    assert out.get("modo") != "espera_agente"
    assert not out.get("ticket_id")
    # Debe haber pasado por proposal/policy (motivo de deny persistido o ask).
    ctx = _load_ctx(conv_id)
    assert "bloqueado_escalate" in str(ctx.get("ultima_diag_motivo") or "") or out.get(
        "modo"
    ) in ("bot", "diagnostico", None) or out.get("diagnostico_ia")


def test_e4_escalate_no_cubre_paso():
    tel = "5492235615023"
    seed = _seed_tec(diag_turnos=4)
    cub_antes = list(seed["pasos_cubiertos"])
    org_id, conv_id = _abrir(tel, extra=seed)
    tickets: list = []
    _aplicar(
        org_id,
        conv_id,
        "ya probé de todo y sigue",
        ia={
            "accion": "escalate",
            "mensaje": "Derivo.",
            "paso_cubierto": "reinicio_ont",
            "motivo": "ia",
        },
        tickets=tickets,
    )
    ctx2 = _load_ctx(conv_id)
    assert "reinicio_ont" not in (ctx2.get("pasos_cubiertos") or [])
    assert list(ctx2.get("pasos_cubiertos") or []) == cub_antes
    cs = hydrate_conversation_state(ctx2)
    assert "reinicio_ont" not in (cs.slot("tec-1").covered_steps or [])


def test_e5_escalate_no_cambia_active_domain():
    tel = "5492235615024"
    seed = _seed_tec(diag_turnos=4)
    org_id, conv_id = _abrir(tel, extra=seed)
    before = hydrate_conversation_state(_load_ctx(conv_id)).active_domain_id
    tickets: list = []
    _aplicar(
        org_id,
        conv_id,
        "ya probé de todo y sigue",
        ia={
            "accion": "escalate",
            "mensaje": "Derivo.",
            "paso_cubierto": "wifi_vs_cable_ftth",
            "motivo": "ia",
        },
        tickets=tickets,
    )
    after = hydrate_conversation_state(_load_ctx(conv_id)).active_domain_id
    assert after == before == "tec-1"


def test_e6_heuristic_b_sigue_escalando():
    tel = "5492235615025"
    org_id, conv_id = _abrir(tel, extra=_seed_tec(diag_turnos=1))
    tickets: list = []
    out = _aplicar(
        org_id,
        conv_id,
        "ya probé todo el checklist",
        ia={
            "accion": "escalate",
            "mensaje": "Derivamos por agotamiento.",
            "paso_cubierto": "consumo_paquete",
            "motivo": "agotamiento_checklist",
        },
        tickets=tickets,
    )
    assert tickets
    assert out.get("escalate_authorized") is True
    assert out.get("escalate_source") == SOURCE_HEURISTIC
    assert out.get("modo") == "espera_agente"
    ctx = _load_ctx(conv_id)
    assert "consumo_paquete" not in (ctx.get("pasos_cubiertos") or [])


def test_e7_plant_b_sigue_escalando():
    tel = "5492235615026"
    org_id, conv_id = _abrir(tel, extra=_seed_tec(diag_turnos=0))
    tickets: list = []
    out = _aplicar(
        org_id,
        conv_id,
        "la luz los está en rojo fija",
        ia={
            "accion": "escalate",
            "mensaje": "Problema de fibra; te derivo.",
            "paso_cubierto": "",
            "motivo": "fibra_danada",
        },
        tickets=tickets,
    )
    assert tickets
    assert out.get("escalate_authorized") is True
    assert out.get("escalate_source") == SOURCE_PLANT
    assert out.get("modo") == "espera_agente"


def test_e8_regresion_resolved_suite_importable():
    """Sensor: módulos 11B siguen importables (suite completa se corre aparte)."""
    from tests import test_resolved_authority as tr

    assert callable(tr.test_r2_llm_resolved_allow_cierra)
    assert callable(tr.test_r1_llm_resolved_deny_no_cierra)


def test_integracion_productiva_procesar_mensaje_escalate_deny():
    """Flujo real: LLM escalate atraviesa proposal→policy→Motor; sin ticket."""
    tel = "5492235615027"
    org_id, conv_id = _abrir(tel, extra=_seed_tec(diag_turnos=0))
    tickets: list = []
    auth_seen: list = []

    def _ticket(*_a, **_k):
        tickets.append("x")
        return "T-BYPASS"

    import app.domain.conversation_motor as cm

    _real_auth = cm.authorize_escalate

    def _spy_auth(*a, **k):
        out = _real_auth(*a, **k)
        auth_seen.append(out)
        return out

    with (
        patch(
            "app.services.canal_abonado.resolve_canal_diagnostico_ia",
            return_value=True,
        ),
        patch(
            "app.services.diagnostico_n1.diagnosticar_turno",
            return_value={
                "accion": "escalate",
                "mensaje": "Te derivo.",
                "paso_cubierto": "reinicio_ont",
                "motivo": "ia",
            },
        ),
        patch("app.services.canal_pppoe._talvez_mensaje_pppoe", return_value=None),
        patch("app.services.canal_abonado._linea_acceso_ok_ctx", return_value=False),
        patch("app.services.canal_abonado.indica_resuelto", return_value=False),
        patch("app.services.canal_abonado._cliente_desiste_o_resuelto", return_value=False),
        patch("app.services.canal_abonado._aplicar_discurso_cs", return_value=None),
        patch("app.services.canal_abonado._crear_ticket_n2", side_effect=_ticket),
        patch("app.services.handoff_notify.notify_espera_agente", return_value=0),
        patch.object(cm, "authorize_escalate", side_effect=_spy_auth),
    ):
        # Camino productivo canónico Gate 11C (misma superficie que el canal IA).
        out = _aplicar(
            org_id,
            conv_id,
            "quiero consultar el estado otra vez",
            ia={
                "accion": "escalate",
                "mensaje": "Te derivo.",
                "paso_cubierto": "reinicio_ont",
                "motivo": "ia",
            },
            tickets=tickets,
        )
        Session = get_session_factory()
        with Session() as db:
            # Además: procesar_mensaje_entrante con el mismo mock LLM.
            out2 = procesar_mensaje_entrante(
                db,
                org_id,
                telefono=tel,
                texto="todavía en diagnóstico técnico ftth",
                canal=_CANAL,
                usar_llama=True,
            )
            db.commit()
            conv = db.get(ConversacionCanal, conv_id)
            assert conv.estado != "espera_agente"
            assert not (conv.ticket_id or "").strip()

    assert not tickets
    assert out.get("modo") != "espera_agente"
    assert out.get("escalate_authorized") is not True
    assert out2.get("estado") != "espera_agente"
    # Debe existir al menos una autorización Motor (deny) antes de cualquier ticket.
    assert auth_seen, "authorize_escalate no fue invocado"
    assert all(a.allow is False for a in auth_seen)
    assert all(a.action.type == ACT_ASK_NEXT_STEP for a in auth_seen)
    ctx2 = _load_ctx(conv_id)
    assert "reinicio_ont" not in (ctx2.get("pasos_cubiertos") or [])
    after = hydrate_conversation_state(ctx2).active_domain_id
    assert after == "tec-1"
