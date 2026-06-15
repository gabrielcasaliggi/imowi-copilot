"""Auditoría operativa — registro de acciones sensibles."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.estate.models import AuditEvent


def log_audit(
    db: Session,
    *,
    org_id: str,
    actor: str,
    accion: str,
    recurso: str,
    detalle: str = "",
) -> AuditEvent:
    ev = AuditEvent(
        organizacion_id=org_id,
        actor=actor or "sistema",
        accion=accion,
        recurso=recurso,
        detalle=(detalle or "")[:2000],
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def list_audit(
    db: Session,
    org_id: str | None = None,
    *,
    limit: int = 50,
    admin_global: bool = False,
) -> list[AuditEvent]:
    from sqlalchemy import select

    q = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
    if not admin_global and org_id:
        q = q.where(AuditEvent.organizacion_id == org_id)
    return list(db.scalars(q).all())
