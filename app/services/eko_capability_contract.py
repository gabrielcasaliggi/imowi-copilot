"""Agentic Ops Capability Contract — Fase 4E.

Definición operacional
----------------------
Agentic Ops = Eko puede seleccionar y ejecutar una acción operacional
dentro de un conjunto cerrado de capacidades registradas, sujeto a
Policy, Authorization, Confirmation, Context State, Idempotency y Safety Gates.

NO significa LLM → tool libre / API arbitraria / side effect directo.

Flujo válido::

    LLM / Decision → ActionRequest → Registered Capability
        → Policy → Trusted Context → Executor → ActionResult

Este módulo NO es un segundo registry. Reutiliza:
- ``eko_action_runtime`` (ActionSpec, Policy, executors)
- ``eko_action_coverage`` (N1 Runtime vs Legacy)

Solo agrega metadata de contrato: tipo, riesgo, precondiciones, canales,
lifecycle y fronteras de autoridad.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.services.eko_action_bridge import action_runtime_covers, action_runtime_master_enabled
from app.services.eko_action_coverage import (
    ESCALATE_COMPOSITION,
    coverage_for,
    coverage_matrix,
)
from app.services.eko_action_runtime import (
    get_action,
    is_registered,
    list_registered_actions,
)

# ---------------------------------------------------------------------------
# Capas (arquitectura — no mezclar)
# ---------------------------------------------------------------------------

LAYER_FACTS = "FACTS"  # customer/account/service/billing/support factual
LAYER_STATE = "STATE"  # conversation / workflow / eko_action.*
LAYER_TECHNICAL_OBS = "TECHNICAL_OBSERVATIONS"  # Radius/BCM/UISP/outage
LAYER_ACTIONS = "ACTIONS"  # side effects vía Runtime

# ---------------------------------------------------------------------------
# LLM Contract
# ---------------------------------------------------------------------------

LLM_MAY = frozenset(
    {
        "classify_intent",
        "interpret_user_input",
        "propose_action",
        "provide_non_authoritative_parameters",
        "compose_response",
    }
)

LLM_MAY_NOT = frozenset(
    {
        "authorize",
        "confirm",
        "choose_subscriber_identity",
        "bypass_ownership",
        "choose_unregistered_capability",
        "execute_arbitrary_code_or_tool",
        "override_policy",
        "override_multi_account_gate",
        "trigger_technical_probes_implicitly",
    }
)

# ---------------------------------------------------------------------------
# Authority boundaries
# ---------------------------------------------------------------------------

AUTHORITY_BOUNDARIES: dict[str, str] = {
    "LLM": "interpret / classify / propose / compose — never authority",
    "Facts": "factual reality; never authorization; never ActionResult",
    "State": "conversation/workflow/eko_action.*; holds confirmation pending",
    "Decision": "selects registered capability or Legacy path",
    "Policy": "eko_action_runtime.evaluate_policy — sole allow/deny/needs_*",
    "Runtime": "execute_action allowlist; TrustedContext from backend",
    "Legacy": "bounded compatibility when gate off or not wired",
    "TechnicalReaders": "explicit diagnostic only; never auto in Facts",
}

# ---------------------------------------------------------------------------
# Confirmation / Authorization contracts
# ---------------------------------------------------------------------------

CONFIRMATION_CONTRACT = (
    "Trusted Confirmation = resolve_user_confirmation(historial|STATE) "
    "→ TrustedContext.confirmation_received. "
    "Never LLM.confirmation_received. Never decision_engine.auto_confirmado."
)

AUTHORIZATION_CONTRACT = (
    "Authorization = Trusted Identity + Trusted Ownership + Policy. "
    "Identity from conv/abonado/readers. LLM params (abonado_id, dni, "
    "authorized, confirmation_received, ticket ownership) are sanitized."
)

DIAGNOSTIC_BOUNDARY = {
    "normal_conversation": {"probes": 0, "rule": "build_eko_facts / decision → zero readers"},
    "explicit_diagnostic": {
        "probes": "exactly required reader",
        "rule": "ActionRequest diagnostic → specialized reader",
    },
    "multi_account_no_selection": {
        "probes": 0,
        "rule": "NEEDS_INPUT; Radius=BCM=UISP=0",
    },
}

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

CapabilityType = Literal[
    "READ",
    "PRESENTATION",
    "NAVIGATION",
    "DIAGNOSTIC",
    "MUTATION",
    "ESCALATION",
]

RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]

LifecycleState = Literal[
    "DISCOVERED",
    "REGISTERED",
    "POLICY_DEFINED",
    "TESTED",
    "RUNTIME_READY",
    "CHANNEL_ENABLED",
    "PRODUCTION_ENABLED",
]

Channel = Literal["n1", "whatsapp", "telegram", "portal", "mobile", "helpdesk"]

# Canales donde N1 Runtime puede aplicar (mismo hot path canal_abonado).
_N1_CHANNELS: frozenset[str] = frozenset({"n1", "whatsapp", "telegram", "portal"})


@dataclass(frozen=True)
class CapabilityContract:
    """Contrato declarativo de una capability registrada."""

    name: str
    domain: str
    type: CapabilityType
    risk: RiskLevel
    requires_confirmation: bool
    requires_identity: bool
    requires_service_selection: bool
    requires_diagnostic_intent: bool
    requires_authorization: bool
    idempotent: str  # SAFE | PROTECTED | RISK | UNKNOWN (+ strategy note)
    side_effect: str
    allowed_channels: frozenset[str]
    runtime_status: str  # from coverage
    legacy_fallback: str
    lifecycle: LifecycleState
    preconditions: tuple[str, ...]
    postconditions: tuple[str, ...]
    migration_precondition: str = ""
    why_legacy: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "domain": self.domain,
            "type": self.type,
            "risk": self.risk,
            "requires_confirmation": self.requires_confirmation,
            "requires_identity": self.requires_identity,
            "requires_service_selection": self.requires_service_selection,
            "requires_diagnostic_intent": self.requires_diagnostic_intent,
            "requires_authorization": self.requires_authorization,
            "idempotent": self.idempotent,
            "side_effect": self.side_effect,
            "allowed_channels": sorted(self.allowed_channels),
            "runtime_status": self.runtime_status,
            "legacy_fallback": self.legacy_fallback,
            "lifecycle": self.lifecycle,
            "preconditions": list(self.preconditions),
            "postconditions": list(self.postconditions),
            "migration_precondition": self.migration_precondition,
            "why_legacy": self.why_legacy,
            "notes": self.notes,
        }


# Metadata de contrato (no duplica ActionSpec; complementa).
# confirmation/requires_abonado/idempotency se leen del registry al ensamblar.
_CONTRACT_META: dict[str, dict[str, Any]] = {
    "send_message": {
        "domain": "presentation",
        "type": "PRESENTATION",
        "risk": "LOW",
        "requires_service_selection": False,
        "requires_diagnostic_intent": False,
        "requires_authorization": False,
        "side_effect": "USER_VISIBLE_NO_MUTATION",
        "allowed_channels": _N1_CHANNELS | frozenset({"mobile", "helpdesk"}),
        "preconditions": ("registered_capability",),
        "postconditions": ("ActionResult.success|failed", "no_business_mutation"),
        "why_legacy": "N1 usa _enviar_respuesta; Runtime executor opcional",
        "migration_precondition": "low value; keep presentation outside Runtime",
        "idempotency_strategy": "SAFE (no mutation)",
    },
    "show_balance": {
        "domain": "billing",
        "type": "READ",
        "risk": "LOW",
        "requires_service_selection": False,
        "requires_diagnostic_intent": False,
        "requires_authorization": True,
        "side_effect": "READ_ONLY",
        "allowed_channels": _N1_CHANNELS | frozenset({"mobile"}),
        "preconditions": ("identity=trusted", "facts.billing"),
        "postconditions": (
            "ActionResult.success|unavailable",
            "no_mutation",
            "stale≠live",
            "unavailable≠al_día",
        ),
        "idempotency_strategy": "SAFE",
    },
    "show_ticket": {
        "domain": "support",
        "type": "READ",
        "risk": "LOW",
        "requires_service_selection": False,
        "requires_diagnostic_intent": False,
        "requires_authorization": True,
        "side_effect": "READ_ONLY",
        "allowed_channels": _N1_CHANNELS | frozenset({"mobile"}),
        "preconditions": ("identity=trusted", "ticket_ownership=true"),
        "postconditions": (
            "ActionResult.success|denied",
            "foreign_ticket→DENIED",
            "no_foreign_leak",
        ),
        "idempotency_strategy": "SAFE",
    },
    "request_account_selection": {
        "domain": "connectivity",
        "type": "PRESENTATION",
        "risk": "LOW",
        "requires_service_selection": False,  # this capability IS the selection ask
        "requires_diagnostic_intent": False,
        "requires_authorization": True,
        "side_effect": "USER_VISIBLE_NO_MUTATION",
        "allowed_channels": _N1_CHANNELS,
        "preconditions": ("identity=trusted", "multiple_internet_accounts"),
        "postconditions": (
            "STATE.multi_cuenta_pendiente=true",
            "NEEDS_INPUT path for diagnostics",
            "zero_probes",
        ),
        "idempotency_strategy": "SAFE",
    },
    "open_OV": {
        "domain": "ov_navigation",
        "type": "NAVIGATION",
        "risk": "LOW",
        "requires_service_selection": False,
        "requires_diagnostic_intent": False,
        "requires_authorization": False,
        "side_effect": "EXTERNAL_SIDE_EFFECT",
        "allowed_channels": _N1_CHANNELS | frozenset({"mobile"}),
        "preconditions": ("destination_allowlisted",),
        "postconditions": (
            "public_URL",
            "no_JSAT",
            "no_Eko_auth_mutation",
        ),
        "idempotency_strategy": "UNKNOWN (public links only)",
        "notes": "auth=external; no SSO simulation",
    },
    "run_diagnostic_pppoe": {
        "domain": "connectivity",
        "type": "DIAGNOSTIC",
        "risk": "MEDIUM",
        "requires_service_selection": True,
        "requires_diagnostic_intent": True,
        "requires_authorization": True,
        "side_effect": "EXTERNAL_SIDE_EFFECT",
        "allowed_channels": _N1_CHANNELS,
        "preconditions": (
            "identity=trusted",
            "explicit_diagnostic_intent",
            "login_seleccionado OR single_account",
        ),
        "postconditions": (
            "technical_observation",
            "ActionResult→STATE",
            "no_auto_ticket",
        ),
        "idempotency_strategy": "RISK (explicit allow; one reader)",
    },
    "run_diagnostic_bcm": {
        "domain": "connectivity",
        "type": "DIAGNOSTIC",
        "risk": "MEDIUM",
        "requires_service_selection": True,
        "requires_diagnostic_intent": True,
        "requires_authorization": True,
        "side_effect": "EXTERNAL_SIDE_EFFECT",
        "allowed_channels": _N1_CHANNELS,
        "preconditions": (
            "identity=trusted",
            "explicit_diagnostic_intent",
            "selected_service",
        ),
        "postconditions": ("technical_observation", "ActionResult→STATE"),
        "why_legacy": "Post-PPPoE path in canal_pppoe still calls BCM reader directly",
        "migration_precondition": (
            "Wire dispatch without changing diagnostic semantics / double probe"
        ),
        "idempotency_strategy": "RISK",
    },
    "run_diagnostic_uisp": {
        "domain": "connectivity",
        "type": "DIAGNOSTIC",
        "risk": "MEDIUM",
        "requires_service_selection": True,
        "requires_diagnostic_intent": True,
        "requires_authorization": True,
        "side_effect": "EXTERNAL_SIDE_EFFECT",
        "allowed_channels": _N1_CHANNELS,
        "preconditions": (
            "identity=trusted",
            "explicit_diagnostic_intent",
            "selected_login",
        ),
        "postconditions": ("technical_observation", "ActionResult→STATE"),
        "why_legacy": "Post-PPPoE path in canal_pppoe still calls UISP reader directly",
        "migration_precondition": (
            "Wire dispatch without changing diagnostic semantics / double probe"
        ),
        "idempotency_strategy": "RISK",
    },
    "create_ticket": {
        "domain": "support",
        "type": "MUTATION",
        "risk": "HIGH",
        "requires_service_selection": False,
        "requires_diagnostic_intent": False,
        "requires_authorization": True,
        "side_effect": "MUTATING",
        "allowed_channels": _N1_CHANNELS,
        "preconditions": (
            "identity=trusted",
            "confirmation=trusted",
            "idempotency=conv.ticket_id",
        ),
        "postconditions": (
            "ticket_id",
            "STATE.eko_action",
            "already_done_if_exists",
            "no_legacy_fallback_on_deny",
        ),
        "idempotency_strategy": "PROTECTED: conv.ticket_id → ALREADY_DONE",
        "notes": "Not in default ACTION_RUNTIME_ACTIONS CSV",
    },
    "update_ticket": {
        "domain": "support",
        "type": "MUTATION",
        "risk": "HIGH",
        "requires_service_selection": False,
        "requires_diagnostic_intent": False,
        "requires_authorization": True,
        "side_effect": "MUTATING",
        "allowed_channels": _N1_CHANNELS | frozenset({"helpdesk"}),
        "preconditions": (
            "identity=trusted",
            "ticket_ownership=true",
            "ticket_id_from_trusted_context",
        ),
        "postconditions": ("evidencia_appended", "no_foreign_ticket"),
        "why_legacy": "N1 uses _append_evidencia_ticket; Runtime not dispatched",
        "migration_precondition": "Explicit N1 call site + no behavior change",
        "idempotency_strategy": "PROTECTED: ownership + existing dedup",
    },
    "escalate_human": {
        "domain": "support",
        "type": "ESCALATION",
        "risk": "HIGH",
        "requires_service_selection": False,
        "requires_diagnostic_intent": False,
        "requires_authorization": True,
        "side_effect": "MUTATING",
        "allowed_channels": _N1_CHANNELS,
        "preconditions": ("identity=trusted", "confirmation=trusted"),
        "postconditions": ("espera_agente|ticket", "no_parallel_ticket_writer"),
        "why_legacy": ESCALATE_COMPOSITION,
        "migration_precondition": "Decide if escalate≠create_ticket before wiring",
        "idempotency_strategy": "PROTECTED (composition via create_ticket)",
        "notes": ESCALATE_COMPOSITION,
    },
    "close_conversation": {
        "domain": "support",
        "type": "MUTATION",
        "risk": "HIGH",
        "requires_service_selection": False,
        "requires_diagnostic_intent": False,
        "requires_authorization": True,
        "side_effect": "MUTATING",
        "allowed_channels": _N1_CHANNELS,
        "preconditions": ("identity=trusted", "confirmation when Runtime path"),
        "postconditions": ("conv.estado=cerrado", "optional_CSAT"),
        "why_legacy": "N1 _cerrar_consulta_resuelta + encuesta; Lifecycle complex",
        "migration_precondition": "Preserve CSAT/cierre semantics before Runtime wire",
        "idempotency_strategy": "PROTECTED: estado=cerrado → ALREADY_DONE",
    },
}

REQUIRED_CONTRACT_FIELDS = frozenset(
    {
        "name",
        "domain",
        "type",
        "risk",
        "requires_confirmation",
        "requires_identity",
        "requires_service_selection",
        "requires_diagnostic_intent",
        "requires_authorization",
        "idempotent",
        "side_effect",
        "allowed_channels",
        "runtime_status",
        "legacy_fallback",
        "lifecycle",
        "preconditions",
        "postconditions",
    }
)


def _lifecycle_for(name: str, coverage_status: str) -> LifecycleState:
    """Distingue executor existe vs production enabled."""
    if coverage_status == "EXECUTED_BY_RUNTIME":
        if action_runtime_master_enabled() and action_runtime_covers(name):
            return "PRODUCTION_ENABLED"
        # Cableado N1 + policy/tests; flag off o no listado → no producción
        return "CHANNEL_ENABLED"
    if coverage_status == "PARTIAL":
        return "RUNTIME_READY"
    if coverage_status == "RUNTIME_EXECUTOR_ONLY":
        return "TESTED"
    if coverage_status == "EXECUTED_BY_LEGACY":
        return "POLICY_DEFINED"
    return "REGISTERED"


def build_capability(name: str) -> CapabilityContract | None:
    """Ensambla contrato desde registry + coverage + metadata 4E."""
    name = (name or "").strip()
    meta = _CONTRACT_META.get(name)
    if meta is None:
        return None
    if not is_registered(name):
        from app.services.eko_action_runtime import bootstrap_registry

        bootstrap_registry()
    spec = get_action(name)
    cov = coverage_for(name)
    if spec is None or cov is None:
        return None

    requires_identity = bool(spec.requires_abonado)
    requires_confirmation = bool(spec.confirmation_required)
    idem = meta.get("idempotency_strategy") or spec.idempotency

    return CapabilityContract(
        name=name,
        domain=str(meta["domain"]),
        type=meta["type"],
        risk=meta["risk"],
        requires_confirmation=requires_confirmation,
        requires_identity=requires_identity,
        requires_service_selection=bool(meta["requires_service_selection"]),
        requires_diagnostic_intent=bool(meta["requires_diagnostic_intent"]),
        requires_authorization=bool(meta["requires_authorization"]),
        idempotent=str(idem),
        side_effect=str(meta["side_effect"]),
        allowed_channels=frozenset(meta["allowed_channels"]),
        runtime_status=cov.status,
        legacy_fallback=cov.legacy_call_site,
        lifecycle=_lifecycle_for(name, cov.status),
        preconditions=tuple(meta["preconditions"]),
        postconditions=tuple(meta["postconditions"]),
        migration_precondition=str(meta.get("migration_precondition") or ""),
        why_legacy=str(meta.get("why_legacy") or ""),
        notes=str(meta.get("notes") or cov.notes or ""),
    )


def all_capabilities() -> list[CapabilityContract]:
    """Todas las capabilities del contrato (orden estable)."""
    out: list[CapabilityContract] = []
    for name in sorted(_CONTRACT_META.keys()):
        cap = build_capability(name)
        if cap is not None:
            out.append(cap)
    return out


def capability_matrix_rows() -> list[dict[str, Any]]:
    """Filas para informe / tests (sin PII)."""
    rows = []
    for cap in all_capabilities():
        rows.append(
            {
                "capability": cap.name,
                "type": cap.type,
                "risk": cap.risk,
                "confirmation": cap.requires_confirmation,
                "selection": cap.requires_service_selection,
                "diagnostic": cap.requires_diagnostic_intent,
                "authorization": cap.requires_authorization,
                "idempotent": cap.idempotent,
                "n1_runtime": cap.runtime_status,
                "legacy": cap.legacy_fallback,
                "lifecycle": cap.lifecycle,
                "status": cap.runtime_status,
            }
        )
    return rows


def channel_allows(capability: str, channel: str) -> bool:
    """REGISTERED ≠ ENABLED FOR CHANNEL."""
    cap = build_capability(capability)
    if cap is None:
        return False
    ch = (channel or "").strip().lower()
    if ch in ("whatsapp", "telegram", "portal", "web"):
        # web portal bot = n1 path
        return ch in cap.allowed_channels or "n1" in cap.allowed_channels
    return ch in cap.allowed_channels


def is_agentic_decision(*, action: str, passed_runtime: bool) -> bool:
    """Agentic solo si pasó por capability registrada + Runtime/Policy.

    LLM text o proposal sin Runtime NO es agentic.
    """
    if not passed_runtime:
        return False
    if not is_registered(action):
        return False
    return build_capability(action) is not None


def contract_invariants() -> dict[str, Any]:
    """Snapshot verificable del contrato (tests / ops)."""
    registered = set(list_registered_actions())
    contracted = set(_CONTRACT_META.keys())
    coverage_names = {r.action for r in coverage_matrix()}
    return {
        "llm_may": sorted(LLM_MAY),
        "llm_may_not": sorted(LLM_MAY_NOT),
        "confirmation_contract": CONFIRMATION_CONTRACT,
        "authorization_contract": AUTHORIZATION_CONTRACT,
        "diagnostic_boundary": DIAGNOSTIC_BOUNDARY,
        "authority_boundaries": AUTHORITY_BOUNDARIES,
        "layers": [LAYER_FACTS, LAYER_STATE, LAYER_TECHNICAL_OBS, LAYER_ACTIONS],
        "registered_equals_contracted": registered == contracted,
        "coverage_equals_contracted": coverage_names == contracted,
        "capability_count": len(contracted),
        "escalate_composition": ESCALATE_COMPOSITION,
        "action_runtime_enabled": action_runtime_master_enabled(),
    }


def protocolo_mesa_boundary() -> dict[str, str]:
    """Frontera acotada — no migrar en 4E."""
    return {
        "status": "MIXED_BOUNDED",
        "bypass_policy": "no — no invoke execute_action/tools from LLM text",
        "side_effects_outside_runtime": "presentation/playbook only; tickets via canal writers",
        "llm_arbitrary_activation": "no — gated by domain/intencion/playbook",
        "double_runtime_action": "no Runtime dispatch in protocolo_mesa",
        "note": "Keep outside mass Agentic Ops migration",
    }
