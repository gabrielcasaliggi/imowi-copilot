from __future__ import annotations

from datetime import UTC, datetime, time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.deps import get_tenant_context
from app.api.v1.schemas import TenantContext
from app.estate import repository as repo
from app.estate.database import get_db
from app.estate.executive_analytics import executive_analytics

router = APIRouter(tags=["Analytics"])


@router.get("/analytics/tickets")
def ticket_analytics(
    desde: str | None = None,
    hasta: str | None = None,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    if not (
        ctx.puede("stats.global")
        or ctx.puede("stats.bot")
        or ctx.puede("stats.agents")
    ):
        raise HTTPException(403, "Sin permiso para ver estadísticas de tickets")
    admin_global = ctx.puede("stats.global") and ctx.organizacion_slug == "imowi"
    desde_dt = _parse_desde(desde)
    hasta_dt = _parse_hasta(hasta)
    stats = repo.ticket_stats(
        db,
        ctx.organizacion_id,
        admin_global=admin_global,
        desde=desde_dt,
        hasta=hasta_dt,
    )
    return {
        "tenant": ctx.organizacion_slug,
        "desde": desde_dt.isoformat() if desde_dt else None,
        "hasta": hasta_dt.isoformat() if hasta_dt else None,
        "alcance": "global" if admin_global else "organizacion",
        **stats,
    }


@router.get("/analytics/executive")
def executive_dashboard(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    if not (ctx.puede("stats.global") or ctx.puede("stats.bot")):
        raise HTTPException(403, "Sin permiso para analytics ejecutivo / performance del bot")
    admin_global = ctx.puede("stats.global") and ctx.organizacion_slug == "imowi"
    data = executive_analytics(db, admin_global=admin_global, org_id=ctx.organizacion_id)
    return {"tenant": ctx.organizacion_slug, "alcance": "global" if admin_global else "organizacion", **data}


@router.get("/analytics/agents")
def agents_performance(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    if not (ctx.puede("stats.agents") or ctx.puede("stats.global")):
        raise HTTPException(403, "Sin permiso para ver performance de agentes")
    data = repo.agent_performance(db, ctx.organizacion_id)
    return {"tenant": ctx.organizacion_slug, **data}


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
