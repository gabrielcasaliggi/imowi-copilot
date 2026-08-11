"""API de incidentes masivos por NAS."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v1.deps import require_permiso
from app.api.v1.schemas import TenantContext
from app.estate import repository as repo
from app.estate.database import get_db
from app.services import outages as outage_svc

router = APIRouter(tags=["Outages"])


class OutageCreate(BaseModel):
    nas_shortname: str = Field(min_length=1, max_length=120)
    nas_ip: str = ""
    alcance: str = "total"  # total|parcial
    tipo: str = "DOWN"
    comentario: str = Field(min_length=1, max_length=4000)
    eta_minutos: int = Field(default=45, ge=1, le=24 * 60)
    usar_ia: bool = True


class OutageUpdate(BaseModel):
    alcance: str | None = None
    tipo: str | None = None
    comentario: str | None = None
    eta_minutos: int | None = Field(default=None, ge=1, le=24 * 60)
    usar_ia: bool = True


@router.get("/nas")
def list_nas(
    ctx: TenantContext = Depends(require_permiso("outages.manage")),
    db: Session = Depends(get_db),
    force: bool = Query(default=False),
):
    try:
        items = outage_svc.listar_nas_radius(db, force=force)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"No se pudo obtener NAS desde Radius: {exc}") from exc
    return {"tenant": ctx.organizacion_slug, "count": len(items), "data": items}


@router.get("/nas/{shortname}/health")
def nas_health(
    shortname: str,
    ctx: TenantContext = Depends(require_permiso("outages.manage")),
    db: Session = Depends(get_db),
):
    _ = ctx
    try:
        status = outage_svc.health_nas(db, shortname)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"No se pudo consultar NAS: {exc}") from exc
    return status


@router.get("/outages")
def list_outages(
    ctx: TenantContext = Depends(require_permiso("outages.manage")),
    db: Session = Depends(get_db),
    estado: str | None = Query(default="activo"),
):
    estado_q = None if estado in (None, "", "todos", "all") else estado
    items = repo.list_network_outages(db, ctx.organizacion_id, estado=estado_q)
    return {
        "tenant": ctx.organizacion_slug,
        "count": len(items),
        "data": [outage_svc.outage_to_dict(o) for o in items],
    }


@router.post("/outages")
def create_outage(
    body: OutageCreate,
    ctx: TenantContext = Depends(require_permiso("outages.manage")),
    db: Session = Depends(get_db),
):
    shortname = body.nas_shortname.strip()
    existente = outage_svc.outage_activo_para_nas(db, ctx.organizacion_id, shortname)
    if existente:
        raise HTTPException(
            409,
            f"Ya hay un incidente activo para NAS '{shortname}' (id={existente.id})",
        )

    nas_ip = (body.nas_ip or "").strip()
    reachable_flag = ""
    try:
        health = outage_svc.health_nas(db, shortname)
        reachable_flag = "Sí" if health.get("reachable") else "No"
        if not nas_ip:
            # Completar IP desde inventario si falta
            try:
                for n in outage_svc.listar_nas_radius(db):
                    if outage_svc.normalizar_nas_key(n.get("shortname", "")) == outage_svc.normalizar_nas_key(
                        shortname
                    ):
                        nas_ip = str(n.get("nasname") or n.get("ip") or "")
                        break
            except Exception:
                pass
        alcance = (body.alcance or "").strip().lower()
        if alcance not in ("total", "parcial"):
            alcance = str(health.get("alcance_sugerido") or "total")
    except Exception:
        alcance = (body.alcance or "total").strip().lower() or "total"

    if alcance not in ("total", "parcial"):
        alcance = "total"

    mensaje = outage_svc.generar_mensaje_cliente(
        alcance=alcance,
        comentario=body.comentario,
        eta_minutos=body.eta_minutos,
        nas_shortname=shortname,
        usar_ia=body.usar_ia,
    )
    o = repo.create_network_outage(
        db,
        ctx.organizacion_id,
        nas_shortname=shortname,
        nas_ip=nas_ip,
        alcance=alcance,
        tipo=body.tipo,
        comentario=body.comentario,
        mensaje_cliente=mensaje,
        eta_minutos=body.eta_minutos,
        nas_reachable_at_declare=reachable_flag,
        created_by=ctx.usuario_email or ctx.usuario_nombre,
    )
    return {"status": "creado", "outage": outage_svc.outage_to_dict(o)}


@router.patch("/outages/{outage_id}")
def update_outage(
    outage_id: str,
    body: OutageUpdate,
    ctx: TenantContext = Depends(require_permiso("outages.manage")),
    db: Session = Depends(get_db),
):
    o = repo.get_network_outage(db, ctx.organizacion_id, outage_id)
    if not o:
        raise HTTPException(404, "Incidente no encontrado")
    if o.estado != "activo":
        raise HTTPException(400, "Solo se pueden editar incidentes activos")

    alcance = body.alcance if body.alcance is not None else o.alcance
    comentario = body.comentario if body.comentario is not None else o.comentario
    eta = body.eta_minutos if body.eta_minutos is not None else o.eta_minutos
    regenerar = body.comentario is not None or body.alcance is not None or body.eta_minutos is not None
    mensaje = o.mensaje_cliente
    if regenerar:
        mensaje = outage_svc.generar_mensaje_cliente(
            alcance=alcance or "total",
            comentario=comentario or "",
            eta_minutos=eta or 45,
            nas_shortname=o.nas_shortname,
            usar_ia=body.usar_ia,
        )
    o = repo.update_network_outage(
        db,
        o,
        alcance=body.alcance,
        tipo=body.tipo,
        comentario=body.comentario,
        mensaje_cliente=mensaje if regenerar else None,
        eta_minutos=body.eta_minutos,
    )
    return {"status": "actualizado", "outage": outage_svc.outage_to_dict(o)}


@router.patch("/outages/{outage_id}/resolve")
def resolve_outage(
    outage_id: str,
    ctx: TenantContext = Depends(require_permiso("outages.manage")),
    db: Session = Depends(get_db),
):
    o = repo.get_network_outage(db, ctx.organizacion_id, outage_id)
    if not o:
        raise HTTPException(404, "Incidente no encontrado")
    if o.estado == "resuelto":
        return {"status": "ya_resuelto", "outage": outage_svc.outage_to_dict(o)}
    o = repo.resolve_network_outage(db, o)
    return {"status": "resuelto", "outage": outage_svc.outage_to_dict(o)}
