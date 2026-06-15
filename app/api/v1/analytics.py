from __future__ import annotations

from datetime import UTC, datetime, time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.deps import get_tenant_context
from app.api.v1.schemas import TenantContext
from app.estate import repository as repo
from app.estate.database import get_db

router = APIRouter(tags=["Analytics"])


@router.get("/analytics/tickets")
def ticket_analytics(
    desde: str | None = None,
    hasta: str | None = None,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    if not ctx.es_admin_imowi:
        raise HTTPException(403, "Las estadísticas globales son exclusivas del administrador NOC")
    desde_dt = _parse_desde(desde)
    hasta_dt = _parse_hasta(hasta)
    stats = repo.ticket_stats(
        db,
        ctx.organizacion_id,
        admin_global=ctx.es_admin_imowi and ctx.organizacion_slug == "imowi",
        desde=desde_dt,
        hasta=hasta_dt,
    )
    return {
        "tenant": ctx.organizacion_slug,
        "desde": desde_dt.isoformat() if desde_dt else None,
        "hasta": hasta_dt.isoformat() if hasta_dt else None,
        **stats,
    }


def _parse_desde(value: str | None) -> datetime | None:
    if not value:
        return None
    d = datetime.fromisoformat(value).date()
    return datetime.combine(d, time.min, tzinfo=UTC)


def _parse_hasta(value: str | None) -> datetime | None:
    if not value:
        return None
    d = datetime.fromisoformat(value).date()
    return datetime.combine(d, time.max, tzinfo=UTC)
