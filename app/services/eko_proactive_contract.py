"""Eko 2.3D/G-B — tipos canónicos ProactiveEvent / ProactiveDecision.

Documentación: docs/EKO-2.3B / 2.3C / 2.3G-B. Sin ledger ni scheduler.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

PolicyDecisionKind = Literal["ALLOW", "SUPPRESS", "NOT_ELIGIBLE", "INVALID"]

SourceAuthority = Literal[
    "AUTHORITATIVE",
    "TRUSTED_READ",
    "DERIVED",
    "UNKNOWN",
]

EVENT_VERSION = 1
POLICY_VERSION = "eko-proactive-policy-1"

# Eventos habilitados para delivery (outage 2.3D + ticket 2.3G-B).
SUPPORTED_PROACTIVE_EVENTS: frozenset[str] = frozenset(
    {
        "outage.started",
        "outage.material_update",
        "outage.resolved",
        "ticket.created",
        "ticket.updated",
        "ticket.closed",
        # ticket.resolved: UNSUPPORTED — no hay estado Resuelto en estate.
    }
)

# Payload Expo legacy (mobile parsea declared|updated|resolved).
OUTAGE_EVENT_TO_LEGACY_PUSH: dict[str, str] = {
    "outage.started": "declared",
    "outage.material_update": "updated",
    "outage.resolved": "resolved",
}

# Contrato mobile 2.3G-M: event ∈ created|updated|resolved|closed|"".
TICKET_EVENT_TO_LEGACY_PUSH: dict[str, str] = {
    "ticket.created": "created",
    "ticket.updated": "updated",
    "ticket.closed": "closed",
}


@dataclass
class ProactiveEvent:
    """Hecho normalizado. No proviene del LLM."""

    event_type: str
    source: str
    source_event_id: str
    source_authority: SourceAuthority = "AUTHORITATIVE"
    event_id: str = ""
    event_version: int = EVENT_VERSION
    customer_scope: str = ""
    service_scope: str = ""
    outage_id: str = ""
    client_number: str = ""
    ticket_id: str = ""
    service_id: str = ""
    organizacion_id: str = ""
    customer_message: str = ""
    customer_title: str = ""
    facts: dict[str, Any] = field(default_factory=dict)
    channel: str = "app_push"


@dataclass
class ProactiveDecision:
    """Resultado de policy (2.3C). El adapter solo actúa si decision=ALLOW."""

    decision: PolicyDecisionKind
    event: ProactiveEvent
    policy_version: str = POLICY_VERSION
    suppression_reason: str | None = None
    reason: str = ""
    channel: str = "app_push"

    @property
    def event_type(self) -> str:
        return self.event.event_type

    @property
    def allowed(self) -> bool:
        return self.decision == "ALLOW"
