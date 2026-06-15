from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.deps import get_tenant_context, require_kb_admin
from app.api.v1.schemas import TenantContext, TicketUpdateV1
from app.estate import repository as repo
from app.estate.database import get_db
from app.services import ticket_bridge

router = APIRouter(tags=["Tickets OSS/BSS"])


def _ticket_out(t) -> dict:
    org = getattr(t, "organizacion", None)
    return {
        "id": t.id,
        "organizacion": org.nombre if org else "",
        "organizacion_id": t.organizacion_id,
        "linea": t.linea,
        "dispositivo": t.dispositivo,
        "descripcion_falla": t.descripcion_falla,
        "origen": t.origen,
        "estado": t.estado,
        "resolucion_tecnica": t.resolucion_tecnica,
        "categoria": t.categoria,
        "intent_ejecutado": t.intent_ejecutado,
        "creado_por": t.creado_por,
        "nivel": getattr(t, "nivel", "N1"),
        "destino": getattr(t, "destino", "cooperativa"),
        "proveedor": getattr(t, "proveedor", ""),
        "motivo_escalamiento": getattr(t, "motivo_escalamiento", ""),
        "evidencia": getattr(t, "evidencia", ""),
        "regla_clasificacion": getattr(t, "regla_clasificacion", ""),
        "estado_sla": getattr(t, "estado_sla", "Pendiente"),
        "ticket_externo_id": getattr(t, "ticket_externo_id", ""),
        "created_at": t.created_at.isoformat() if t.created_at else "",
        "updated_at": t.updated_at.isoformat() if t.updated_at else "",
    }


def _event_out(e) -> dict:
    return {
        "id": e.id,
        "ticket_id": e.ticket_id,
        "tipo": e.tipo,
        "titulo": e.titulo,
        "detalle": e.detalle,
        "nivel": e.nivel,
        "estado": e.estado,
        "actor": e.actor,
        "visible_cliente": e.visible_cliente,
        "created_at": e.created_at.isoformat() if e.created_at else "",
    }


def _notification_out(n) -> dict:
    return {
        "id": n.id,
        "ticket_id": n.ticket_id,
        "destinatario": n.destinatario,
        "canal": n.canal,
        "titulo": n.titulo,
        "mensaje": n.mensaje,
        "leida": n.leida,
        "created_at": n.created_at.isoformat() if n.created_at else "",
    }


@router.get("/tickets")
def list_tickets(ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    tickets = ticket_bridge.listar_tickets(
        db, ctx.organizacion_id, admin_global=ctx.es_admin_imowi and ctx.organizacion_slug == "imowi"
    )
    return {"tenant": ctx.organizacion_slug, "tickets": [_ticket_out(t) for t in tickets]}


@router.get("/tickets/notifications")
def list_notifications(
    unread: bool = False,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    destinatario = "" if ctx.es_admin_imowi else ctx.usuario_email
    items = repo.list_ticket_notifications(
        db,
        ctx.organizacion_id,
        destinatario=destinatario,
        solo_no_leidas=unread,
        admin_global=ctx.es_admin_imowi and ctx.organizacion_slug == "imowi",
    )
    return {"tenant": ctx.organizacion_slug, "notificaciones": [_notification_out(n) for n in items]}


@router.put("/tickets/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    n = repo.mark_notification_read(db, ctx.organizacion_id, notification_id)
    if not n:
        raise HTTPException(404, f"Notificación {notification_id} no encontrada")
    return {"status": "ok", "notificacion": _notification_out(n)}


@router.get("/tickets/{ticket_id}")
def get_ticket_detail(
    ticket_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    admin_global = ctx.es_admin_imowi and ctx.organizacion_slug == "imowi"
    t = repo.get_ticket(db, ctx.organizacion_id, ticket_id, admin_global=admin_global)
    if not t:
        raise HTTPException(404, f"Ticket {ticket_id} no encontrado")
    eventos = repo.list_ticket_events(
        db,
        ctx.organizacion_id,
        ticket_id,
        solo_visibles=not ctx.es_admin_imowi,
        admin_global=admin_global,
    )
    return {
        "tenant": ctx.organizacion_slug,
        "ticket": _ticket_out(t),
        "timeline": [_event_out(e) for e in eventos],
    }


@router.get("/tickets/{ticket_id}/timeline")
def get_ticket_timeline(
    ticket_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    eventos = repo.list_ticket_events(
        db,
        ctx.organizacion_id,
        ticket_id,
        solo_visibles=not ctx.es_admin_imowi,
        admin_global=ctx.es_admin_imowi and ctx.organizacion_slug == "imowi",
    )
    return {"tenant": ctx.organizacion_slug, "ticket_id": ticket_id, "timeline": [_event_out(e) for e in eventos]}


@router.put("/tickets/{ticket_id}")
def update_ticket(
    ticket_id: str,
    body: TicketUpdateV1,
    ctx: TenantContext = Depends(require_kb_admin),
    db: Session = Depends(get_db),
):
    if not ctx.es_admin_imowi:
        raise HTTPException(403, "Solo el administrador NOC puede actualizar seguimiento de tickets")
    t = repo.update_ticket(
        db,
        ctx.organizacion_id,
        ticket_id,
        estado=body.estado,
        resolucion_tecnica=body.resolucion_tecnica,
        descripcion_falla=body.descripcion_falla,
        nivel=body.nivel,
        destino=body.destino,
        proveedor=body.proveedor,
        motivo_escalamiento=body.motivo_escalamiento,
        estado_sla=body.estado_sla,
        ticket_externo_id=body.ticket_externo_id,
        admin_global=ctx.es_admin_imowi and ctx.organizacion_slug == "imowi",
    )
    if not t:
        raise HTTPException(404, f"Ticket {ticket_id} no encontrado")
    return {"status": "ok", "ticket": _ticket_out(t)}
