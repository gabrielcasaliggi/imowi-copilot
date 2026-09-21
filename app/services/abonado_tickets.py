"""Reader factual de tickets visibles por abonado (anti-IDOR).

Misma regla de ownership que el portal:
- conversaciones del abonado con ticket_id;
- y/o Ticket.linea coincidente con claves de identidad del abonado.

No inventa asociación. No incluye eventos internos ni datos de operadores.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.estate import canal_repo as crepo
from app.estate.models import Abonado, ConversacionCanal, Ticket


def claves_identidad_ticket(db: Session, org_id: str, abo: Abonado) -> set[str]:
    """Teléfonos / líneas normalizadas asociadas al abonado (canal + padrón)."""
    keys: set[str] = set()
    for raw in (abo.linea_msisdn, abo.telefono_e164):
        s = (raw or "").strip()
        if s:
            keys.add(s)
        n = crepo.normalizar_telefono(s)
        if n:
            keys.add(n)
    for c in db.scalars(
        select(ConversacionCanal).where(
            ConversacionCanal.organizacion_id == org_id,
            ConversacionCanal.abonado_id == abo.id,
        )
    ).all():
        s = (c.telefono or "").strip()
        if s:
            keys.add(s)
        n = crepo.normalizar_telefono(s)
        if n:
            keys.add(n)
    return {k for k in keys if k}


def conv_ids_por_ticket(db: Session, org_id: str, abo_id: str) -> dict[str, str]:
    """ticket_id → conversacion_id (la más reciente por updated_at)."""
    out: dict[str, str] = {}
    rows = db.scalars(
        select(ConversacionCanal)
        .where(
            ConversacionCanal.organizacion_id == org_id,
            ConversacionCanal.abonado_id == abo_id,
            ConversacionCanal.ticket_id != "",
        )
        .order_by(ConversacionCanal.updated_at.desc())
    ).all()
    for c in rows:
        tid = (c.ticket_id or "").strip()
        if tid and tid not in out:
            out[tid] = c.id
    return out


def list_tickets_visibles_abonado(
    db: Session,
    org_id: str,
    abo: Abonado,
) -> list[tuple[Ticket, str]]:
    """Tickets del abonado vía conversación.ticket_id y/o coincidencia de línea."""
    conv_map = conv_ids_por_ticket(db, org_id, abo.id)
    ids = set(conv_map.keys())
    keys = claves_identidad_ticket(db, org_id, abo)

    tickets: dict[str, Ticket] = {}
    if ids:
        for t in db.scalars(
            select(Ticket).where(Ticket.id.in_(ids), Ticket.organizacion_id == org_id)
        ).all():
            tickets[t.id] = t

    if keys:
        for t in db.scalars(
            select(Ticket).where(
                Ticket.organizacion_id == org_id,
                Ticket.linea.in_(list(keys)),
            )
        ).all():
            tickets[t.id] = t

    ordered = sorted(
        tickets.values(),
        key=lambda t: t.updated_at or t.created_at or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    return [(t, conv_map.get(t.id, "")) for t in ordered]


def ticket_pertenece_abonado(
    db: Session,
    org_id: str,
    abo: Abonado,
    ticket: Ticket,
) -> bool:
    if ticket.organizacion_id != org_id:
        return False
    return any(t.id == ticket.id for t, _ in list_tickets_visibles_abonado(db, org_id, abo))


def ticket_fact_item(ticket: Ticket, *, conversation_id: str = "") -> dict[str, Any]:
    """Proyección factual mínima para N1 (sin eventos ni datos internos)."""
    return {
        "id": ticket.id,
        "state": ticket.estado or "",
        "category": ticket.categoria or "",
        "origin": ticket.origen or "",
        "created_at": ticket.created_at.isoformat() if ticket.created_at else "",
        "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else "",
        "conversation_id": conversation_id or "",
    }


def load_ticket_facts(
    abonado: Any | None,
    *,
    db: Session | None,
    org_id: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    """Bloque facts.tickets para Eko Facts. Sin probes técnicos."""
    if abonado is None or db is None:
        return {
            "status": "omitted",
            "items": [],
            "reason_code": "missing_identity_or_db",
        }
    org = (org_id or str(getattr(abonado, "organizacion_id", "") or "")).strip()
    if not org:
        return {
            "status": "unavailable",
            "items": [],
            "reason_code": "missing_org",
        }
    try:
        rows = list_tickets_visibles_abonado(db, org, abonado)
        items = [
            ticket_fact_item(t, conversation_id=cid) for t, cid in rows[: max(0, limit)]
        ]
    except Exception:
        return {
            "status": "unavailable",
            "items": [],
            "reason_code": "source_unavailable",
        }
    if not items:
        return {"status": "empty", "items": [], "reason_code": None}
    return {"status": "ok", "items": items, "reason_code": None}


def portal_ticket_out_es(ticket: Ticket, *, conversacion_id: str = "") -> dict[str, Any]:
    """Shape HTTP portal (español) — compatible con /portal/tickets y Summary."""
    return {
        "id": ticket.id,
        "estado": ticket.estado or "",
        "categoria": ticket.categoria or "",
        "origen": ticket.origen or "",
        "created_at": ticket.created_at.isoformat() if ticket.created_at else "",
        "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else "",
        "conversacion_id": conversacion_id or "",
    }
