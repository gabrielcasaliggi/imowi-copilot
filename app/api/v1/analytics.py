from __future__ import annotations

from datetime import UTC, datetime, time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.deps import get_tenant_context
from app.api.v1.schemas import TenantContext
from app.estate import repository as repo
from app.estate.database import get_db
from app.estate.executive_analytics import executive_analytics
from app.estate.ops_analytics import build_ops_analytics
from app.services.encuesta_satisfaccion import build_csat_analytics

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


@router.get("/analytics/ops")
def ops_analytics(
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
        raise HTTPException(403, "Sin permiso para ver estadísticas operativas")
    admin_global = ctx.puede("stats.global") and ctx.organizacion_slug == "imowi"
    desde_dt = _parse_desde(desde)
    hasta_dt = _parse_hasta(hasta)
    data = build_ops_analytics(
        db,
        ctx.organizacion_id,
        desde=desde_dt,
        hasta=hasta_dt,
        admin_global=admin_global,
    )
    return {
        "tenant": ctx.organizacion_slug,
        **data,
        "agentes": data["agentes"]
        if (ctx.puede("stats.agents") or ctx.puede("stats.global"))
        else [],
    }


@router.get("/analytics/me")
def me_analytics(
    desde: str | None = None,
    hasta: str | None = None,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    if not (
        ctx.puede("stats.self")
        or ctx.puede("stats.agents")
        or ctx.puede("stats.global")
        or ctx.puede("stats.bot")
    ):
        raise HTTPException(403, "Sin permiso para ver tu actividad")
    desde_dt = _parse_desde(desde)
    hasta_dt = _parse_hasta(hasta)
    data = build_ops_analytics(
        db,
        ctx.organizacion_id,
        desde=desde_dt,
        hasta=hasta_dt,
        agent_filter=ctx.usuario_email or "",
    )
    me = data.get("me") or {}
    csat = build_csat_analytics(
        db,
        ctx.organizacion_id,
        desde=desde_dt,
        hasta=hasta_dt,
        agent_filter=ctx.usuario_email or "",
    )
    return {
        "tenant": ctx.organizacion_slug,
        "desde": data["desde"],
        "hasta": data["hasta"],
        "canal": {
            "claims_en_rango": me.get("claims", 0),
            "cierres_en_rango": me.get("cierres_canal", 0),
            "chats_activos": me.get("chats_activos", 0),
        },
        "tickets": {
            "abiertos": me.get("tickets_abiertos", 0),
            "cerrados": me.get("tickets_cerrados", 0),
            "con_resolucion": me.get("tickets_con_resolucion", 0),
            "pct_resolucion": me.get("pct_resolucion", 0.0),
        },
        "csat": csat.get("me") or csat.get("resumen"),
        "me": me,
    }


@router.get("/analytics/csat")
def csat_analytics(
    desde: str | None = None,
    hasta: str | None = None,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """CSAT: admin/supervisor ven bot + agentes; agente solo las propias."""
    puede_equipo = ctx.puede("stats.global") or ctx.puede("stats.agents") or ctx.puede("stats.bot")
    puede_self = ctx.puede("stats.self")
    if not (puede_equipo or puede_self):
        raise HTTPException(403, "Sin permiso para ver estadísticas de satisfacción")

    desde_dt = _parse_desde(desde)
    hasta_dt = _parse_hasta(hasta)
    admin_global = ctx.puede("stats.global") and ctx.organizacion_slug == "imowi"

    if puede_equipo:
        data = build_csat_analytics(
            db,
            ctx.organizacion_id,
            desde=desde_dt,
            hasta=hasta_dt,
            admin_global=admin_global,
        )
        # Ejecutivo (solo stats.bot): ocultar desglose por agente
        if ctx.puede("stats.bot") and not (
            ctx.puede("stats.agents") or ctx.puede("stats.global")
        ):
            data["agentes"] = []
            data["tecnicos"] = None
        return {"tenant": ctx.organizacion_slug, **data}

    data = build_csat_analytics(
        db,
        ctx.organizacion_id,
        desde=desde_dt,
        hasta=hasta_dt,
        agent_filter=ctx.usuario_email or "",
    )
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
