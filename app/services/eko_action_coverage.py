"""Cobertura declarativa Action Runtime ↔ N1 (Fase 4D).

No es un segundo registry de acciones. Reutiliza
``eko_action_runtime`` / ``eko_action_registry`` y responde:

- ¿Qué acciones de N1 están gobernadas por Runtime?
- ¿Cuáles siguen Legacy?
- ¿Cuáles tienen executor pero aún no están cableadas?

Clasificación estricta (no confundir «executor existe» con «gobernado»):

- EXECUTED_BY_RUNTIME — hot path N1 llama dispatch cuando el gate cubre
- EXECUTED_BY_LEGACY — hot path N1 solo Legacy (gate off o no cableado)
- RUNTIME_EXECUTOR_ONLY — executor registrado; N1 no despacha
- PARTIAL — Runtime en un tramo; Legacy en otro del mismo flujo
- NOT_USED — sin uso operativo N1
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.services.eko_action_bridge import (
    action_runtime_covers,
    action_runtime_master_enabled,
)
from app.services.eko_action_runtime import is_registered

CoverageStatus = Literal[
    "EXECUTED_BY_RUNTIME",
    "EXECUTED_BY_LEGACY",
    "RUNTIME_EXECUTOR_ONLY",
    "PARTIAL",
    "NOT_USED",
]

# Acciones cuyo call site N1 despacha vía bridge cuando covers() es True.
_N1_WIRED_RUNTIME: frozenset[str] = frozenset(
    {
        "show_balance",
        "show_ticket",
        "request_account_selection",
        "open_OV",
        "run_diagnostic_pppoe",
        "create_ticket",
    }
)

# Executor existe; N1 no usa dispatch (presentación / cierre / evidencia).
_EXECUTOR_ONLY: frozenset[str] = frozenset(
    {
        "send_message",
        "update_ticket",
        "escalate_human",
        "close_conversation",
    }
)

# Diagnóstico planta: PPPoE puede ir Runtime; BCM/UISP siguen Legacy en canal_pppoe.
_PARTIAL: frozenset[str] = frozenset(
    {
        "run_diagnostic_bcm",
        "run_diagnostic_uisp",
    }
)

# escalate_human en N1 se compone como create_ticket (escape agente), no como
# ActionRequest("escalate_human") independiente.
ESCALATE_COMPOSITION = "escalate_human → create_ticket (N1 escape/handoff)"


@dataclass(frozen=True)
class ActionCoverage:
    action: str
    status: CoverageStatus
    legacy_call_site: str
    runtime_call_site: str
    feature_gate: str
    executor: bool
    confirmation: str
    idempotency: str
    notes: str = ""


def _base_rows() -> list[ActionCoverage]:
    return [
        ActionCoverage(
            action="send_message",
            status="RUNTIME_EXECUTOR_ONLY",
            legacy_call_site="canal_abonado._enviar_respuesta",
            runtime_call_site="(none — N1 no despacha)",
            feature_gate="ACTION_RUNTIME_ACTIONS",
            executor=True,
            confirmation="NOT_REQUIRED",
            idempotency="SAFE",
            notes="Presentación; no side-effect de negocio vía Runtime",
        ),
        ActionCoverage(
            action="show_balance",
            status="EXECUTED_BY_RUNTIME",
            legacy_call_site="canal_abonado._responder_consulta_saldo (else)",
            runtime_call_site="canal_abonado._responder_consulta_saldo → dispatch",
            feature_gate="ACTION_RUNTIME_ENABLED + ACTIONS",
            executor=True,
            confirmation="NOT_REQUIRED",
            idempotency="SAFE",
        ),
        ActionCoverage(
            action="show_ticket",
            status="EXECUTED_BY_RUNTIME",
            legacy_call_site="(none dedicated)",
            runtime_call_site="canal_abonado consulta_ticket → dispatch",
            feature_gate="ACTION_RUNTIME_ENABLED + ACTIONS",
            executor=True,
            confirmation="NOT_REQUIRED",
            idempotency="SAFE",
            notes="Ownership vía ticket_pertenece_abonado",
        ),
        ActionCoverage(
            action="request_account_selection",
            status="EXECUTED_BY_RUNTIME",
            legacy_call_site="canal_pppoe multi_cuenta_pendiente=True",
            runtime_call_site="canal_pppoe._talvez_mensaje_pppoe → dispatch",
            feature_gate="ACTION_RUNTIME_ENABLED + ACTIONS",
            executor=True,
            confirmation="NOT_REQUIRED",
            idempotency="SAFE",
        ),
        ActionCoverage(
            action="open_OV",
            status="EXECUTED_BY_RUNTIME",
            legacy_call_site="ov_handoff.resolve_handoff",
            runtime_call_site="gesto_ov / saldo compose → dispatch",
            feature_gate="ACTION_RUNTIME_ENABLED + ACTIONS",
            executor=True,
            confirmation="NOT_REQUIRED",
            idempotency="UNKNOWN (public links only)",
            notes="Sin JSAT/SSO; solo URLs allowlisted",
        ),
        ActionCoverage(
            action="run_diagnostic_pppoe",
            status="EXECUTED_BY_RUNTIME",
            legacy_call_site="canal_pppoe.consultar_conexion_pppoe",
            runtime_call_site="canal_pppoe → dispatch (reusa estado)",
            feature_gate="ACTION_RUNTIME_ENABLED + ACTIONS",
            executor=True,
            confirmation="NOT_REQUIRED",
            idempotency="RISK (allow explícito)",
        ),
        ActionCoverage(
            action="run_diagnostic_bcm",
            status="PARTIAL",
            legacy_call_site="canal_pppoe.consultar_onu_bcm_mejor_esfuerzo",
            runtime_call_site="executor only (no dispatch N1)",
            feature_gate="ACTION_RUNTIME_ACTIONS",
            executor=True,
            confirmation="NOT_REQUIRED",
            idempotency="RISK",
            notes="Post-PPPoE Legacy; sin auto-probe en Facts",
        ),
        ActionCoverage(
            action="run_diagnostic_uisp",
            status="PARTIAL",
            legacy_call_site="canal_pppoe.consultar_cpe_uisp",
            runtime_call_site="executor only (no dispatch N1)",
            feature_gate="ACTION_RUNTIME_ACTIONS",
            executor=True,
            confirmation="NOT_REQUIRED",
            idempotency="RISK",
            notes="Post-PPPoE Legacy; sin auto-probe en Facts",
        ),
        ActionCoverage(
            action="create_ticket",
            status="EXECUTED_BY_RUNTIME",
            legacy_call_site="canal_abonado._crear_ticket_n2",
            runtime_call_site="_ticket_via_runtime_o_legacy → dispatch",
            feature_gate="ENABLED + ACTIONS (no default CSV)",
            executor=True,
            confirmation="REQUIRED (trusted)",
            idempotency="PROTECTED (conv.ticket_id)",
            notes="Fuera del set default; listar en ACTION_RUNTIME_ACTIONS",
        ),
        ActionCoverage(
            action="update_ticket",
            status="RUNTIME_EXECUTOR_ONLY",
            legacy_call_site="canal_abonado._append_evidencia_ticket",
            runtime_call_site="(none — N1 no despacha)",
            feature_gate="ACTION_RUNTIME_ACTIONS (explícito)",
            executor=True,
            confirmation="NOT_REQUIRED",
            idempotency="PROTECTED",
            notes="Ownership en executor; gap de cableado N1",
        ),
        ActionCoverage(
            action="escalate_human",
            status="RUNTIME_EXECUTOR_ONLY",
            legacy_call_site="escape → create_ticket / espera_agente",
            runtime_call_site="executor; N1 compone create_ticket",
            feature_gate="ACTION_RUNTIME_ACTIONS (explícito)",
            executor=True,
            confirmation="REQUIRED",
            idempotency="PROTECTED",
            notes=ESCALATE_COMPOSITION,
        ),
        ActionCoverage(
            action="close_conversation",
            status="RUNTIME_EXECUTOR_ONLY",
            legacy_call_site="canal_abonado._cerrar_consulta_resuelta",
            runtime_call_site="(none — N1 no despacha)",
            feature_gate="ACTION_RUNTIME_ACTIONS (explícito)",
            executor=True,
            confirmation="REQUIRED",
            idempotency="PROTECTED",
            notes="Cierre Legacy + CSAT; no forzar migración 4D",
        ),
    ]


def coverage_matrix() -> list[ActionCoverage]:
    """Inventario estático de cobertura (independiente del flag runtime)."""
    rows = _base_rows()
    for row in rows:
        if not is_registered(row.action) and row.executor:
            # Registry debe estar bootstrapped
            from app.services.eko_action_runtime import bootstrap_registry

            bootstrap_registry()
    return rows


def coverage_for(action: str) -> ActionCoverage | None:
    name = (action or "").strip()
    for row in coverage_matrix():
        if row.action == name:
            return row
    return None


def effective_execution_path(action: str) -> Literal["runtime", "legacy", "none"]:
    """Path efectivo en este proceso según feature gate."""
    name = (action or "").strip()
    row = coverage_for(name)
    if row is None:
        return "none"
    if row.status == "RUNTIME_EXECUTOR_ONLY":
        return "legacy" if name != "send_message" else "none"
    if row.status == "PARTIAL":
        # BCM/UISP: siempre Legacy en hot path N1 hoy
        return "legacy"
    if row.status == "EXECUTED_BY_RUNTIME":
        if action_runtime_covers(name):
            return "runtime"
        return "legacy"
    if row.status == "EXECUTED_BY_LEGACY":
        return "legacy"
    return "none"


def runtime_governed_actions() -> list[str]:
    """Acciones con cableado N1 que el gate puede gobernar."""
    return sorted(_N1_WIRED_RUNTIME)


def executor_only_actions() -> list[str]:
    return sorted(_EXECUTOR_ONLY)


def partial_actions() -> list[str]:
    return sorted(_PARTIAL)


def rollout_snapshot() -> dict[str, object]:
    """Resumen operable para logs/tests sin PII."""
    enabled = action_runtime_master_enabled()
    governed = []
    legacy = []
    for name in runtime_governed_actions():
        if enabled and action_runtime_covers(name):
            governed.append(name)
        else:
            legacy.append(name)
    return {
        "action_runtime_enabled": enabled,
        "runtime_governed_now": governed,
        "legacy_fallback_now": legacy,
        "executor_only": executor_only_actions(),
        "partial": partial_actions(),
        "escalate_composition": ESCALATE_COMPOSITION,
    }
