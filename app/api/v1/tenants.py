from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_tenant_context
from app.api.v1.schemas import TenantContext
from app.auth import UsuarioSesion, obtener_usuario_requerido
from app.estate import repository as repo
from app.estate.database import get_db

router = APIRouter(tags=["Tenants"])


@router.get("/tenants")
def list_tenants(
    usuario: UsuarioSesion = Depends(obtener_usuario_requerido),
    db: Session = Depends(get_db),
):
    if usuario.rol == "admin":
        orgs = repo.list_organizations(db)
    else:
        org = repo.get_org_by_slug(db, usuario.org_slug)
        orgs = [org] if org else []
    return {
        "organizaciones": [
            {
                "slug": o.slug,
                "nombre": o.nombre,
                "brand_color": o.brand_color,
                "logo_label": o.logo_label,
            }
            for o in orgs
        ]
    }


@router.get("/session/context")
def session_context(ctx: TenantContext = Depends(get_tenant_context)):
    return ctx.model_dump()
