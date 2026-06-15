from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_tenant_context, require_kb_admin
from app.api.v1.schemas import KBCreate, TenantContext
from app.estate.database import get_db
from app.estate import repository as repo

router = APIRouter(tags=["Knowledge Estate"])


@router.get("/kb")
def list_kb(ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    arts = repo.list_kb(db, ctx.organizacion_id)
    return {
        "tenant": ctx.organizacion_slug,
        "articulos": [
            {
                "id": a.id,
                "titulo": a.titulo,
                "categoria": a.categoria,
                "contenido": a.contenido,
                "created_at": a.created_at.isoformat() if a.created_at else "",
            }
            for a in arts
        ],
    }


@router.post("/kb")
def create_kb(
    body: KBCreate,
    ctx: TenantContext = Depends(require_kb_admin),
    db: Session = Depends(get_db),
):
    art = repo.add_kb(db, ctx.organizacion_id, body.titulo, body.categoria, body.contenido)
    return {
        "status": "ok",
        "articulo": {
            "id": art.id,
            "titulo": art.titulo,
            "categoria": art.categoria,
        },
    }
