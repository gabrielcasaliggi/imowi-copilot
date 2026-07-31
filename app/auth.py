"""Autenticación consola por JWT (typ=console, aud separado del portal)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import (
    AUTH_SECRET,
    AUTH_TOKEN_HOURS,
    CONSOLE_JWT_AUD,
    MOCK_USERS,
    demo_users_disabled,
    es_produccion,
)
from app.estate import repository as repo
from app.estate.database import get_db
from app.estate.security import hash_password, is_hashed, verify_password
from app.models import LoginInput, LoginResponse
from app.rbac import normalizar_rol_consola, permisos_para_rol, puede as rbac_puede
from app.services import auth_security as aseg

_bearer = HTTPBearer(auto_error=False)
_ALGORITMO = "HS256"
_CONSOLE_TYP = "console"

# Rutas permitidas cuando must_change_password=true
_MUST_CHANGE_ALLOW_SUFFIXES = (
    "/api/login",
    "/api/logout",
    "/api/me",
    "/api/v1/auth/change-password",
    "/api/v1/auth/logout",
)


def _secret_efectivo() -> str:
    if AUTH_SECRET:
        return AUTH_SECRET
    if es_produccion():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AUTH_SECRET no configurado en el servidor.",
        )
    return "dev-secret-no-usar-en-produccion"


@dataclass
class UsuarioSesion:
    usuario: str
    rol: str
    cooperativa: str | None
    nombre: str
    org_slug: str = "imowi"
    user_id: str = ""
    token_version: int = 0
    must_change_password: bool = False
    jti: str = ""
    raw_token: str = field(default="", repr=False)


def _client_ip(request: Request | None) -> str:
    if request is None:
        return ""
    forwarded = request.headers.get("x-forwarded-for") or ""
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    if request.client:
        return (request.client.host or "")[:64]
    return ""


def _crear_token(
    payload: dict,
    *,
    user_id: str = "",
    token_version: int = 0,
    must_change: bool = False,
) -> str:
    exp = datetime.now(UTC) + timedelta(hours=AUTH_TOKEN_HOURS)
    jti = str(uuid.uuid4())
    data = {
        **payload,
        "typ": _CONSOLE_TYP,
        "aud": CONSOLE_JWT_AUD,
        "sub": user_id or payload.get("usuario", ""),
        "ver": int(token_version or 0),
        "mcp": bool(must_change),
        "jti": jti,
        "iat": datetime.now(UTC),
        "exp": exp,
    }
    return jwt.encode(data, _secret_efectivo(), algorithm=_ALGORITMO)


def _decodificar_token(token: str) -> dict | None:
    try:
        return jwt.decode(
            token,
            _secret_efectivo(),
            algorithms=[_ALGORITMO],
            audience=CONSOLE_JWT_AUD,
        )
    except jwt.PyJWTError:
        # Compat: tokens sin aud (pre-hardening) solo fuera de production
        if es_produccion():
            return None
        try:
            payload = jwt.decode(
                token,
                _secret_efectivo(),
                algorithms=[_ALGORITMO],
                options={"verify_aud": False},
            )
            if payload.get("typ") == "portal":
                return None
            return payload
        except jwt.PyJWTError:
            return None


def cargar_tokens_desde_disco() -> int:
    """Compat startup: JWT no requiere restaurar sesiones."""
    return 0


def login_usuario(data: LoginInput) -> LoginResponse:
    if demo_users_disabled() or not MOCK_USERS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
        )
    cred = MOCK_USERS.get(data.usuario)
    if not cred or cred["password"] != data.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
        )

    org_slug = cred.get("org_slug") or "coop-batan"
    rol = normalizar_rol_consola(cred["rol"], org_slug)
    if not org_slug:
        org_slug = "imowi" if rol == "admin" else "coop-batan"
    token = _crear_token(
        {
            "usuario": data.usuario,
            "rol": rol,
            "cooperativa": cred["cooperativa"],
            "nombre": cred["nombre"],
            "org_slug": org_slug,
        },
        user_id=f"mock:{data.usuario}",
        token_version=0,
        must_change=False,
    )
    return LoginResponse(
        token=token,
        rol=rol,
        usuario=data.usuario,
        cooperativa=cred["cooperativa"],
        nombre=cred["nombre"],
        org_slug=org_slug,
        permisos=sorted(permisos_para_rol(rol)),
    )


def login_usuario_db(
    data: LoginInput,
    db: Session,
    *,
    request: Request | None = None,
) -> LoginResponse:
    """Valida aliases demo (si habilitados) y luego usuarios del Data Estate."""
    ip = _client_ip(request)
    actor = (data.usuario or "").strip().lower()

    if aseg.is_locked(db, superficie="console", actor=actor, ip=ip):
        aseg.record_login_event(
            db, superficie="console", actor=actor, ip=ip, ok=False, reason="locked"
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos fallidos. Probá más tarde.",
        )

    if not demo_users_disabled() and MOCK_USERS:
        try:
            resp = login_usuario(data)
            aseg.clear_failures(db, superficie="console", actor=actor, ip=ip)
            aseg.record_login_event(
                db,
                superficie="console",
                actor=actor,
                ip=ip,
                ok=True,
                reason="mock_ok",
                org_slug=resp.org_slug,
            )
            return resp
        except HTTPException:
            pass

    found = repo.get_user_by_login(db, data.usuario)
    if not found:
        aseg.record_login_event(
            db, superficie="console", actor=actor, ip=ip, ok=False, reason="not_found"
        )
        aseg.register_failure(db, superficie="console", actor=actor, ip=ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
        )
    user, org = found
    if not repo.user_is_active(user):
        aseg.record_login_event(
            db,
            superficie="console",
            actor=actor,
            ip=ip,
            ok=False,
            reason="inactive",
            org_slug=org.slug,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario desactivado. Contactá al administrador o supervisor.",
        )
    if not verify_password(data.password, user.password):
        aseg.record_login_event(
            db,
            superficie="console",
            actor=actor,
            ip=ip,
            ok=False,
            reason="bad_password",
            org_slug=org.slug,
        )
        locked = aseg.register_failure(db, superficie="console", actor=actor, ip=ip)
        if locked:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Demasiados intentos fallidos. Probá más tarde.",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
        )
    if not is_hashed(user.password) and not es_produccion():
        user.password = hash_password(data.password, enforce_policy=False)
        db.commit()
    user.last_login_at = datetime.now(UTC)
    rol_token = normalizar_rol_consola(user.rol, org.slug)
    if user.rol != rol_token:
        user.rol = rol_token
    db.commit()

    must_change = (user.must_change_password or "").lower() in ("sí", "si", "yes", "true")
    cooperativa = None if org.slug == "imowi" else org.nombre
    ver = int(getattr(user, "token_version", 0) or 0)
    token = _crear_token(
        {
            "usuario": user.email,
            "rol": rol_token,
            "cooperativa": cooperativa,
            "nombre": user.nombre,
            "org_slug": org.slug,
        },
        user_id=user.id,
        token_version=ver,
        must_change=must_change,
    )
    aseg.clear_failures(db, superficie="console", actor=actor, ip=ip)
    aseg.record_login_event(
        db,
        superficie="console",
        actor=user.email,
        ip=ip,
        ok=True,
        reason="ok",
        org_slug=org.slug,
    )
    return LoginResponse(
        token=token,
        rol=rol_token,
        usuario=user.email,
        cooperativa=cooperativa,
        nombre=user.nombre,
        org_slug=org.slug,
        must_change_password=must_change,
        permisos=sorted(permisos_para_rol(rol_token)),
    )


def _resolver_sesion(token: str | None, db: Session | None = None) -> UsuarioSesion | None:
    if not token:
        return None
    payload = _decodificar_token(token)
    if not payload:
        return None
    typ = payload.get("typ")
    if typ == "portal":
        return None
    if typ and typ != _CONSOLE_TYP and es_produccion():
        return None
    # Deny-list jti
    jti = str(payload.get("jti") or "")
    if db is not None and jti and aseg.denylist_contains(db, jti):
        return None

    org_slug = payload.get("org_slug") or ""
    rol = normalizar_rol_consola(payload.get("rol", ""), org_slug)
    user_id = str(payload.get("sub") or "")
    ver = int(payload.get("ver") or 0)
    must_change = bool(payload.get("mcp"))

    # Validar token_version / activo contra DB cuando hay sub real
    if db is not None and user_id and not user_id.startswith("mock:"):
        from app.estate.models import User

        user = db.get(User, user_id)
        if user:
            if not repo.user_is_active(user):
                return None
            db_ver = int(getattr(user, "token_version", 0) or 0)
            if ver != db_ver:
                return None
            must_change = (user.must_change_password or "").lower() in ("sí", "si", "yes", "true")

    return UsuarioSesion(
        usuario=payload.get("usuario", ""),
        rol=rol,
        cooperativa=payload.get("cooperativa"),
        nombre=payload.get("nombre", ""),
        org_slug=org_slug or ("imowi" if rol == "admin" else "coop-batan"),
        user_id=user_id,
        token_version=ver,
        must_change_password=must_change,
        jti=jti,
        raw_token=token,
    )


def obtener_usuario_opcional(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> UsuarioSesion | None:
    if not credentials:
        return None
    return _resolver_sesion(credentials.credentials, db)


def obtener_usuario_requerido(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> UsuarioSesion:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token requerido",
            headers={"WWW-Authenticate": "Bearer"},
        )
    sesion = _resolver_sesion(credentials.credentials, db)
    if not sesion:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
        )
    if sesion.must_change_password:
        path = request.url.path.rstrip("/") or "/"
        allowed = any(path.endswith(s.rstrip("/")) or path == s for s in _MUST_CHANGE_ALLOW_SUFFIXES)
        # también permitir /api/v1/auth/change-password exacto
        if path.endswith("/auth/change-password") or path.endswith("/auth/logout"):
            allowed = True
        if path.endswith("/me") or path.endswith("/login"):
            allowed = True
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Debés cambiar tu contraseña antes de continuar",
            )
    return sesion


def requiere_admin(usuario: UsuarioSesion = Depends(obtener_usuario_requerido)) -> UsuarioSesion:
    if usuario.rol != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Se requiere rol admin")
    return usuario


def requiere_permiso(codigo: str):
    """Dependency factory: exige un permiso RBAC sobre la sesión JWT."""

    def _dep(usuario: UsuarioSesion = Depends(obtener_usuario_requerido)) -> UsuarioSesion:
        if not rbac_puede(usuario.rol, codigo):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Se requiere permiso '{codigo}'",
            )
        return usuario

    return _dep


def bump_token_version(db: Session, user_id: str) -> None:
    from app.estate.models import User

    user = db.get(User, user_id)
    if not user:
        return
    user.token_version = int(getattr(user, "token_version", 0) or 0) + 1
    db.commit()


def logout_sesion(db: Session, sesion: UsuarioSesion) -> None:
    if not sesion.jti:
        return
    payload = _decodificar_token(sesion.raw_token) if sesion.raw_token else None
    exp = datetime.now(UTC) + timedelta(hours=AUTH_TOKEN_HOURS)
    if payload and payload.get("exp"):
        try:
            exp = datetime.fromtimestamp(int(payload["exp"]), tz=UTC)
        except (TypeError, ValueError, OSError):
            pass
    aseg.denylist_add(db, sesion.jti, exp)
