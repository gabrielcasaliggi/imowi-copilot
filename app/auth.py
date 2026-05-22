"""Autenticación por JWT (stateless, apta para PaaS sin disco)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import AUTH_SECRET, AUTH_TOKEN_HOURS, MOCK_USERS, es_produccion
from app.models import LoginInput, LoginResponse

_bearer = HTTPBearer(auto_error=False)
_ALGORITMO = "HS256"


def _secret_efectivo() -> str:
    if AUTH_SECRET:
        return AUTH_SECRET
    if es_produccion():
        raise RuntimeError("AUTH_SECRET es obligatorio cuando APP_ENV=production")
    return "dev-secret-no-usar-en-produccion"


@dataclass
class UsuarioSesion:
    usuario: str
    rol: str
    cooperativa: str | None
    nombre: str


def _crear_token(payload: dict) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=AUTH_TOKEN_HOURS)
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

    token = _crear_token(
        {
            "usuario": data.usuario,
            "rol": cred["rol"],
            "cooperativa": cred["cooperativa"],
            "nombre": cred["nombre"],
        }
    )
    return LoginResponse(
        token=token,
        rol=cred["rol"],
        usuario=data.usuario,
        cooperativa=cred["cooperativa"],
        nombre=cred["nombre"],
    )


def _resolver_sesion(token: str | None) -> UsuarioSesion | None:
    if not token:
        return None
    payload = _decodificar_token(token)
    if not payload:
        return None
    return UsuarioSesion(
        usuario=payload.get("usuario", ""),
        rol=payload.get("rol", ""),
        cooperativa=payload.get("cooperativa"),
        nombre=payload.get("nombre", ""),
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
