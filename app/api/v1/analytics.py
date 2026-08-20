from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.v1.deps import get_tenant_context
from app.api.v1.schemas import TenantContext
from app.estate import repository as repo
from app.estate.database import get_db
from app.estate.executive_analytics import executive_analytics
from app.estate.ops_analytics import build_ops_analytics
from app.services.encuesta_satisfaccion import build_csat_analytics

router = APIRouter(tags=["Analytics"])


def _alcance_global(ctx: TenantContext) -> bool:
    """Admin plataforma en tenant imowi: agrega todas las cooperativas."""
    return bool(ctx.es_admin_imowi or ctx.puede("stats.global")) and ctx.organizacion_slug == "imowi"


def _flatten_for_csv(prefix: str, value: object, rows: list[dict[str, str]]) -> None:
    """Aplana métricas escalares/listas simples a filas metric,value."""
    if value is None:
        return
    if isinstance(value, (str, int, float, bool)):
        rows.append({"metric": prefix, "value": str(value)})
        return
    if isinstance(value, dict):
        for k, v in value.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, (dict, list)):
                _flatten_for_csv(key, v, rows)
            else:
                rows.append({"metric": key, "value": "" if v is None else str(v)})
        return
    if isinstance(value, list):
        if not value:
            rows.append({"metric": prefix, "value": ""})
            return
        if all(isinstance(x, dict) for x in value):
            for i, item in enumerate(value):
                _flatten_for_csv(f"{prefix}[{i}]", item, rows)
        else:
            rows.append({"metric": prefix, "value": "; ".join(str(x) for x in value)})
        return
    rows.append({"metric": prefix, "value": str(value)})


def _csv_response(rows: list[dict[str, str]], filename: str) -> StreamingResponse:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["metric", "value"])
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/analytics/export")
def export_analytics_csv(
    kind: str = Query(default="executive", pattern="^(executive|ops|tickets)$"),
    desde: str | None = None,
    hasta: str | None = None,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Export CSV de métricas. Requiere reports.export."""
    if not ctx.puede("reports.export"):
        raise HTTPException(403, "Sin permiso para exportar reportes")

    admin_global = _alcance_global(ctx)
    desde_dt = _parse_desde(desde)
    hasta_dt = _parse_hasta(hasta)
    rows: list[dict[str, str]] = [
        {"metric": "tenant", "value": ctx.organizacion_slug},
        {"metric": "kind", "value": kind},
        {"metric": "exported_at", "value": datetime.now(UTC).isoformat()},
    ]

    if kind == "executive":
        data = executive_analytics(db, admin_global=admin_global, org_id=ctx.organizacion_id)
        _flatten_for_csv("", data, rows)
    elif kind == "ops":
        data = build_ops_analytics(
            db,
            ctx.organizacion_id,
            desde=desde_dt,
            hasta=hasta_dt,
            admin_global=admin_global,
        )
        _flatten_for_csv("", data, rows)
    else:
        stats = repo.ticket_stats(
            db,
            ctx.organizacion_id,
            admin_global=admin_global,
            desde=desde_dt,
            hasta=hasta_dt,
        )
        # backlog de tickets como objetos: solo IDs/estados para CSV
        backlog = stats.pop("backlog", None) or []
        series = stats.pop("series", None)
        _flatten_for_csv("", stats, rows)
        if series:
            _flatten_for_csv("series", series, rows)
        for i, t in enumerate(backlog[:200]):
            if hasattr(t, "id"):
                rows.append(
                    {
                        "metric": f"backlog[{i}]",
                        "value": f"{t.id}|{getattr(t, 'estado', '')}|{getattr(t, 'estado_sla', '')}|{getattr(t, 'nivel', '')}",
                    }
                )
            elif isinstance(t, dict):
                rows.append(
                    {
                        "metric": f"backlog[{i}]",
                        "value": f"{t.get('id', '')}|{t.get('estado', '')}|{t.get('estado_sla', '')}|{t.get('nivel', '')}",
                    }
                )

    stamp = datetime.now(UTC).strftime("%Y%m%d")
    return _csv_response(rows, f"analytics-{kind}-{ctx.organizacion_slug}-{stamp}.csv")


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
    admin_global = _alcance_global(ctx)
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
    admin_global = _alcance_global(ctx)
    data = executive_analytics(db, admin_global=admin_global, org_id=ctx.organizacion_id)
    return {"tenant": ctx.organizacion_slug, "alcance": "global" if admin_global else "organizacion", **data}


@router.get("/analytics/agents")
def agents_performance(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    if not (ctx.puede("stats.agents") or ctx.puede("stats.global")):
        raise HTTPException(403, "Sin permiso para ver performance de agentes")
    admin_global = _alcance_global(ctx)
    data = repo.agent_performance(db, ctx.organizacion_id, admin_global=admin_global)
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
    admin_global = _alcance_global(ctx)
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
    admin_global = _alcance_global(ctx)

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
