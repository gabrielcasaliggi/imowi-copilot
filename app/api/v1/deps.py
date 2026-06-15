"""Contexto multitenant — JWT + vista admin imowi."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.schemas import TenantContext
from app.auth import UsuarioSesion, obtener_usuario_requerido
from app.estate import repository as repo
from app.estate.database import get_db

_ROLES_ADMIN_KB = ("admin_sistema", "admin_org", "ingeniero_noc", "admin", "cooperativa")
_ROLES_TELEMETRY = ("admin_sistema", "admin_org", "ingeniero_noc", "admin")
_ROLES_COOP_KB = ("admin_sistema", "admin_org", "ingeniero_noc", "admin")


def _rol_plataforma(rol: str) -> str:
    if rol == "admin":
        return "admin_sistema"
    if rol == "cooperativa":
        return "ingeniero_noc"
    return rol


def get_tenant_context(
    usuario: UsuarioSesion = Depends(obtener_usuario_requerido),
    x_tenant_slug: str | None = Header(default=None, alias="X-Tenant-Slug"),
    db: Session = Depends(get_db),
) -> TenantContext:
    slug = usuario.org_slug
    if usuario.rol == "admin" and x_tenant_slug:
        slug = x_tenant_slug

    org = repo.get_org_by_slug(db, slug)
    if not org:
        raise HTTPException(404, f"Organización '{slug}' no encontrada")

    rol = _rol_plataforma(usuario.rol)
    if usuario.rol == "admin" and slug == "imowi":
        rol = "admin_sistema"

    return TenantContext(
        organizacion_id=org.id,
        organizacion_slug=org.slug,
        organizacion_nombre=org.nombre,
        brand_color=org.brand_color,
        logo_label=org.logo_label,
        usuario_email=f"{usuario.usuario}@imowi.demo",
        usuario_nombre=usuario.nombre,
        rol=rol,
        es_admin_imowi=usuario.rol == "admin",
        cooperativa_legacy=usuario.cooperativa,
    )


def require_kb_admin(ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
    if ctx.rol == "cliente":
        raise HTTPException(403, "Tu rol no puede editar la base de conocimiento")
    return ctx


def require_telemetry(ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
    if ctx.rol not in _ROLES_TELEMETRY and not ctx.es_admin_imowi:
        raise HTTPException(403, "Sin permiso para telemetría de red")
    return ctx
