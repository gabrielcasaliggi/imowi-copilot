"""Eko 2.3D/E/G-B — Proactive Push Adapter.

Traduce ProactiveDecision(ALLOW) → app_push existente.
No evalúa policy, no resuelve ownership, no llama LLM.
XOR outage: API outages. Ticket: post-commit TicketEvent detector.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.services import app_push
from app.services.eko_proactive_contract import (
    OUTAGE_EVENT_TO_LEGACY_PUSH,
    SUPPORTED_PROACTIVE_EVENTS,
    TICKET_EVENT_TO_LEGACY_PUSH,
    ProactiveDecision,
)

logger = logging.getLogger("operations_hub")


def deliver_proactive_push(
    db: Session,
    decision: ProactiveDecision,
    *,
    nas_shortname: str = "",
    nas_ip: str = "",
) -> dict[str, Any]:
    """Ejecuta delivery solo si decision.ALLOW y event_type soportado."""
    event = decision.event
    et = decision.event_type
    is_ticket = et.startswith("ticket.")
    source_id = (
        (event.source_event_id or "").strip()
        if is_ticket
        else (event.outage_id or event.source_event_id or "").strip()
    )
    event_id = (event.event_id or f"{et}:{source_id}").strip()

    base: dict[str, Any] = {
        "ok": True,
        "sent": 0,
        "decision": decision.decision,
        "event_type": et,
        "event_id": event_id,
        "source_event_id": source_id,
        "policy_version": decision.policy_version,
        "suppression_reason": decision.suppression_reason,
        "delivery_path": "proactive_adapter",
        "customer_scope": event.customer_scope or "",
    }

    if decision.decision != "ALLOW":
        logger.info(
            "proactive_push skipped decision=%s reason=%s event_type=%s "
            "event_id=%s source_event_id=%s",
            decision.decision,
            decision.suppression_reason or decision.reason,
            et,
            event_id[:48],
            source_id[:36],
        )
        return {
            **base,
            "skipped": decision.suppression_reason or decision.decision,
        }

    if et not in SUPPORTED_PROACTIVE_EVENTS:
        return {
            **base,
            "ok": True,
            "decision": "NOT_ELIGIBLE",
            "skipped": "SIGNAL_NOT_SUPPORTED",
            "suppression_reason": "SIGNAL_NOT_SUPPORTED",
        }

    org_id = (event.organizacion_id or "").strip()
    if not org_id or not source_id:
        return {
            **base,
            "ok": True,
            "decision": "SUPPRESS",
            "skipped": "OWNERSHIP_UNRESOLVED",
            "suppression_reason": "OWNERSHIP_UNRESOLVED",
            "sent": 0,
        }

    if is_ticket:
        ticket_id = (event.ticket_id or "").strip()
        if not ticket_id:
            return {
                **base,
                "ok": True,
                "decision": "SUPPRESS",
                "skipped": "OWNERSHIP_UNRESOLVED",
                "suppression_reason": "OWNERSHIP_UNRESOLVED",
                "sent": 0,
            }
        legacy = TICKET_EVENT_TO_LEGACY_PUSH.get(et, "")
        body = (event.customer_message or "").strip()
        title = (event.customer_title or "").strip()
        logger.info(
            "proactive_push attempt event_type=%s event_id=%s source_event_id=%s "
            "ticket_id=%s policy=%s legacy_event=%s",
            et,
            event_id[:48],
            source_id[:36],
            ticket_id[:32],
            decision.policy_version,
            legacy,
        )
        result = app_push.notificar_ticket_app(
            db,
            org_id,
            ticket_id=ticket_id,
            ticket_event_id=source_id,
            event=legacy,
            title=title or "Tu solicitud",
            body=body or title or "Hay una novedad en tu solicitud.",
        )
    else:
        nas = (nas_shortname or "").strip()
        nip = (nas_ip or "").strip()
        body = (event.customer_message or "").strip()
        title = (event.customer_title or "").strip()
        outage_id = source_id

        logger.info(
            "proactive_push attempt event_type=%s event_id=%s source_event_id=%s "
            "policy=%s customer_scope=%s legacy_event=%s",
            et,
            event_id[:48],
            outage_id[:36],
            decision.policy_version,
            event.customer_scope or "",
            OUTAGE_EVENT_TO_LEGACY_PUSH.get(et, ""),
        )

        if et == "outage.started":
            result = app_push.notificar_incidente_app(
                db,
                org_id,
                title=title or app_push.TITLE_DECLARED,
                body=body,
                outage_id=outage_id,
                nas_shortname=nas,
                nas_ip=nip,
            )
        elif et == "outage.material_update":
            result = app_push.notificar_incidente_actualizado_app(
                db,
                org_id,
                outage_id=outage_id,
                nas_shortname=nas,
                nas_ip=nip,
                body=body or title or app_push.TITLE_UPDATED,
                title=title or app_push.TITLE_UPDATED,
            )
        elif et == "outage.resolved":
            result = app_push.notificar_incidente_resuelto_app(
                db,
                org_id,
                outage_id=outage_id,
                nas_shortname=nas,
                nas_ip=nip,
            )
        else:
            return {
                **base,
                "skipped": "SIGNAL_NOT_SUPPORTED",
                "suppression_reason": "SIGNAL_NOT_SUPPORTED",
            }

    provider_ok = bool(result.get("ok"))
    sent = int(result.get("sent") or 0)
    error_category = str(result.get("error_category") or "")
    out = {
        **base,
        **result,
        "ok": provider_ok,
        "sent": sent,
        "decision": "ALLOW",
        "event_type": et,
        "event_id": event_id,
        "source_event_id": source_id,
        "policy_version": decision.policy_version,
        "delivery_path": "proactive_adapter",
        "provider_ok": provider_ok,
        "error_category": error_category,
        "retryable": bool(result.get("retryable")),
    }
    if result.get("skipped"):
        out["skipped"] = result.get("skipped")
    mid = result.get("provider_message_ids") or []
    logger.info(
        "proactive_push result event_type=%s event_id=%s source_event_id=%s "
        "sent=%s provider_ok=%s skipped=%s error_category=%s retryable=%s "
        "provider_msg_ids=%s device_tokens=%s",
        et,
        event_id[:48],
        source_id[:36],
        sent,
        provider_ok,
        out.get("skipped"),
        error_category,
        out.get("retryable"),
        len(mid) if isinstance(mid, list) else 0,
        result.get("device_tokens"),
    )
    return out
