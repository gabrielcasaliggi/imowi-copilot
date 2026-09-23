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
    "ticket.sla_breached": (
        "Plazo de atención",
        "Tu ticket superó el plazo previsto de atención. "
        "Podés consultar el estado y el detalle desde Eko.",
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

# 2.6D/E — proyección portal (allowlist). actualizacion solo si Cerrado → closed.
_PORTAL_CUSTOMER_TIPOS = frozenset({"creacion", "nota", "sla_breach"})
CUSTOMER_NOTE_MAX_LEN = 800
CUSTOMER_NOTE_TITLE = "Actualización"


def is_ticket_event_customer_visible(ev: TicketEvent) -> bool:
    """Gate determinístico: flag explícito + no tipo interno."""
    flag = str(getattr(ev, "visible_cliente", "") or "").strip().lower()
    if flag not in ("sí", "si", "yes", "true", "1"):
        return False
    tipo = str(getattr(ev, "tipo", "") or "").strip().lower()
    if not tipo or tipo in _INTERNAL_TIPOS:
        return False
    return True


def is_self_note_actor(actor: str) -> bool:
    """N1 abonado self-note: Event visible, push SUPPRESS (2.6D materiality)."""
    a = str(actor or "").strip().lower()
    return a == "abonado" or a.startswith("abonado:")


def is_portal_customer_event(ev: TicketEvent) -> bool:
    """Proyección portal 2.6E: allowlist + cierre; sin migration de históricos."""
    flag = str(getattr(ev, "visible_cliente", "") or "").strip().lower()
    if flag not in ("sí", "si", "yes", "true", "1"):
        return False
    tipo = str(getattr(ev, "tipo", "") or "").strip().lower()
    if not tipo or tipo in _INTERNAL_TIPOS:
        return False
    if tipo == "actualizacion":
        return str(getattr(ev, "estado", "") or "").strip() == "Cerrado"
    return tipo in _PORTAL_CUSTOMER_TIPOS


def sanitize_customer_note_message(raw: str) -> str:
    """Mensaje customer-safe: trim + max length. Sin campos Ticket."""
    return str(raw or "").strip()[:CUSTOMER_NOTE_MAX_LEN]


def map_ticket_event_type(ev: TicketEvent) -> str | None:
    """Mapea tipo/estado a ticket.* canónico. None = unsupported/ambiguous.

    ticket.resolved: UNSUPPORTED — ESTADOS_TICKET_VALIDOS no incluye Resuelto;
    cierre de ciclo = Cerrado → ticket.closed.
    ticket.sla_breached: tipo=sla_breach (2.6A); no reinterpretar actualizacion.
    """
    tipo = str(getattr(ev, "tipo", "") or "").strip().lower()
    estado = str(getattr(ev, "estado", "") or "").strip()

    if tipo == "creacion":
        return "ticket.created"
    if tipo == "sla_breach":
        return "ticket.sla_breached"
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
    # SLA: no notificar si el evento quedó asociado a ticket ya cerrado.
    if et == "ticket.sla_breached":
        estado_ev = str(getattr(ev, "estado", "") or "").strip()
        if estado_ev == "Cerrado":
            return None
    eid = str(getattr(ev, "id", "") or "").strip()
    tid = str(getattr(ev, "ticket_id", "") or "").strip()
    org = str(getattr(ev, "organizacion_id", "") or "").strip()
    if not eid or not tid or not org:
        return None
    title, body = _TICKET_COPY[et]
    occurred = getattr(ev, "created_at", None)
    facts: dict[str, Any] = {
        "occurred_at": occurred.isoformat() if occurred else "",
        "ticket_event_tipo": str(getattr(ev, "tipo", "") or ""),
        "legacy_push_event": TICKET_EVENT_TO_LEGACY_PUSH[et],
    }
    if et == "ticket.sla_breached":
        # Semántica: sla_breached_at en Ticket = deadline vencido (no wall-clock).
        # En el evento, created_at ≈ detected_at; deadline va en facts si está en detalle.
        detalle = str(getattr(ev, "detalle", "") or "").strip()
        if detalle.startswith("sla_breached_at="):
            facts["sla_breached_at"] = detalle.split("=", 1)[1].strip()
            facts["occurred_at"] = facts["sla_breached_at"] or facts["occurred_at"]
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
        facts=facts,
        channel="app_push",
    )


