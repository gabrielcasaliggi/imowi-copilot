"""Autenticación por JWT (stateless, apta para PaaS sin disco)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import AUTH_SECRET, AUTH_TOKEN_HOURS, MOCK_USERS, es_produccion
from app.estate import repository as repo
from app.estate.security import hash_password, is_hashed, verify_password
from app.models import LoginInput, LoginResponse
from app.rbac import normalizar_rol_consola, permisos_para_rol, puede as rbac_puede

_bearer = HTTPBearer(auto_error=False)
_ALGORITMO = "HS256"


def _secret_efectivo() -> str:
    if AUTH_SECRET:
        return AUTH_SECRET
    if es_produccion():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AUTH_SECRET no configurado en el servidor (Render → Environment).",
        )
    return "dev-secret-no-usar-en-produccion"


@dataclass
class UsuarioSesion:
    usuario: str
    rol: str
    cooperativa: str | None
    nombre: str
    org_slug: str = "imowi"


def _crear_token(payload: dict) -> str:
    exp = datetime.now(UTC) + timedelta(hours=AUTH_TOKEN_HOURS)
    data = {**payload, "exp": exp}
    return jwt.encode(data, _secret_efectivo(), algorithm=_ALGORITMO)


def _decodificar_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, _secret_efectivo(), algorithms=[_ALGORITMO])
    except jwt.PyJWTError:
        return None


def cargar_tokens_desde_disco() -> int:
    """Compat startup: JWT no requiere restaurar sesiones."""
    return 0


def login_usuario(data: LoginInput) -> LoginResponse:
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
        }
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


def login_usuario_db(data: LoginInput, db: Session) -> LoginResponse:
    """Valida primero aliases demo y luego usuarios del Data Estate."""
    try:
        return login_usuario(data)
    except HTTPException:
        pass

    found = repo.get_user_by_login(db, data.usuario)
    if not found:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
        )
    user, org = found
    if not repo.user_is_active(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario desactivado. Contactá al administrador o supervisor.",
        )
    if not verify_password(data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
        )
    if not is_hashed(user.password):
        user.password = hash_password(data.password)
        db.commit()
    user.last_login_at = datetime.now(UTC)
    # Persistí rol normalizado si venía legacy
    rol_token = normalizar_rol_consola(user.rol, org.slug)
    if user.rol != rol_token:
        user.rol = rol_token
    db.commit()

    cooperativa = None if org.slug == "imowi" else org.nombre
    token = _crear_token(
        {
            "usuario": user.email,
            "rol": rol_token,
            "cooperativa": cooperativa,
            "nombre": user.nombre,
            "org_slug": org.slug,
        }
    )
    return LoginResponse(
        token=token,
        rol=rol_token,
        usuario=user.email,
        cooperativa=cooperativa,
        nombre=user.nombre,
        org_slug=org.slug,
        must_change_password=(user.must_change_password or "").lower() in ("sí", "si", "yes", "true"),
        permisos=sorted(permisos_para_rol(rol_token)),
    )


def _resolver_sesion(token: str | None) -> UsuarioSesion | None:
    if not token:
        return None
    payload = _decodificar_token(token)
    if not payload:
        return None
    org_slug = payload.get("org_slug") or ""
    rol = normalizar_rol_consola(payload.get("rol", ""), org_slug)
    return UsuarioSesion(
        usuario=payload.get("usuario", ""),
        rol=rol,
        cooperativa=payload.get("cooperativa"),
        nombre=payload.get("nombre", ""),
        org_slug=org_slug or ("imowi" if rol == "admin" else "coop-batan"),
    )


def obtener_usuario_opcional(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> UsuarioSesion | None:
    if not credentials:
        return None
    return _resolver_sesion(credentials.credentials)


def obtener_usuario_requerido(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> UsuarioSesion:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token requerido",
            headers={"WWW-Authenticate": "Bearer"},
        )
    sesion = _resolver_sesion(credentials.credentials)
    if not sesion:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
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
