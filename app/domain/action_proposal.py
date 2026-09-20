"""Propuestas de acción irreversible (Gate 11A/11C).

El LLM / heurísticas / planta proponen; la policy decide; el Motor autoriza.
El canal ejecuta efectos. Nunca es cover (contrato 10B).
"""

from __future__ import annotations

from dataclasses import dataclass

SOURCE_LLM = "llm"
SOURCE_HEURISTIC = "heuristic"
SOURCE_PLANT = "plant"
SOURCE_GUARDRAIL = "guardrail"
SOURCE_HUMAN = "human"

ACTION_RESOLVED = "resolved"
ACTION_ASK = "ask"
ACTION_ESCALATE = "escalate"

# Motivos de planta / óptica / telemetría (no LLM).
_PLANT_MOTIVOS = frozenset(
    {
        "fibra_danada",
        "los_con_chequeo_fibra",
        "los_y_fibra_danada",
        "los_confirmada",
        "bloqueado_wifi_post_los",
        "pon_verde_enlace_ok",
        "dano_campo",
        "dano_fisico_campo",
        "cable_arrancado",
        "lectura_forzada_e1",
        "e1_acceso_malo",
        "e1_agotado",
    }
)

_HUMAN_MOTIVOS = frozenset(
    {
        "pedido_humano",
        "escape_agente",
        "pide_humano",
    }
)


@dataclass
class ActionProposal:
    """Sugerencia no autoritativa. step_hint ≠ cover (contrato 10B)."""

    action: str
    source: str
    reason: str = ""
    message: str = ""
    step_hint: str | None = None


@dataclass
class PolicyDecision:
    allow: bool
    reason: str
    message: str = ""
    demote_to: str = ACTION_ASK


_PLANT_CLAIM_MARKERS = (
    "fibra",
    "los_",
    "onu_",
    "bcm",
    "uisp",
    "e1_",
    "olt",
    "wis",
    "dano_campo",
    "daño",
)


def sanitize_llm_claimed_motivo(motivo: str) -> str:
    """Gate 13C: todo motivo del JSON LLM es claim, nunca autoridad B/H.

    Contenido ≠ autoridad. Aunque el texto coincida con un motivo heurístico
    o de planta conocido, el origen LLM no puede producir SOURCE_HEURISTIC
    ni SOURCE_PLANT. Las asignaciones determinísticas *después* de este
    sanitizado (guardrails, LOS, early-return fuera del bloque LLM) usan
    motivos sin prefijo ``ia_`` y conservan su source legítimo.
    """
    m = (motivo or "").strip()
    if not m:
        return "ia"
    ml = m.lower()
    if ml == "ia" or ml.startswith("ia_") or ml.startswith("ia "):
        return m[:200]
    return f"ia_{ml}"[:200]


def infer_proposal_source(result: dict | None) -> str:
    """Clasifica fuente sin degradar B a C.

    Gate 13: prefijos ``ia_`` / ``ia `` tienen prioridad sobre marcadores de
    planta; un LLM que forgea ``motivo=fibra_danada`` no obtiene SOURCE_PLANT.
    """
    raw = result if isinstance(result, dict) else {}
    motivo = str(raw.get("motivo") or "").strip().lower()
    # Claims LLM primero: nunca upgrade por substring de planta.
    if not motivo or motivo == "ia" or motivo.startswith("ia_") or motivo.startswith("ia "):
        return SOURCE_LLM
    if motivo in _HUMAN_MOTIVOS or any(
        x in motivo for x in ("pedido_humano", "pide_agente", "escape")
    ):
        return SOURCE_HUMAN
    if motivo in _PLANT_MOTIVOS or any(x in motivo for x in _PLANT_CLAIM_MARKERS):
        return SOURCE_PLANT
    return SOURCE_HEURISTIC


def proposal_from_diag_result(result: dict | None, *, message: str = "") -> ActionProposal:
    raw = result if isinstance(result, dict) else {}
    accion = str(raw.get("accion") or "").strip().lower() or ACTION_ASK
    hint = str(raw.get("paso_cubierto") or "").strip() or None
    return ActionProposal(
        action=accion,
        source=infer_proposal_source(raw),
        reason=str(raw.get("motivo") or "").strip()[:200],
        message=(message or str(raw.get("mensaje") or "")).strip(),
        step_hint=hint,
    )


