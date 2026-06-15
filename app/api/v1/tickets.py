from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.deps import get_tenant_context, require_kb_admin
from app.api.v1.schemas import TenantContext, TicketUpdateV1
from app.estate import repository as repo
from app.estate.audit import log_audit
from app.estate.database import get_db
from app.estate.learning_loop import similares_con_resolucion, sugerir_kb
from app.estate.ticket_intelligence import calcular_prioridad, explicar_escalamiento, ordenar_por_riesgo
from app.services import ticket_bridge

router = APIRouter(tags=["Tickets OSS/BSS"])


def _org_name(t) -> str:
    org = getattr(t, "organizacion", None)
    return org.nombre if org else ""


def _ticket_out(t, *, pool=None, db=None) -> dict:
    org = getattr(t, "organizacion", None)
    if db is not None and t.estado != "Cerrado":
        sla = repo.ensure_ticket_sla(db, t)
    else:
        sla = (calcular_prioridad(t, pool=pool, org_name=org.nombre if org else "").get("sla") or {})
    intel = calcular_prioridad(t, pool=pool, org_name=org.nombre if org else "")
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
        "estado_sla": sla.get("estado_sla") or getattr(t, "estado_sla", "Pendiente"),
        "sla_policy": sla.get("sla_policy") or getattr(t, "sla_policy", ""),
        "sla_due_at": sla.get("sla_due_at"),
        "sla_breached_at": sla.get("sla_breached_at"),
        "sla_label": sla.get("label", ""),
        "ticket_externo_id": getattr(t, "ticket_externo_id", ""),
        "created_at": t.created_at.isoformat() if t.created_at else "",
        "updated_at": t.updated_at.isoformat() if t.updated_at else "",
        "intelligence": intel,
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


def _load_pool(db: Session, ctx: TenantContext) -> list:
    admin_global = ctx.es_admin_imowi and ctx.organizacion_slug == "imowi"
    return ticket_bridge.listar_tickets(db, ctx.organizacion_id, admin_global=admin_global)


@router.get("/tickets")
def list_tickets(ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    admin_global = ctx.es_admin_imowi and ctx.organizacion_slug == "imowi"
    tickets = ticket_bridge.listar_tickets(db, ctx.organizacion_id, admin_global=admin_global)
    pool = tickets
    scored = ordenar_por_riesgo(tickets, pool=pool)
    open_ids = {t.id for t, _ in scored}
    rest = [t for t in tickets if t.id not in open_ids]
    ordered = [t for t, _ in scored] + rest
    return {
        "tenant": ctx.organizacion_slug,
        "tickets": [_ticket_out(t, pool=pool, db=db) for t in ordered],
    }


@router.get("/tickets/prioritized")
def list_prioritized_tickets(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    if not ctx.es_admin_imowi:
        raise HTTPException(403, "Cola priorizada exclusiva del administrador NOC")
    pool = _load_pool(db, ctx)
    scored = ordenar_por_riesgo(pool, pool=pool)
    return {
        "tenant": ctx.organizacion_slug,
        "cola": [
            {"ticket": _ticket_out(t, pool=pool, db=db), "intelligence": intel}
            for t, intel in scored[:20]
        ],
    }


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
    pool = _load_pool(db, ctx)
    eventos = repo.list_ticket_events(
        db,
        ctx.organizacion_id,
        ticket_id,
        solo_visibles=not ctx.es_admin_imowi,
        admin_global=admin_global,
    )
    org_id = t.organizacion_id
    similares = similares_con_resolucion(db, org_id, t)
    kb = sugerir_kb(db, org_id, t)
    learning = None
    if t.estado == "Cerrado":
        org = repo.get_org_by_id(db, org_id)
        learning = {
            "kb_sugerencias": kb,
            "similares_resueltos": [s for s in similares if s.get("cerrado")],
            "postmortem": next(
                (e.detalle for e in eventos if e.tipo == "aprendizaje"),
                None,
            ),
        }
    return {
        "tenant": ctx.organizacion_slug,
        "ticket": _ticket_out(t, pool=pool, db=db),
        "timeline": [_event_out(e) for e in eventos],
        "tickets_similares": similares,
        "kb_sugerencias": kb,
        "learning": learning,
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


@router.get("/tickets/{ticket_id}/explain-escalation")
def explain_escalation(
    ticket_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    if not ctx.es_admin_imowi:
        raise HTTPException(403, "Solo el administrador NOC puede generar explicación de escalamiento")
    admin_global = ctx.es_admin_imowi and ctx.organizacion_slug == "imowi"
    t = repo.get_ticket(db, ctx.organizacion_id, ticket_id, admin_global=admin_global)
    if not t:
        raise HTTPException(404, f"Ticket {ticket_id} no encontrado")
    org = repo.get_org_by_id(db, t.organizacion_id)
    texto = explicar_escalamiento(t, org_name=org.nombre if org else "")
    log_audit(
        db,
        org_id=t.organizacion_id,
        actor=ctx.usuario_email,
        accion="explain_escalation",
        recurso=ticket_id,
        detalle=texto[:500],
    )
    return {"ticket_id": ticket_id, "explicacion": texto}


@router.put("/tickets/{ticket_id}")
def update_ticket(
    ticket_id: str,
    body: TicketUpdateV1,
    ctx: TenantContext = Depends(require_kb_admin),
    db: Session = Depends(get_db),
):
    if not ctx.es_admin_imowi:
        raise HTTPException(403, "Solo el administrador NOC puede actualizar seguimiento de tickets")
    admin_global = ctx.es_admin_imowi and ctx.organizacion_slug == "imowi"
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
        admin_global=admin_global,
    )
    if not t:
        raise HTTPException(404, f"Ticket {ticket_id} no encontrado")
    accion = "ticket_cierre" if body.estado == "Cerrado" else "ticket_actualizacion"
    log_audit(
        db,
        org_id=t.organizacion_id,
        actor=ctx.usuario_email,
        accion=accion,
        recurso=ticket_id,
        detalle=f"estado={body.estado or t.estado} nivel={body.nivel or t.nivel}",
    )
    pool = _load_pool(db, ctx)
    return {"status": "ok", "ticket": _ticket_out(t, pool=pool, db=db)}
