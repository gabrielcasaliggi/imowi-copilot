from fastapi import APIRouter, Depends

from app.auth import UsuarioSesion, obtener_usuario_requerido
from app.knowledge import estadisticas, listar_muestra_modulos
from app.models import ChatInput, ChatResponse, EstructurarInput, EstructurarResponse, GuardarTicketInput
from app.services.chat_service import procesar_chat
from app.services.extraction_service import estructurar_ticket
from app import tickets_store

router = APIRouter(prefix="/api", tags=["Copilot"])


@router.get("/modulos")
async def obtener_modulos():
    """Muestra de bloques KB cargados desde el Markdown."""
    stats = estadisticas()
    return {
        "fuente": stats.get("archivo"),
        "total_bloques": stats.get("total_bloques", 0),
        "modulos": listar_muestra_modulos(30),
    }


@router.get("/knowledge/status")
async def knowledge_status():
    return estadisticas()


@router.post("/chat", response_model=ChatResponse)
async def chat(data: ChatInput):
    return await procesar_chat(data)


@router.post("/estructurar-ticket", response_model=EstructurarResponse)
@router.post("/estructurar", response_model=EstructurarResponse)
async def estructurar(data: EstructurarInput):
    return await estructurar_ticket(data)


# --- Legacy compat ---

@router.post("/crear-ticket")
async def crear_ticket_legacy(
    data: GuardarTicketInput,
    usuario: UsuarioSesion = Depends(obtener_usuario_requerido),
):
    payload = data.model_copy()
    if not payload.descripcion:
        payload.descripcion = payload.falla_exacta
    ticket = tickets_store.crear_ticket(payload, creado_por=usuario.usuario)
    return {"status": "success", "ticket": ticket.model_dump()}


@router.get("/listar-tickets")
async def listar_tickets_legacy():
    tickets = tickets_store.listar_todos()
    return {"tickets": [t.model_dump() for t in tickets]}


@router.patch("/cerrar-ticket/{ticket_id}")
async def cerrar_ticket_legacy(ticket_id: str):
    ticket = tickets_store.cerrar_ticket_legacy(ticket_id)
    return {"status": "success", "ticket": ticket.model_dump()}
