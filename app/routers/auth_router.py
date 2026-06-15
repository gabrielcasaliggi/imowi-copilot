from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import UsuarioSesion, login_usuario_db, obtener_usuario_requerido
from app.estate.database import get_db
from app.models import LoginInput, LoginResponse

router = APIRouter(prefix="/api", tags=["Autenticación"])


@router.post("/login", response_model=LoginResponse)
async def login(data: LoginInput, db: Session = Depends(get_db)) -> LoginResponse:
    return login_usuario_db(data, db)


@router.get("/me")
async def perfil(usuario: UsuarioSesion = Depends(obtener_usuario_requerido)):
    return {
        "usuario": usuario.usuario,
        "rol": usuario.rol,
        "cooperativa": usuario.cooperativa,
        "nombre": usuario.nombre,
        "org_slug": usuario.org_slug,
    }