def emit_ticket_customer_note(
    db: Session,
    org_id: str,
    ticket_id: str,
    mensaje: str,
    *,
    actor: str,
    abonado: Any | None = None,
    agent_authorized: bool = False,
    nivel: str = "",
    estado: str = "",
) -> TicketEvent | None:
    """2.6E/G ACT ticket_customer_note → TicketEvent(tipo=nota, visible=Sí).

    Ownership defensivo (2.6G):
    - ``abonado`` presente → ``ticket_pertenece_abonado`` obligatorio.
    - ``agent_authorized=True`` → ticket existe en org (caller API agente ya RBAC).
    - sin ninguno → DENY (no confiar en el caller a ciegas).

    Idempotente por (ticket, detalle). Self-note (actor abonado*) → no push.
    """
    from sqlalchemy import select

    from app.estate import repository as repo
    from app.estate.models import Ticket
    from app.services.abonado_tickets import ticket_pertenece_abonado

    tid = str(ticket_id or "").strip()
    org = str(org_id or "").strip()
    msg = sanitize_customer_note_message(mensaje)
    act = str(actor or "").strip() or "sistema"
    if not tid or not org or not msg:
        return None

    t = repo.get_ticket(db, org, tid)
    if t is None or not isinstance(t, Ticket):
        return None

    if abonado is not None:
        if not ticket_pertenece_abonado(db, org, abonado, t):
            return None
    elif not agent_authorized:
        return None

    existing = db.scalar(
        select(TicketEvent).where(
            TicketEvent.organizacion_id == org,
            TicketEvent.ticket_id == tid,
            TicketEvent.tipo == "nota",
            TicketEvent.detalle == msg,
        )
    )
    if existing is not None:
        return existing

    return repo.add_ticket_event(
        db,
        org,
        tid,
        tipo="nota",
        titulo=CUSTOMER_NOTE_TITLE,
        detalle=msg,
        nivel=nivel or str(t.nivel or ""),
        estado=estado or str(t.estado or ""),
        actor=act,
        visible_cliente="Sí",
    )


def emit_customer_sla_breach_event(db: Session, ticket: Any) -> TicketEvent | None:
    """Emite TicketEvent tipo=sla_breach en la transición NULL→sla_breached_at.

    Reutiliza add_ticket_event → maybe_deliver_ticket_event_push (claim por id).
    No crea scheduler. Idempotente: un solo evento por ticket.
    """
    from sqlalchemy import select

    from app.estate import repository as repo
    from app.estate.models import Ticket

    if not isinstance(ticket, Ticket):
        return None
    if (ticket.estado or "") == "Cerrado":
        return None
    if not ticket.sla_breached_at:
        return None
    tid = str(ticket.id or "").strip()
    org = str(ticket.organizacion_id or "").strip()
    if not tid or not org:
        return None

    existing = db.scalar(
        select(TicketEvent).where(
            TicketEvent.organizacion_id == org,
            TicketEvent.ticket_id == tid,
            TicketEvent.tipo == "sla_breach",
        )
    )
    if existing is not None:
        return None

    breached = ticket.sla_breached_at
    breached_iso = breached.isoformat() if breached else ""
    return repo.add_ticket_event(
        db,
        org,
        tid,
        tipo="sla_breach",
        titulo="Plazo de atención superado",
        detalle=f"sla_breached_at={breached_iso}" if breached_iso else "",
        nivel=str(ticket.nivel or ""),
        estado=str(ticket.estado or ""),
        actor="sistema",
        visible_cliente="Sí",
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

        # 2.6D/E: self-note del abonado es MATERIAL en timeline, no en push.
        if pe.event_type == "ticket.updated" and is_self_note_actor(
            str(getattr(ev, "actor", "") or "")
        ):
            logger.info(
                "ticket_proactive suppress ticket_event_id=%s ticket_id=%s "
                "reason=SELF_NOTE_NO_PUSH actor=%s",
                pe.source_event_id[:36],
                pe.ticket_id[:32],
                str(getattr(ev, "actor", "") or "")[:48],
            )
            return {
                **base,
                "decision": "SUPPRESS",
                "event_type": pe.event_type,
                "skipped": "SELF_NOTE_NO_PUSH",
                "suppression_reason": "SELF_NOTE_NO_PUSH",
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
