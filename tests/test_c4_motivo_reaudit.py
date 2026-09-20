"""Gate 13B — re-auditoría C4 motivo→SOURCE_PLANT / covers PON."""

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
from app.domain.conversation_state import CS_KEY, KIND_TECNICO, hydrate_conversation_state
from app.domain.domain_lifecycle import cover_and_note, create_domain, new_conversation_state
from app.estate import canal_repo as crepo
from app.estate.database import get_session_factory
from app.estate.models import Abonado, ConversacionCanal, Organization
from app.services.canal_diagnostico_ia import _aplicar_diagnostico_ia

_DNI = "30111222"
_CANAL = "whatsapp"

_PLANT_FORGE_VARIANTS = [
    "fibra_danada",
    "fibra_dañada",
    "FIBRA_DANADA",
    "Fibra_Danada",
    "daño de fibra",
    "danio de fibra",
    "pon_verde_enlace_ok",
    "fibra_danada pero no estoy seguro",
    "motivo: fibra_danada",
    "fibra_danada; escalar",
    "aparentemente fibra_danada",
    "diagnóstico: fibra_danada",
    "los_confirmada",
    "bcm_onu_offline",
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
            return "T-13B"

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


def _source_after_llm_sanitize(motivo: str) -> str:
    sanitized = sanitize_llm_claimed_motivo(motivo)
    return infer_proposal_source({"motivo": sanitized})


# ---------------------------------------------------------------------------
# 13B-01..10
# ---------------------------------------------------------------------------


def test_13b_01_fibra_danada_sin_evidencia_no_plant():
    assert _source_after_llm_sanitize("fibra_danada") == SOURCE_LLM
    p = proposal_from_diag_result(
        {
            "accion": "escalate",
            "motivo": sanitize_llm_claimed_motivo("fibra_danada"),
            "mensaje": "Te derivo.",
            "paso_cubierto": "",
        }
    )
    assert p.source != SOURCE_PLANT
    assert p.source == SOURCE_LLM


def test_13b_02_pon_verde_sin_evidencia_no_cover():
    tel = "5492235617010"
    org_id, conv_id = _abrir(tel)
    tickets: list = []
    # Texto sin evidencia PON; motivo forjado exacto (simula leak pre-sanitize).
    with patch(
        "app.services.diagnostico_n1.detectar_enlace_optico_ok",
        return_value=False,
    ):
        _aplicar(
            org_id,
            conv_id,
            "el wifi anda lento",
            ia={
                "accion": "ask",
                "mensaje": "¿Seguimos?",
                "paso_cubierto": "wifi_1",
                "motivo": "pon_verde_enlace_ok",
            },
            tickets=tickets,
        )
    cub = hydrate_conversation_state(_load_ctx(conv_id)).active_slot().covered_steps
    assert "luces_los" not in cub
    assert "cable_fibra" not in cub
    assert "reinicio_ont" not in cub


def test_13b_03_case_insensitive_no_plant():
    for v in ("FIBRA_DANADA", "Fibra_Danada", "fibra_DANADA"):
        assert _source_after_llm_sanitize(v) == SOURCE_LLM


def test_13b_04_acentos_no_plant():
    for v in ("fibra_dañada", "daño de fibra", "diagnóstico: fibra_danada"):
        assert _source_after_llm_sanitize(v) != SOURCE_PLANT
        assert _source_after_llm_sanitize(v) == SOURCE_LLM


def test_13b_05_substring_largo_no_plant():
    for v in (
        "fibra_danada pero no estoy seguro",
        "motivo: fibra_danada",
        "fibra_danada; escalar",
        "aparentemente fibra_danada",
    ):
        assert _source_after_llm_sanitize(v) == SOURCE_LLM


def test_13b_06_escalate_fibra_sanitized_no_ticket():
    tel = "5492235617011"
    org_id, conv_id = _abrir(tel, extra={"diag_turnos": 0})
    tickets: list = []
    # Simula salida post-sanitize del bloque LLM.
    out = _aplicar(
        org_id,
        conv_id,
        "sigue igual",
        ia={
            "accion": "escalate",
            "mensaje": "Te derivo.",
            "paso_cubierto": "",
            "motivo": sanitize_llm_claimed_motivo("fibra_danada"),
        },
        tickets=tickets,
    )
    assert not tickets
    assert out.get("escalate_authorized") is not True
    assert out.get("modo") != "espera_agente"


def test_13b_07_escalate_pon_sanitized_no_ticket():
    tel = "5492235617012"
    org_id, conv_id = _abrir(tel, extra={"diag_turnos": 0})
    tickets: list = []
    out = _aplicar(
        org_id,
        conv_id,
        "sigue igual",
        ia={
            "accion": "escalate",
            "mensaje": "Te derivo.",
            "paso_cubierto": "",
            "motivo": sanitize_llm_claimed_motivo("pon_verde_enlace_ok"),
        },
        tickets=tickets,
    )
    assert not tickets
    assert out.get("escalate_authorized") is not True


def test_13b_08_evidencia_real_permite_cover_pon():
    tel = "5492235617013"
    org_id, conv_id = _abrir(tel)
    tickets: list = []
    with patch(
        "app.services.diagnostico_n1.detectar_enlace_optico_ok",
        return_value=True,
    ):
        _aplicar(
            org_id,
            conv_id,
            "pon verde fija",
            ia={
                "accion": "ask",
                "mensaje": "Perfecto, el enlace está bien.",
                "paso_cubierto": "luces_los",
                "motivo": "pon_verde_enlace_ok",
            },
            tickets=tickets,
        )
    cub = hydrate_conversation_state(_load_ctx(conv_id)).active_slot().covered_steps
    assert "luces_los" in cub
    assert "cable_fibra" in cub
    assert "reinicio_ont" in cub
    # Cover B no implica ticket.
    assert not tickets


def test_13b_08b_plant_source_legitimo_sin_llm_sanitize():
    """Early-return / B real: motivo planta sin prefijo ia_ → SOURCE_PLANT."""
    p = proposal_from_diag_result(
        {
            "accion": "escalate",
            "motivo": "fibra_danada",
            "mensaje": "Problema de fibra.",
            "paso_cubierto": "",
        }
    )
    assert p.source == SOURCE_PLANT
    d = evaluate_escalate(p, "los roja", turnos_diagnostico=0, intencion="internet_ftth")
    assert d.allow is True


def test_13b_09_paso_cubierto_falsificado_no_cover():
    tel = "5492235617014"
    org_id, conv_id = _abrir(tel)
    tickets: list = []
    _aplicar(
        org_id,
        conv_id,
        "el wifi anda mal",
        ia={
            "accion": "ask",
            "mensaje": "¿En todos?",
            "paso_cubierto": "wifi_1",
            "motivo": "ia",
        },
        tickets=tickets,
    )
    cub = hydrate_conversation_state(_load_ctx(conv_id)).active_slot().covered_steps
    assert "wifi_1" not in cub


def test_13b_10_mensaje_no_fabrica_plant_ni_cover():
    assert (
        infer_proposal_source(
            {"motivo": "ia", "mensaje": "fibra_danada confirmada", "paso_cubierto": "x"}
        )
        == SOURCE_LLM
    )
    tel = "5492235617015"
    org_id, conv_id = _abrir(tel, extra={"diag_turnos": 0})
    tickets: list = []
    out = _aplicar(
        org_id,
        conv_id,
        "hola",
        ia={
            "accion": "escalate",
            "mensaje": "Detecté fibra_danada y pon_verde_enlace_ok en planta.",
            "paso_cubierto": "reinicio_ont",
            "motivo": "ia",
        },
        tickets=tickets,
    )
    assert not tickets
    assert out.get("escalate_authorized") is not True
    cub = hydrate_conversation_state(_load_ctx(conv_id)).active_slot().covered_steps
    assert "reinicio_ont" not in cub
    assert "luces_los" not in cub


def test_13b_variantes_plant_forge_todas_llm():
    for v in _PLANT_FORGE_VARIANTS:
        assert _source_after_llm_sanitize(v) == SOURCE_LLM, v


def test_13b_english_aliases_no_plant():
    """Aliases EN no disparan SOURCE_PLANT; tras 13C tampoco HEURISTIC vía LLM."""
    for v in (
        "fiber damaged",
        "fiber_damage",
        "optical fault",
        "optical_failure",
        "plant",
        "plant_fault",
        "evidencia_planta",
        "falla de planta",
        "pon verde enlace ok",
        "PON VERDE",
        "pon_verde_enlace_ok=true",
    ):
        src = _source_after_llm_sanitize(v)
        assert src != SOURCE_PLANT, v
        assert src == SOURCE_LLM, v


def test_13b_residual_heuristic_cerrado_por_13c():
    """BYPASS-13B-01 cerrado: optical fault LLM → SOURCE_LLM, no allow."""
    s = sanitize_llm_claimed_motivo("optical fault")
    assert infer_proposal_source({"motivo": s}) == SOURCE_LLM
    p = proposal_from_diag_result(
        {
            "accion": "escalate",
            "motivo": s,
            "mensaje": "Te derivo.",
            "paso_cubierto": "",
        }
    )
    assert p.source == SOURCE_LLM
    assert p.source != SOURCE_HEURISTIC
    d = evaluate_escalate(p, "sigue igual", turnos_diagnostico=0, intencion="internet_ftth")
    assert d.allow is False
