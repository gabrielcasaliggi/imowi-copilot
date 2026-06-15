from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents.pipeline import procesar_mensaje
from app.api.v1.deps import get_tenant_context
from app.api.v1.schemas import ChatV1Request, ChatV1Response, TenantContext
from app.estate.database import get_db

router = APIRouter(tags=["Agentic Chat"])


@router.post("/chat", response_model=ChatV1Response)
async def chat_v1(
    body: ChatV1Request,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    historial = [m.model_dump() for m in body.historial]
    mensaje = body.mensaje.strip()
    if mensaje:
        historial.append({"rol": "usuario", "contenido": mensaje})

    if not historial:
        return ChatV1Response(
            respuesta="Contame el inconveniente del cliente (cooperativa, línea, síntoma).",
            relevante=False,
            prefilter_motivo="vacío",
            agent_traces=["🛡️ [Pre-LLM]: Sin mensajes."],
        )

    ultimo = historial[-1]["contenido"] if historial[-1]["rol"] == "usuario" else mensaje
    session_id = (body.session_id or "").strip() or f"{ctx.organizacion_id}:{ctx.usuario_email}"
    accion = (body.accion_operador or "").strip() or None
    result = await procesar_mensaje(
        db,
        ctx.organizacion_id,
        historial[:-1] if historial[-1]["rol"] == "usuario" else historial,
        ultimo,
        creado_por=ctx.usuario_email,
        forzar_escalamiento=body.forzar_escalamiento,
        admin_global=ctx.es_admin_imowi,
        session_id=session_id,
        usuario=ctx.usuario_email,
        accion_operador=accion,
    )
    return ChatV1Response(**result)
