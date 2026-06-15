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
from app.models import LoginInput, LoginResponse

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

    org_slug = cred.get("org_slug") or ("imowi" if cred["rol"] == "admin" else "coop-batan")
    token = _crear_token(
        {
            "usuario": data.usuario,
            "rol": cred["rol"],
            "cooperativa": cred["cooperativa"],
            "nombre": cred["nombre"],
            "org_slug": org_slug,
        }
    )
    return LoginResponse(
        token=token,
        rol=cred["rol"],
        usuario=data.usuario,
        cooperativa=cred["cooperativa"],
        nombre=cred["nombre"],
        org_slug=org_slug,
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
    if user.password != data.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
        )

    rol_token = _rol_token_desde_estate(user.rol, org.slug)
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
    )


def _rol_token_desde_estate(rol: str, org_slug: str) -> str:
    if org_slug == "imowi" and rol in ("admin_sistema", "admin", "ingeniero_noc"):
        return "admin"
    if rol in ("admin_sistema", "admin"):
        return "admin"
    return "cooperativa"


def _resolver_sesion(token: str | None) -> UsuarioSesion | None:
    if not token:
        return None
    payload = _decodificar_token(token)
    if not payload:
        return None
    rol = payload.get("rol", "")
    return UsuarioSesion(
        usuario=payload.get("usuario", ""),
        rol=rol,
        cooperativa=payload.get("cooperativa"),
        nombre=payload.get("nombre", ""),
        org_slug=payload.get("org_slug") or ("imowi" if rol == "admin" else "coop-batan"),
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
