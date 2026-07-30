"""Catálogo RBAC y gestión de usuarios por org (admin / supervisor)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.deps import get_tenant_context, require_permiso
from app.api.v1.schemas import AvailabilityUpdate, TenantContext, UserCreate, UserUpdate
from app.auth import UsuarioSesion, obtener_usuario_requerido, requiere_admin
from app.estate import repository as repo
from app.estate.audit import log_audit
from app.estate.database import get_db
from app.estate.security import valid_email, valid_password
from app.rbac import (
    catalogo_permisos,
    catalogo_roles,
    normalizar_rol_consola,
    permisos_para_rol,
    roles_alta_permitidos,
)

router = APIRouter(tags=["RBAC"])


@router.get("/rbac/roles")
def list_roles(_: UsuarioSesion = Depends(obtener_usuario_requerido)):
    return {"roles": catalogo_roles()}


@router.get("/rbac/permissions")
def list_permissions(_: UsuarioSesion = Depends(requiere_admin)):
    return {"permisos": catalogo_permisos(), "matriz": catalogo_roles()}


@router.get("/rbac/me")
def my_rbac(usuario: UsuarioSesion = Depends(obtener_usuario_requerido)):
    rol = normalizar_rol_consola(usuario.rol, usuario.org_slug)
    return {
        "rol": rol,
        "org_slug": usuario.org_slug,
        "permisos": sorted(permisos_para_rol(rol)),
    }


@router.patch("/me/availability")
def update_my_availability(
    body: AvailabilityUpdate,
    ctx: TenantContext = Depends(require_permiso("agent.availability")),
    db: Session = Depends(get_db),
):
    allowed = {"disponible", "ocupado", "ausente"}
    valor = (body.disponibilidad or "").strip().lower()
    if valor not in allowed:
        raise HTTPException(400, f"disponibilidad debe ser una de: {', '.join(sorted(allowed))}")
    user = repo.set_user_availability(db, ctx.organizacion_id, ctx.usuario_email, valor)
    if not user:
        # Mock JWT users may not exist in DB — accept as session-only ack
        return {"status": "ok", "disponibilidad": valor, "persistido": False}
    return {"status": "ok", "disponibilidad": user.disponibilidad, "persistido": True, "usuario": repo.user_to_dict(user)}


@router.get("/org/users")
def list_org_users(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    if not (ctx.puede("users.manage") or ctx.puede("users.manage_agents") or ctx.puede("stats.agents")):
        raise HTTPException(403, "Sin permiso para listar usuarios de la organización")
    users = repo.list_users_for_org(db, ctx.organizacion_id)
    if ctx.puede("users.manage"):
        out = users
    elif ctx.puede("users.manage_agents") or ctx.puede("stats.agents"):
        out = [u for u in users if normalizar_rol_consola(u.rol) == "agente"]
    else:
        out = []
    return {"slug": ctx.organizacion_slug, "usuarios": [repo.user_to_dict(u) for u in out]}


@router.post("/org/users")
def create_org_agent(
    body: UserCreate,
    ctx: TenantContext = Depends(require_permiso("users.manage_agents")),
    db: Session = Depends(get_db),
):
    """Supervisor (o admin con el permiso) crea agentes en su cooperativa."""
    allowed = roles_alta_permitidos(actor_rol=ctx.rol, org_slug=ctx.organizacion_slug)
    rol_destino = normalizar_rol_consola(body.rol or "agente", ctx.organizacion_slug)
    if "agente" not in allowed and not ctx.puede("users.manage"):
        raise HTTPException(403, "No podés crear usuarios en esta organización")
    if not ctx.puede("users.manage") and rol_destino != "agente":
        raise HTTPException(403, "Solo podés crear usuarios con rol agente")
    if not body.email.strip() or not body.nombre.strip():
        raise HTTPException(400, "Email y nombre son obligatorios")
    if not valid_email(body.email.strip()):
        raise HTTPException(400, "Email inválido")
    pwd = body.password or "cliente"
    if not valid_password(pwd):
        raise HTTPException(400, "La clave debe tener al menos 6 caracteres")
    try:
        user = repo.create_user_for_org(
            db,
            ctx.organizacion_id,
            email=body.email.strip(),
            nombre=body.nombre.strip(),
            password=pwd,
            rol="agente" if not ctx.puede("users.manage") else rol_destino,
            telefono=body.telefono,
            linea_principal=body.linea_principal,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    log_audit(
        db,
        org_id=ctx.organizacion_id,
        actor=ctx.usuario_email,
        accion="usuario_alta",
        recurso=user.email,
        detalle=f"Usuario {user.nombre} ({user.rol}) vía org API",
    )
    return {"status": "ok", "usuario": repo.user_to_dict(user)}


@router.patch("/org/users/{user_id}")
def update_org_user(
    user_id: str,
    body: UserUpdate,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    if not (ctx.puede("users.manage") or ctx.puede("users.manage_agents")):
        raise HTTPException(403, "Sin permiso para editar usuarios")

    existing = repo.get_user_by_id(db, ctx.organizacion_id, user_id)
    if not existing:
        raise HTTPException(404, "Usuario no encontrado")

    if not ctx.puede("users.manage"):
        # Supervisor: solo agentes; solo activo (desactivar) y datos básicos, sin cambiar a otros roles
        if normalizar_rol_consola(existing.rol) != "agente":
            raise HTTPException(403, "Solo podés gestionar agentes de tu cooperativa")
        if body.rol is not None and normalizar_rol_consola(body.rol) != "agente":
            raise HTTPException(403, "No podés cambiar el rol fuera de agente")
        allowed_roles = frozenset({"agente"})
    else:
        allowed_roles = roles_alta_permitidos(actor_rol=ctx.rol, org_slug=ctx.organizacion_slug)

    try:
        user = repo.update_user_for_org(
            db,
            ctx.organizacion_id,
            user_id,
            nombre=body.nombre,
            rol=body.rol,
            telefono=body.telefono,
            linea_principal=body.linea_principal,
            activo=body.activo,
            password=body.password,
            allowed_roles=allowed_roles if body.rol is not None else None,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not user:
        raise HTTPException(404, "Usuario no encontrado")
    log_audit(
        db,
        org_id=ctx.organizacion_id,
        actor=ctx.usuario_email,
        accion="usuario_actualizacion",
        recurso=user.email,
        detalle=f"activo={repo.user_is_active(user)} rol={user.rol}",
    )
    return {"status": "ok", "usuario": repo.user_to_dict(user)}
