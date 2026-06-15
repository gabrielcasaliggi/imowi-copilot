from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.deps import get_tenant_context
from app.api.v1.schemas import TenantContext
from app.estate.database import get_db
from app.jsc import connector as jsc
from app.estate import repository as repo

router = APIRouter(tags=["JSC"])


@router.get("/jsc/lineas")
def listar_lineas(
    q: str = "",
    limit: int = 20,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    admin = ctx.es_admin_imowi and ctx.organizacion_slug == "imowi"
    if q.strip():
        rows = repo.search_lineas(
            db, ctx.organizacion_id, q, limit=limit, admin_global=admin
        )
        lineas = [jsc.ficha_linea(r) for r in rows]
    else:
        lineas = jsc.listar_lineas_org(
            db, ctx.organizacion_id, limit=limit, admin_global=admin
        )
    return {
        "tenant": ctx.organizacion_slug,
        "fuente": "JSC (réplica demo)",
        "lineas": lineas,
    }


@router.get("/jsc/lineas/{msisdn}")
def obtener_linea(
    msisdn: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    admin = ctx.es_admin_imowi
    row = jsc.buscar_linea(db, ctx.organizacion_id, msisdn, admin_global=admin)
    ficha = jsc.ficha_linea(row)
    if not ficha:
        raise HTTPException(404, f"Línea {msisdn} no encontrada en catálogo JSC del tenant")
    return {"linea": ficha}
