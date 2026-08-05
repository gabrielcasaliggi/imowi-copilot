from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.auth import UsuarioSesion, login_usuario_db, logout_sesion, obtener_usuario_requerido
from app.estate.database import get_db
from app.http_cookies import clear_console_cookie, set_console_cookie
from app.models import LoginInput, LoginResponse

router = APIRouter(prefix="/api", tags=["Autenticación"])


@router.post("/login", response_model=LoginResponse)
async def login(
    data: LoginInput,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    result = login_usuario_db(data, db, request=request)
    set_console_cookie(response, result.token, request=request)
    return result


@router.post("/logout")
async def logout(
    response: Response,
    usuario: UsuarioSesion = Depends(obtener_usuario_requerido),
    db: Session = Depends(get_db),
):
    logout_sesion(db, usuario)
    clear_console_cookie(response)
    return {"status": "ok"}


@router.get("/me")
async def perfil(usuario: UsuarioSesion = Depends(obtener_usuario_requerido)):
    from app.rbac import normalizar_rol_consola, permisos_para_rol

    rol = normalizar_rol_consola(usuario.rol, usuario.org_slug)
    return {
        "usuario": usuario.usuario,
        "rol": rol,
        "cooperativa": usuario.cooperativa,
        "nombre": usuario.nombre,
        "org_slug": usuario.org_slug,
        "permisos": sorted(permisos_para_rol(rol)),
        "must_change_password": usuario.must_change_password,
    }
