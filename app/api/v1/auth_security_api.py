"""Auth seguridad consola: change-password, logout, invites, audit login."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import UsuarioSesion, bump_token_version, logout_sesion, obtener_usuario_requerido, requiere_admin
from app.api.v1.deps import require_permiso
from app.api.v1.schemas import TenantContext
from app.estate import repository as repo
from app.estate.audit import log_audit
from app.estate.database import get_db
from app.estate.models import User, UserInvite
from app.estate.security import (
    generate_invite_token,
    hash_password,
    hash_token,
    password_policy_errors,
    valid_email,
    valid_password,
    verify_password,
)
from app.rbac import normalizar_rol_consola, roles_alta_permitidos
from app.services import auth_security as aseg
from app.services import email as email_svc

router = APIRouter(tags=["Auth seguridad"])


class ChangePasswordIn(BaseModel):
    current_password: str = Field(default="", max_length=200)
    new_password: str = Field(..., min_length=10, max_length=200)


class InviteCreateIn(BaseModel):
    email: str = Field(..., max_length=120)
    nombre: str = Field(default="", max_length=120)
    rol: str = Field(default="agente", max_length=32)


class InviteAcceptIn(BaseModel):
    token: str = Field(..., min_length=10, max_length=200)
    password: str = Field(..., min_length=10, max_length=200)
    nombre: str = Field(default="", max_length=120)


class ResetPasswordIn(BaseModel):
    new_password: str = Field(default="", max_length=200)
    must_change: bool = True
    via_email: bool = True  # True = link por email; False = clave temporal (legacy)


def _invite_link_payload(raw_token: str, email_sent: bool) -> dict:
    from app.config import es_produccion

    out: dict = {"email_sent": email_sent}
    # Si el mail no salió, el admin necesita el link para compartirlo.
    # En non-prod siempre devolvemos token para tests.
    if not email_sent or not es_produccion():
        out["token"] = raw_token
        out["invite_link"] = email_svc.invite_public_link(raw_token)
    return out


def _expire_pending_invites(db: Session, *, org_id: str, email: str, purpose: str) -> None:
    """Invalida invites pendientes del mismo email/purpose marcándolos aceptados (usados)."""
    now = datetime.now(UTC)
    rows = list(
        db.scalars(
            select(UserInvite).where(
                UserInvite.organizacion_id == org_id,
                UserInvite.email == email,
                UserInvite.purpose == purpose,
                UserInvite.accepted_at.is_(None),
            )
        ).all()
    )
    for inv in rows:
        inv.accepted_at = now
    if rows:
        db.flush()


@router.post("/auth/change-password")
def change_password(
    body: ChangePasswordIn,
    usuario: UsuarioSesion = Depends(obtener_usuario_requerido),
    db: Session = Depends(get_db),
):
    from app.auth import _crear_token
    from app.rbac import permisos_para_rol

    if usuario.user_id.startswith("mock:"):
        raise HTTPException(400, "Usuarios demo no pueden cambiar contraseña; usá un usuario de DB")
    user = db.get(User, usuario.user_id)
    if not user:
        # fallback por email
        found = repo.get_user_by_login(db, usuario.usuario)
        if not found:
            raise HTTPException(404, "Usuario no encontrado")
        user = found[0]

    must_change = (user.must_change_password or "").lower() in ("sí", "si", "yes", "true")
    if not must_change:
        if not verify_password(body.current_password, user.password):
            raise HTTPException(401, "Contraseña actual incorrecta")
    elif body.current_password and not verify_password(body.current_password, user.password):
        raise HTTPException(401, "Contraseña actual incorrecta")

    if not valid_password(body.new_password):
        raise HTTPException(
            400,
            "La nueva clave no cumple la política: " + ", ".join(password_policy_errors(body.new_password)),
        )
    if verify_password(body.new_password, user.password):
        raise HTTPException(400, "La nueva clave debe ser distinta a la actual")

    user.password = hash_password(body.new_password)
    user.must_change_password = "No"
    if not user.email_verified_at:
        user.email_verified_at = datetime.now(UTC)
    user.token_version = int(getattr(user, "token_version", 0) or 0) + 1
    db.commit()
    db.refresh(user)

    # Invalidar JWT anterior (jti) si existe
    logout_sesion(db, usuario)

    org = repo.get_org_by_id(db, user.organizacion_id)
    org_slug = org.slug if org else usuario.org_slug
    rol = normalizar_rol_consola(user.rol, org_slug)
    cooperativa = None if org_slug == "imowi" else (org.nombre if org else usuario.cooperativa)
    token = _crear_token(
        {
            "usuario": user.email,
            "rol": rol,
            "cooperativa": cooperativa,
            "nombre": user.nombre,
            "org_slug": org_slug,
        },
        user_id=user.id,
        token_version=int(getattr(user, "token_version", 0) or 0),
        must_change=False,
    )
    log_audit(
        db,
        org_id=user.organizacion_id,
        actor=user.email,
        accion="auth.change_password",
        recurso=user.email,
        detalle="password updated",
    )
    return {
        "status": "ok",
        "must_change_password": False,
        "token": token,
        "rol": rol,
        "usuario": user.email,
        "cooperativa": cooperativa,
        "nombre": user.nombre,
        "org_slug": org_slug,
        "permisos": sorted(permisos_para_rol(rol)),
    }


@router.post("/auth/logout")
def auth_logout(
    usuario: UsuarioSesion = Depends(obtener_usuario_requerido),
    db: Session = Depends(get_db),
):
    logout_sesion(db, usuario)
    return {"status": "ok"}


@router.get("/auth/login-events")
def login_events(
    superficie: str = "console",
    limit: int = 100,
    _: UsuarioSesion = Depends(requiere_admin),
    db: Session = Depends(get_db),
):
    rows = aseg.list_login_events(db, superficie=superficie or None, limit=limit)
    return {
        "eventos": [
            {
                "id": r.id,
                "superficie": r.superficie,
                "actor": r.actor,
                "ip": r.ip,
                "ok": r.ok == "Sí",
                "reason": r.reason,
                "org_slug": r.org_slug,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }


@router.post("/auth/invites")
def create_invite(
    body: InviteCreateIn,
    request: Request,
    ctx: TenantContext = Depends(require_permiso("users.manage")),
    db: Session = Depends(get_db),
):
    email = body.email.strip().lower()
    if not valid_email(email):
        raise HTTPException(400, "Email inválido")
    allowed = roles_alta_permitidos(actor_rol=ctx.rol, org_slug=ctx.organizacion_slug)
    rol = normalizar_rol_consola(body.rol or "agente", ctx.organizacion_slug)
    if rol not in allowed and not ctx.puede("users.manage"):
        raise HTTPException(403, f"No podés invitar con rol '{rol}'")
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(400, "El email ya está registrado — usá reset por email si olvidó la clave")

    _expire_pending_invites(db, org_id=ctx.organizacion_id, email=email, purpose="invite")

    raw = generate_invite_token()
    invite = UserInvite(
        organizacion_id=ctx.organizacion_id,
        email=email,
        nombre=(body.nombre or "").strip(),
        rol=rol,
        purpose="invite",
        token_hash=hash_token(raw),
        invited_by=ctx.usuario_email,
        expires_at=datetime.now(UTC) + timedelta(hours=72),
    )
    db.add(invite)
    db.commit()

    org = repo.get_org_by_id(db, ctx.organizacion_id)
    sent = email_svc.send_invite_email(
        to=email,
        nombre=invite.nombre or email,
        org_nombre=org.nombre if org else ctx.organizacion_slug,
        token=raw,
        rol=rol,
    )
    log_audit(
        db,
        org_id=ctx.organizacion_id,
        actor=ctx.usuario_email,
        accion="auth.invite_create",
        recurso=email,
        detalle=f"rol={rol} sent={sent}",
    )
    out = {
        "status": "ok",
        "email": email,
        "rol": rol,
        "purpose": "invite",
        "expires_at": invite.expires_at.isoformat(),
        **_invite_link_payload(raw, sent),
    }
    return out


@router.get("/auth/invites")
def list_invites(
    ctx: TenantContext = Depends(require_permiso("users.manage")),
    db: Session = Depends(get_db),
):
    rows = list(
        db.scalars(
            select(UserInvite)
            .where(UserInvite.organizacion_id == ctx.organizacion_id)
            .order_by(UserInvite.created_at.desc())
            .limit(100)
        ).all()
    )
    return {
        "invites": [
            {
                "id": i.id,
                "email": i.email,
                "nombre": i.nombre,
                "rol": i.rol,
                "expires_at": i.expires_at.isoformat() if i.expires_at else None,
                "accepted_at": i.accepted_at.isoformat() if i.accepted_at else None,
                "invited_by": i.invited_by,
                "purpose": getattr(i, "purpose", None) or "invite",
                "pendiente": i.accepted_at is None,
            }
            for i in rows
        ]
    }


@router.get("/auth/invite/{token}")
def peek_invite(token: str, db: Session = Depends(get_db)):
    invite = db.scalar(select(UserInvite).where(UserInvite.token_hash == hash_token(token)))
    if not invite or invite.accepted_at:
        raise HTTPException(404, "Invitación inválida o ya utilizada")
    exp = invite.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=UTC)
    if exp < datetime.now(UTC):
        raise HTTPException(410, "Invitación expirada")
    org = repo.get_org_by_id(db, invite.organizacion_id)
    purpose = getattr(invite, "purpose", None) or "invite"
    return {
        "email": invite.email,
        "nombre": invite.nombre,
        "rol": invite.rol,
        "purpose": purpose,
        "org_slug": org.slug if org else "",
        "org_nombre": org.nombre if org else "",
        "expires_at": invite.expires_at.isoformat(),
    }


@router.post("/auth/invite/accept")
def accept_invite(body: InviteAcceptIn, db: Session = Depends(get_db)):
    invite = db.scalar(select(UserInvite).where(UserInvite.token_hash == hash_token(body.token)))
    if not invite or invite.accepted_at:
        raise HTTPException(404, "Invitación inválida o ya utilizada")
    exp = invite.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=UTC)
    if exp < datetime.now(UTC):
        raise HTTPException(410, "Invitación expirada")
    if not valid_password(body.password):
        raise HTTPException(
            400,
            "La clave no cumple la política: " + ", ".join(password_policy_errors(body.password)),
        )

    purpose = getattr(invite, "purpose", None) or "invite"
    org = repo.get_org_by_id(db, invite.organizacion_id)

    if purpose == "password_reset":
        user = db.scalar(select(User).where(User.email == invite.email))
        if not user or user.organizacion_id != invite.organizacion_id:
            raise HTTPException(404, "Usuario no encontrado para este reset")
        user.password = hash_password(body.password)
        user.must_change_password = "No"
        user.token_version = int(getattr(user, "token_version", 0) or 0) + 1
        if not user.email_verified_at:
            user.email_verified_at = datetime.now(UTC)
        if body.nombre.strip():
            user.nombre = body.nombre.strip()
        invite.accepted_at = datetime.now(UTC)
        db.commit()
        db.refresh(user)
        log_audit(
            db,
            org_id=invite.organizacion_id,
            actor=invite.email,
            accion="auth.password_reset_accept",
            recurso=invite.email,
            detalle="via_email_link",
        )
        return {
            "status": "ok",
            "email": user.email,
            "nombre": user.nombre,
            "rol": user.rol,
            "purpose": purpose,
            "org_slug": org.slug if org else "",
        }

    if db.scalar(select(User).where(User.email == invite.email)):
        raise HTTPException(400, "El email ya está registrado")

    nombre = (body.nombre or invite.nombre or invite.email.split("@")[0]).strip()
    user = User(
        organizacion_id=invite.organizacion_id,
        email=invite.email,
        nombre=nombre,
        password=hash_password(body.password),
        rol=invite.rol,
        must_change_password="No",
        activo="Sí",
        email_verified_at=datetime.now(UTC),
        token_version=0,
    )
    db.add(user)
    invite.accepted_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)
    log_audit(
        db,
        org_id=invite.organizacion_id,
        actor=invite.email,
        accion="auth.invite_accept",
        recurso=invite.email,
        detalle=f"rol={invite.rol}",
    )
    return {
        "status": "ok",
        "email": user.email,
        "nombre": user.nombre,
        "rol": user.rol,
        "purpose": purpose,
        "org_slug": org.slug if org else "",
    }


@router.post("/org/users/{user_id}/reset-password")
def reset_user_password(
    user_id: str,
    body: ResetPasswordIn,
    ctx: TenantContext = Depends(require_permiso("users.manage")),
    db: Session = Depends(get_db),
):
    user = repo.get_user_by_id(db, ctx.organizacion_id, user_id)
    if not user:
        raise HTTPException(404, "Usuario no encontrado")

    # Flujo preferido: link por email para que el usuario defina su clave
    if body.via_email and not body.new_password:
        _expire_pending_invites(
            db, org_id=ctx.organizacion_id, email=user.email, purpose="password_reset"
        )
        raw = generate_invite_token()
        invite = UserInvite(
            organizacion_id=ctx.organizacion_id,
            email=user.email,
            nombre=user.nombre or "",
            rol=user.rol,
            purpose="password_reset",
            token_hash=hash_token(raw),
            invited_by=ctx.usuario_email,
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        db.add(invite)
        # Invalidar sesiones actuales hasta que complete el reset
        user.token_version = int(getattr(user, "token_version", 0) or 0) + 1
        db.commit()

        org = repo.get_org_by_id(db, ctx.organizacion_id)
        sent = email_svc.send_password_reset_email(
            to=user.email,
            nombre=user.nombre or user.email,
            org_nombre=org.nombre if org else ctx.organizacion_slug,
            token=raw,
        )
        log_audit(
            db,
            org_id=ctx.organizacion_id,
            actor=ctx.usuario_email,
            accion="auth.reset_password_email",
            recurso=user.email,
            detalle=f"sent={sent}",
        )
        return {
            "status": "ok",
            "email": user.email,
            "must_change_password": True,
            "via_email": True,
            **_invite_link_payload(raw, sent),
        }

    import secrets
    import string

    if body.new_password:
        if not valid_password(body.new_password):
            raise HTTPException(
                400,
                "La clave no cumple la política: " + ", ".join(password_policy_errors(body.new_password)),
            )
        new_pw = body.new_password
    else:
        alphabet = string.ascii_letters + string.digits
        new_pw = "Tmp" + "".join(secrets.choice(alphabet) for _ in range(10)) + "1a"
    user.password = hash_password(new_pw)
    user.must_change_password = "Sí" if body.must_change else "No"
    user.token_version = int(getattr(user, "token_version", 0) or 0) + 1
    db.commit()
    log_audit(
        db,
        org_id=ctx.organizacion_id,
        actor=ctx.usuario_email,
        accion="auth.reset_password",
        recurso=user.email,
        detalle="must_change=" + str(body.must_change),
    )
    return {
        "status": "ok",
        "email": user.email,
        "must_change_password": body.must_change,
        "via_email": False,
        "temporary_password": new_pw,
    }
