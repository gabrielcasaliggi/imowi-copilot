"""Eko 2.3G-B — detector proactivo de TicketEvent (customer-visible only).

Autoridad: TicketEvent. Identidad: TicketEvent.id. LLM = cero.
No reutiliza claims de outage. Delivery vía eko_proactive_push + app_push.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.estate.models import TicketEvent
from app.services.eko_proactive_contract import (
    TICKET_EVENT_TO_LEGACY_PUSH,
    ProactiveEvent,
)
from app.services.eko_proactive_policy import evaluate_proactive_notification
from app.services.eko_proactive_push import deliver_proactive_push

logger = logging.getLogger("operations_hub")

# Presentación solamente — no es fuente de verdad del evento.
_TICKET_COPY: dict[str, tuple[str, str]] = {
    "ticket.created": (
        "Solicitud recibida",
        "Recibimos tu solicitud. Podés ver el detalle en Actividad.",
    ),
    "ticket.updated": (
        "Actualización de tu solicitud",
        "Tu solicitud tiene una actualización. Revisala en Actividad.",
    ),
    "ticket.closed": (
        "Solicitud cerrada",
        "Tu solicitud fue cerrada. Revisá el detalle en Actividad.",
    ),
}

# Tipos operativos/internos: nunca push al abonado aunque visible_cliente=Sí por defecto.
_INTERNAL_TIPOS = frozenset(
    {
        "nota_interna",
        "reasignacion",
        "paso_operativo",
        "resumen_noc",
        "kb_propuesta",
        "kb_publicada",
        "kb_rechazada",
        "aprendizaje",
        "csat_bajo",
        "contexto_sms",
        "cierre_masivo",
    }
)


def is_ticket_event_customer_visible(ev: TicketEvent) -> bool:
    """Gate determinístico: flag explícito + no tipo interno."""
    flag = str(getattr(ev, "visible_cliente", "") or "").strip().lower()
    if flag not in ("sí", "si", "yes", "true", "1"):
        return False
    tipo = str(getattr(ev, "tipo", "") or "").strip().lower()
    if not tipo or tipo in _INTERNAL_TIPOS:
        return False
    return True


def map_ticket_event_type(ev: TicketEvent) -> str | None:
    """Mapea tipo/estado a ticket.* canónico. None = unsupported/ambiguous.

    ticket.resolved: UNSUPPORTED — ESTADOS_TICKET_VALIDOS no incluye Resuelto;
    cierre de ciclo = Cerrado → ticket.closed.
    """
    tipo = str(getattr(ev, "tipo", "") or "").strip().lower()
    estado = str(getattr(ev, "estado", "") or "").strip()

    if tipo == "creacion":
        return "ticket.created"
    if tipo == "nota":
        return "ticket.updated"
    if tipo == "actualizacion":
        if estado == "Cerrado":
            return "ticket.closed"
        return "ticket.updated"
    return None


def ticket_event_to_proactive_event(ev: TicketEvent) -> ProactiveEvent | None:
    """Construye ProactiveEvent o None si el gate/mapping fallan."""
    if not is_ticket_event_customer_visible(ev):
        return None
    et = map_ticket_event_type(ev)
    if not et or et not in TICKET_EVENT_TO_LEGACY_PUSH:
        return None
    eid = str(getattr(ev, "id", "") or "").strip()
    tid = str(getattr(ev, "ticket_id", "") or "").strip()
    org = str(getattr(ev, "organizacion_id", "") or "").strip()
    if not eid or not tid or not org:
        return None
    title, body = _TICKET_COPY[et]
    occurred = getattr(ev, "created_at", None)
    return ProactiveEvent(
        event_type=et,
        source="estate.ticket_events",
        source_event_id=eid,
        source_authority="AUTHORITATIVE",
        event_id=f"{et}:{eid}",
        ticket_id=tid,
        organizacion_id=org,
        customer_scope="ticket_owner",
        customer_title=title,
        customer_message=body,
        facts={
            "occurred_at": occurred.isoformat() if occurred else "",
            "ticket_event_tipo": str(getattr(ev, "tipo", "") or ""),
            "legacy_push_event": TICKET_EVENT_TO_LEGACY_PUSH[et],
        },
        channel="app_push",
    )


def maybe_deliver_ticket_event_push(db: Session, ev: TicketEvent) -> dict[str, Any]:
    """Post-commit: gate → policy → deliver. Nunca lanza al caller de add_ticket_event."""
    base: dict[str, Any] = {
        "ok": True,
        "sent": 0,
        "ticket_event_id": str(getattr(ev, "id", "") or ""),
        "ticket_id": str(getattr(ev, "ticket_id", "") or ""),
        "delivery_path": "ticket_proactive",
    }
    try:
        pe = ticket_event_to_proactive_event(ev)
        if pe is None:
            logger.info(
                "ticket_proactive suppress ticket_event_id=%s ticket_id=%s "
                "reason=gate_or_unsupported tipo=%s visible=%s",
                base["ticket_event_id"][:36],
                base["ticket_id"][:32],
                str(getattr(ev, "tipo", "") or ""),
                str(getattr(ev, "visible_cliente", "") or ""),
            )
            return {
                **base,
                "skipped": "GATE_OR_UNSUPPORTED",
                "suppression_reason": "GATE_OR_UNSUPPORTED",
            }

        decision = evaluate_proactive_notification(pe)
        if not decision.allowed:
            logger.info(
                "ticket_proactive policy ticket_event_id=%s ticket_id=%s "
                "event_type=%s decision=%s reason=%s",
                pe.source_event_id[:36],
                pe.ticket_id[:32],
                pe.event_type,
                decision.decision,
                decision.suppression_reason or decision.reason,
            )
            return {
                **base,
                "decision": decision.decision,
                "event_type": pe.event_type,
                "skipped": decision.suppression_reason or decision.decision,
                "suppression_reason": decision.suppression_reason,
            }

        result = deliver_proactive_push(db, decision)
        logger.info(
            "ticket_proactive result ticket_event_id=%s ticket_id=%s event_type=%s "
            "sent=%s provider_ok=%s skipped=%s error_category=%s",
            pe.source_event_id[:36],
            pe.ticket_id[:32],
            pe.event_type,
            result.get("sent"),
            result.get("provider_ok", result.get("ok")),
            result.get("skipped"),
            result.get("error_category"),
        )
        return {**base, **result, "event_type": pe.event_type}
    except Exception:
        logger.warning(
            "ticket_proactive failed ticket_event_id=%s ticket_id=%s",
            base["ticket_event_id"][:36],
            base["ticket_id"][:32],
            exc_info=True,
        )
        return {
            **base,
            "ok": False,
            "skipped": "DETECTOR_ERROR",
            "error_category": "internal",
        }
