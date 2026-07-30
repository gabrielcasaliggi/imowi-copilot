"""Contexto multitenant — JWT + permisos RBAC."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.schemas import TenantContext
from app.auth import UsuarioSesion, obtener_usuario_requerido
from app.estate import repository as repo
from app.estate.database import get_db
from app.rbac import normalizar_rol_consola, permisos_para_rol


def get_tenant_context(
    usuario: UsuarioSesion = Depends(obtener_usuario_requerido),
    x_tenant_slug: str | None = Header(default=None, alias="X-Tenant-Slug"),
    db: Session = Depends(get_db),
) -> TenantContext:
    rol = normalizar_rol_consola(usuario.rol, usuario.org_slug)
    slug = usuario.org_slug
    if rol == "admin" and x_tenant_slug:
        slug = x_tenant_slug

    org = repo.get_org_by_slug(db, slug)
    if not org:
        raise HTTPException(404, f"Organización '{slug}' no encontrada")

    perms = sorted(permisos_para_rol(rol))
    return TenantContext(
        organizacion_id=org.id,
        organizacion_slug=org.slug,
        organizacion_nombre=org.nombre,
        brand_color=org.brand_color,
        logo_label=org.logo_label,
        usuario_email=f"{usuario.usuario}@ops-hub.demo" if "@" not in usuario.usuario else usuario.usuario,
        usuario_nombre=usuario.nombre,
        rol=rol,
        es_admin_imowi=rol == "admin",
        cooperativa_legacy=usuario.cooperativa,
        permisos=perms,
    )


def require_permiso(codigo: str):
    """Dependency factory sobre TenantContext."""

    def _dep(ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
        if not ctx.puede(codigo):
            raise HTTPException(403, f"Se requiere permiso '{codigo}'")
        return ctx

    return _dep


def require_kb_admin(ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
    if not ctx.puede("kb.publish") and not ctx.es_admin_imowi:
        raise HTTPException(403, "Se requiere permiso de administración KB")
    return ctx


def require_kb_proposer(ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
    if not ctx.puede("kb.propose"):
        raise HTTPException(403, "Se requiere permiso para proponer a KB")
    return ctx


def require_kb_reviewer(ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
    if not ctx.puede("kb.publish"):
        raise HTTPException(403, "Se requiere permiso de revisión KB")
    return ctx


def require_telemetry(ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
    if not ctx.es_admin_imowi and not ctx.puede("tickets.view"):
        raise HTTPException(403, "Telemetría no disponible para este rol")
    return ctx