def evaluate_resolved(
    proposal: ActionProposal,
    mensaje_cliente: str,
) -> PolicyDecision:
    """Policy de cierre: reutiliza demociones ya existentes en diagnostico_n1.

    No inventa reglas nuevas. No cubre pasos.
    """
    from app.domain.flujos_abonado import confirma_contacto_sin_servicio

    if proposal.action != ACTION_RESOLVED:
        return PolicyDecision(
            allow=False,
            reason="not_resolved_proposal",
            message=proposal.message,
            demote_to=ACTION_ASK,
        )

    if confirma_contacto_sin_servicio(mensaje_cliente):
        return PolicyDecision(
            allow=False,
            reason="bloqueado_resolved_solo_contacto",
            message=(
                "Buenísimo que te hayan contestado. "
                "¿Ya te anda el servicio o seguís con el mismo problema?"
            ),
            demote_to=ACTION_ASK,
        )

    t = (mensaje_cliente or "").lower()
    if any(
        k in t
        for k in (
            "no anda",
            "no funciona",
            "sigue",
            "problema",
            "falla",
            "sin internet",
            "no me",
            "quisiera",
            "consultar",
        )
    ):
        return PolicyDecision(
            allow=False,
            reason="bloqueado_resolved_con_sintoma",
            message=proposal.message
            or (
                "Contame un poco más: ¿seguís sin servicio o ya te quedó andando?"
            ),
            demote_to=ACTION_ASK,
        )

    return PolicyDecision(
        allow=True,
        reason=proposal.reason or "resolved_ok",
        message=proposal.message,
        demote_to=ACTION_ASK,
    )


def evaluate_escalate(
    proposal: ActionProposal,
    mensaje_cliente: str,
    *,
    turnos_diagnostico: int = 0,
    intencion: str = "",
) -> PolicyDecision:
    """Policy de escalate: reutiliza guardrails de diagnostico_n1 (min turnos, etc.).

    LLM solo: no autoriza por sí mismo si faltan turnos.
    plant/human/heuristic B: allow (salvo democión de cierre léxico).
    """
    from app.domain.flujos_abonado import intencion_es_facturacion
    from app.services.diagnostico_n1 import (
        MIN_TURNOS_ANTES_ESCALAR,
        _cierra_consulta_facturacion,
        _cliente_pide_envio_boleta_o_factura,
        _cliente_pide_pagar,
    )

    if proposal.action != ACTION_ESCALATE:
        return PolicyDecision(
            allow=False,
            reason="not_escalate_proposal",
            message=proposal.message,
            demote_to=ACTION_ASK,
        )

    # Cierre léxico: no escalar (misma democión que el canal).
    if _cierra_consulta_facturacion(mensaje_cliente):
        return PolicyDecision(
            allow=False,
            reason="bloqueado_escalate_cierre_facturacion",
            message=proposal.message,
            demote_to=ACTION_ASK,
        )

    # Fuentes B: conservar autoridad (no degradar a exigir turnos LLM).
    if proposal.source in (SOURCE_PLANT, SOURCE_HUMAN):
        return PolicyDecision(
            allow=True,
            reason=proposal.reason or f"escalate_{proposal.source}",
            message=proposal.message,
        )

    if proposal.source == SOURCE_HEURISTIC:
        return PolicyDecision(
            allow=True,
            reason=proposal.reason or "escalate_heuristic",
            message=proposal.message,
        )

    # --- LLM (C): no basta con el JSON ---
    turnos = max(0, int(turnos_diagnostico or 0))
    motivo = (proposal.reason or "").strip().lower()
    excepciones_min = frozenset(
        {
            "fibra_danada",
            "los_con_chequeo_fibra",
            "los_y_fibra_danada",
            "los_confirmada",
            "bloqueado_wifi_post_los",
            "pack_acreditado_sin_datos",
            "pedido_humano",
        }
    )
    if turnos < MIN_TURNOS_ANTES_ESCALAR and motivo not in excepciones_min:
        return PolicyDecision(
            allow=False,
            reason="bloqueado_escalate_min_turnos",
            message=proposal.message
            or "Contame un poco más del problema para seguir el diagnóstico.",
            demote_to=ACTION_ASK,
        )

    if intencion_es_facturacion(intencion) and (
        _cliente_pide_envio_boleta_o_factura(mensaje_cliente)
        or _cliente_pide_pagar(mensaje_cliente)
    ):
        return PolicyDecision(
            allow=False,
            reason="bloqueado_escalate_facturacion",
            message=proposal.message,
            demote_to=ACTION_ASK,
        )

    return PolicyDecision(
        allow=True,
        reason=proposal.reason or "escalate_llm_ok",
        message=proposal.message,
        demote_to=ACTION_ASK,
    )
