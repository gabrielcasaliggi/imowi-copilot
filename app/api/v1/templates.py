from fastapi import APIRouter, Depends, Query

from app.api.v1.deps import get_tenant_context
from app.api.v1.schemas import TenantContext
from app.services.response_templates import listar_plantillas

router = APIRouter(tags=["Plantillas"])


@router.get("/response-templates")
def get_response_templates(
    categoria: str = "",
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Plantillas de respuesta operativa para NOC/cooperativa."""
    _ = ctx
    return {
        "plantillas": listar_plantillas(categoria=categoria),
    }
