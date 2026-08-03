from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents.pipeline import procesar_mensaje
from app.api.v1.deps import get_tenant_context
from app.api.v1.schemas import ChatV1Request, ChatV1Response, TenantContext
from app.estate import repository as repo
from app.estate.database import get_db
from app.services.prompt_safety import clamp_message, sanitize_historial_messages

router = APIRouter(tags=["Agentic Chat"])

_MAX_CHAT_CHARS = 4000


@router.post("/chat", response_model=ChatV1Response)
async def chat_v1(
    body: ChatV1Request,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    mensaje = clamp_message(body.mensaje.strip(), max_chars=_MAX_CHAT_CHARS)
    session_id = (body.session_id or "").strip() or f"{ctx.organizacion_id}:{ctx.usuario_email}"

    # Preferir historial server-side (no confiar en roles/contenido spoofeados del cliente)
    caso = repo.get_caso_conversacion(db, ctx.organizacion_id, session_id)
    server_hist = []
    if caso and isinstance(caso.get("datos_triaje"), dict):
        server_hist = caso["datos_triaje"].get("historial_mensajes") or []

    if server_hist:
        historial = sanitize_historial_messages(server_hist)
    else:
        # Bootstrap: primer turno / sesión nueva — sanitizar lo que manda el cliente
        historial = sanitize_historial_messages([m.model_dump() for m in body.historial])

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

    # Persistir turnos en el caso (si ya existe tras el motor)
    respuesta = (result.get("respuesta") or "").strip()
    if ultimo or respuesta:
        repo.merge_caso_historial_mensajes(
            db,
            ctx.organizacion_id,
            session_id,
            [
                *([{"rol": "usuario", "contenido": ultimo}] if ultimo else []),
                *([{"rol": "asistente", "contenido": respuesta}] if respuesta else []),
            ],
        )

    return ChatV1Response(**result)
