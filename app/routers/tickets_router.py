from fastapi import APIRouter, Depends, HTTPException

from app.auth import UsuarioSesion, obtener_usuario_requerido, requiere_admin
from app.models import Ticket, TicketUpdateInput
from app import tickets_store

router = APIRouter(prefix="/api", tags=["Tickets"])


@router.get("/tickets", response_model=list[Ticket])
async def listar_tickets(usuario: UsuarioSesion = Depends(obtener_usuario_requerido)):
    """
    Admin: todos los tickets.
    Cooperativa: solo los de su cooperativa.
    """
    if usuario.rol == "admin":
        return tickets_store.listar_todos()
    return tickets_store.listar_por_operador(usuario.usuario, usuario.cooperativa)


@router.get("/tickets/{ticket_id}", response_model=Ticket)
async def detalle_ticket(
    ticket_id: str,
    usuario: UsuarioSesion = Depends(obtener_usuario_requerido),
):
    raw = tickets_store.obtener_ticket(ticket_id)
    if not raw:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Ticket no encontrado")

    if usuario.rol == "cooperativa":
        if raw.get("creado_por", "").strip().lower() != usuario.usuario.strip().lower():
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Sin permiso para este ticket")

    from app.models import Ticket
    return Ticket(**raw)


def _verificar_permiso_cooperativa(raw: dict, usuario: UsuarioSesion) -> None:
    if raw.get("creado_por", "").strip().lower() != usuario.usuario.strip().lower():
        raise HTTPException(status_code=403, detail="Sin permiso para este ticket")


@router.patch("/tickets/{ticket_id}", response_model=Ticket)
async def actualizar_contenido_ticket(
    ticket_id: str,
    data: TicketUpdateInput,
    usuario: UsuarioSesion = Depends(obtener_usuario_requerido),
):
    """Cooperativa: actualiza datos del reclamo al retomar o ampliar el caso."""
    if usuario.rol != "cooperativa":
        raise HTTPException(status_code=403, detail="Solo operadores de cooperativa")
    raw = tickets_store.obtener_ticket(ticket_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    _verificar_permiso_cooperativa(raw, usuario)
    return tickets_store.actualizar_ticket(ticket_id, data, solo_contenido=True)


@router.put("/tickets/{ticket_id}", response_model=Ticket)
async def actualizar_ticket(
    ticket_id: str,
    data: TicketUpdateInput,
    _admin: UsuarioSesion = Depends(requiere_admin),
):
    """Admin NOC: estado, resolución y/o contenido."""
    return tickets_store.actualizar_ticket(ticket_id, data, solo_contenido=False)
