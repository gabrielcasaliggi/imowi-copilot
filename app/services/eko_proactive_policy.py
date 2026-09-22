"""Eko 2.3D — policy mínima para notificaciones proactivas.

No crea hechos. No resuelve devices. No llama Expo.
Solo ALLOW / SUPPRESS / NOT_ELIGIBLE / INVALID según 2.3C.
"""

from __future__ import annotations

from typing import Any

from app.services.eko_proactive_contract import (
    POLICY_VERSION,
    SUPPORTED_PROACTIVE_EVENTS,
    ProactiveDecision,
    ProactiveEvent,
    SourceAuthority,
)


def evaluate_proactive_notification(event: ProactiveEvent) -> ProactiveDecision:
    """Evalúa un ProactiveEvent. Determinístico; sin LLM."""
    et = (event.event_type or "").strip()
    if not et:
        return ProactiveDecision(
            decision="INVALID",
            event=event,
            suppression_reason="EVENT_INVALID",
            reason="missing_event_type",
            channel=event.channel or "app_push",
        )

    if et not in SUPPORTED_PROACTIVE_EVENTS:
        return ProactiveDecision(
            decision="NOT_ELIGIBLE",
            event=event,
            suppression_reason="SIGNAL_NOT_SUPPORTED",
            reason=f"event_type_not_enabled:{et}",
            channel=event.channel or "app_push",
        )

    auth = event.source_authority or "UNKNOWN"
    if auth not in ("AUTHORITATIVE", "TRUSTED_READ"):
        return ProactiveDecision(
            decision="SUPPRESS",
            event=event,
            suppression_reason="SOURCE_NOT_AUTHORIZED",
            reason=f"source_authority={auth}",
            channel=event.channel or "app_push",
        )
    # Outages requieren AUTHORITATIVE (ops declare), no TRUSTED_READ solo.
    if et.startswith("outage.") and auth != "AUTHORITATIVE":
        return ProactiveDecision(
            decision="SUPPRESS",
            event=event,
            suppression_reason="SOURCE_NOT_AUTHORIZED",
            reason="outage_requires_authoritative",
            channel=event.channel or "app_push",
        )
    if et.startswith("ticket.") and auth != "AUTHORITATIVE":
        return ProactiveDecision(
            decision="SUPPRESS",
            event=event,
            suppression_reason="SOURCE_NOT_AUTHORIZED",
            reason="ticket_requires_authoritative",
            channel=event.channel or "app_push",
        )

    if (event.channel or "app_push").strip() not in ("", "app_push"):
        return ProactiveDecision(
            decision="SUPPRESS",
            event=event,
            suppression_reason="CHANNEL_UNAVAILABLE",
            reason=f"channel_not_enabled:{event.channel}",
            channel=event.channel,
        )

    oid = (event.outage_id or event.source_event_id or "").strip()
    org = (event.organizacion_id or "").strip()
    if et.startswith("outage.") and (not oid or not org):
        return ProactiveDecision(
            decision="SUPPRESS",
            event=event,
            suppression_reason="OWNERSHIP_UNRESOLVED",
            reason="missing_outage_id_or_org",
            channel="app_push",
        )

    tid = (event.ticket_id or "").strip()
    teid = (event.source_event_id or "").strip()
    if et.startswith("ticket.") and (not tid or not teid or not org):
        return ProactiveDecision(
            decision="SUPPRESS",
            event=event,
            suppression_reason="OWNERSHIP_UNRESOLVED",
            reason="missing_ticket_id_or_event_id_or_org",
            channel="app_push",
        )

    msg = (event.customer_message or "").strip()
    if et == "outage.resolved":
        # Body fijo en delivery; mensaje vacío OK.
        pass
    elif et.startswith("outage.") and not msg:
        return ProactiveDecision(
            decision="INVALID",
            event=event,
            suppression_reason="EVENT_INVALID",
            reason="missing_customer_message",
            channel="app_push",
        )
    elif et.startswith("ticket.") and not msg:
        return ProactiveDecision(
            decision="INVALID",
            event=event,
            suppression_reason="EVENT_INVALID",
            reason="missing_customer_message",
            channel="app_push",
        )

    return ProactiveDecision(
        decision="ALLOW",
        event=event,
        policy_version=POLICY_VERSION,
        reason="allow",
        channel="app_push",
    )


def suppress_decision(
    event: ProactiveEvent,
    *,
    reason_code: str,
    detail: str = "",
) -> ProactiveDecision:
    """Factory para tests / callers que ya decidieron SUPPRESS."""
    return ProactiveDecision(
        decision="SUPPRESS",
        event=event,
        suppression_reason=reason_code,
        reason=detail or reason_code,
        channel=event.channel or "app_push",
    )


def authorize_outage_push(
    *,
    event_type: str,
    org_id: str,
    outage_id: str,
    customer_message: str = "",
    customer_title: str = "",
    source: str = "estate.network_outages",
    source_authority: SourceAuthority = "AUTHORITATIVE",
    facts: dict[str, Any] | None = None,
) -> ProactiveDecision:
    """Construye evento de outage lifecycle y evalúa policy (camino API)."""
    oid = (outage_id or "").strip()
    event = ProactiveEvent(
        event_type=(event_type or "").strip(),
        source=source,
        source_event_id=oid,
        source_authority=source_authority,
        event_id=f"{event_type}:{oid}" if oid else "",
        outage_id=oid,
        organizacion_id=(org_id or "").strip(),
        customer_scope="outage_fanout",
        customer_message=customer_message or "",
        customer_title=customer_title or "",
        facts=dict(facts or {}),
        channel="app_push",
    )
    return evaluate_proactive_notification(event)
