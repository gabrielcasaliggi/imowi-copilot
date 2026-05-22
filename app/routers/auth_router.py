from fastapi import APIRouter, Depends

from app.auth import UsuarioSesion, login_usuario, obtener_usuario_requerido
from app.models import LoginInput, LoginResponse

router = APIRouter(prefix="/api", tags=["Autenticación"])


@router.post("/login", response_model=LoginResponse)
async def login(data: LoginInput) -> LoginResponse:
    return login_usuario(data)


@router.get("/me")
async def perfil(usuario: UsuarioSesion = Depends(obtener_usuario_requerido)):
    return {
        "usuario": usuario.usuario,
        "rol": usuario.rol,
        "cooperativa": usuario.cooperativa,
        "nombre": usuario.nombre,
    }
