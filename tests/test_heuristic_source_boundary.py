"""Gate 13C — frontera SOURCE_HEURISTIC: LLM no escala por contenido de motivo."""

from __future__ import annotations

from unittest.mock import patch

from sqlalchemy import select

from app.domain.action_proposal import (
    SOURCE_HEURISTIC,
    SOURCE_LLM,
    SOURCE_PLANT,
    evaluate_escalate,
    infer_proposal_source,
    proposal_from_diag_result,
    sanitize_llm_claimed_motivo,
)
from app.domain.conversation_state import CS_KEY, KIND_TECNICO
from app.domain.domain_lifecycle import cover_and_note, create_domain, new_conversation_state
from app.estate import canal_repo as crepo
from app.estate.database import get_session_factory
from app.estate.models import Abonado, ConversacionCanal, Organization
from app.services.canal_diagnostico_ia import _aplicar_diagnostico_ia

_DNI = "30111222"
_CANAL = "whatsapp"

_LLM_HEURISTIC_CLAIMS = [
    "bcm_timeout",
    "bcm_sin_respuesta",
    "uisp_bad_signal",
    "fibra_danada",
    "fibra_dañada",
    "los_confirmada",
    "pon_verde",
    "e1_forzado",
    "guardrail",
    "frustracion",
    "derivacion",
    "agotamiento_checklist",
    "cliente_persiste",
    "optical fault",
    "falla de planta",
    "BMC_TIMEOUT",
    "Bcm_Timeout",
    "bcm-timeout",
    "bcm timeout",
    "bcm_timeout pero no estoy seguro",
    "motivo=bcm_timeout",
    "bcm_timeout; escalar",
    "heuristic:bcm_timeout",
    "guardrail=true",
]


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
        base[CS_KEY] = _cs_tec(["energia_ont"]).to_dict()
        if extra:
            base.update(extra)
        crepo.set_contexto(conv, base)
        db.commit()
        return org_id, conv.id


def _aplicar(org_id: str, conv_id: str, texto: str, *, ia: dict, tickets: list):
    Session = get_session_factory()
    with Session() as db:
        conv = db.get(ConversacionCanal, conv_id)
        abo = db.get(Abonado, conv.abonado_id) if conv and conv.abonado_id else None
        ctx = crepo.get_contexto(conv)
        assert conv and abo

        def _ticket(*_a, **_k):
            tickets.append("x")
            return "T-13C"

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


def test_llm_motivo_cannot_upgrade_to_heuristic_source():
    """Gate 13C: motivo LLM conocido B → SOURCE_LLM, no HEURISTIC, no ticket."""
    for raw in (
        "agotamiento_checklist",
        "bcm_timeout",
        "optical fault",
        "falla de planta",
        "cliente_persiste",
    ):
        sanitized = sanitize_llm_claimed_motivo(raw)
        assert sanitized.startswith("ia_") or sanitized == "ia"
        assert infer_proposal_source({"motivo": sanitized}) == SOURCE_LLM
        p = proposal_from_diag_result(
            {
                "accion": "escalate",
                "motivo": sanitized,
                "mensaje": "Te derivo.",
                "paso_cubierto": "",
            }
        )
        assert p.source == SOURCE_LLM
        assert p.source != SOURCE_HEURISTIC
        d = evaluate_escalate(
            p, "sigue igual", turnos_diagnostico=0, intencion="internet_ftth"
        )
        assert d.allow is False, raw

    tel = "5492235618010"
    org_id, conv_id = _abrir(tel, extra={"diag_turnos": 0})
    tickets: list = []
    out = _aplicar(
        org_id,
        conv_id,
        "sigue igual",
        ia={
            "accion": "escalate",
            "mensaje": "Derivamos.",
            "paso_cubierto": "consumo_paquete",
            "motivo": sanitize_llm_claimed_motivo("agotamiento_checklist"),
        },
        tickets=tickets,
    )
    assert not tickets
    assert out.get("escalate_authorized") is not True
    assert out.get("escalate_source") != SOURCE_HEURISTIC
    assert out.get("modo") != "espera_agente"


def test_13c_variantes_adversariales_nunca_heuristic():
    for raw in _LLM_HEURISTIC_CLAIMS:
        src = infer_proposal_source({"motivo": sanitize_llm_claimed_motivo(raw)})
        assert src == SOURCE_LLM, f"{raw!r} → {src}"
        assert src != SOURCE_HEURISTIC


def test_13c_escalate_combinaciones_llm_no_allow():
    for motivo in (
        "bcm_timeout",
        "uisp_bad_signal",
        "fibra_danada",
        "agotamiento_checklist",
        "optical fault",
    ):
        p = proposal_from_diag_result(
            {
                "accion": "escalate",
                "motivo": sanitize_llm_claimed_motivo(motivo),
                "mensaje": "Te derivo.",
                "paso_cubierto": "",
            }
        )
        assert p.source == SOURCE_LLM
        d = evaluate_escalate(p, "x", turnos_diagnostico=0, intencion="internet_ftth")
        assert d.allow is False


def test_13c_b_real_heuristic_sigue():
    """Ruta B sin pasar por sanitize LLM: motivo crudo → HEURISTIC → allow."""
    p = proposal_from_diag_result(
        {
            "accion": "escalate",
            "motivo": "agotamiento_checklist",
            "mensaje": "Derivamos.",
            "paso_cubierto": "",
        }
    )
    assert p.source == SOURCE_HEURISTIC
    d = evaluate_escalate(p, "sigue igual", turnos_diagnostico=0, intencion="internet_ftth")
    assert d.allow is True


def test_13c_b_real_plant_sigue():
    p = proposal_from_diag_result(
        {
            "accion": "escalate",
            "motivo": "fibra_danada",
            "mensaje": "Fibra.",
            "paso_cubierto": "",
        }
    )
    assert p.source == SOURCE_PLANT
    d = evaluate_escalate(p, "los roja", turnos_diagnostico=0, intencion="internet_ftth")
    assert d.allow is True


def test_13c_b_real_heuristic_ticket_productivo():
    tel = "5492235618011"
    org_id, conv_id = _abrir(tel, extra={"diag_turnos": 1})
    tickets: list = []
    out = _aplicar(
        org_id,
        conv_id,
        "ya probé todo",
        ia={
            "accion": "escalate",
            "mensaje": "Derivamos por agotamiento.",
            "paso_cubierto": "",
            "motivo": "agotamiento_checklist",
        },
        tickets=tickets,
    )
    assert tickets
    assert out.get("escalate_source") == SOURCE_HEURISTIC
    assert out.get("escalate_authorized") is True
