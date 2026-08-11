from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.deps import get_tenant_context, require_kb_proposer
from app.api.v1.schemas import (
    TenantContext,
    TicketBulkClose,
    TicketEventCreate,
    TicketKbPublish,
    TicketReassign,
    TicketUpdateV1,
)
from app.estate import repository as repo
from app.estate.audit import log_audit
from app.estate.database import get_db
from app.estate.learning_loop import (
    crear_propuesta_kb_desde_ticket,
    proponer_articulo_kb,
    similares_con_resolucion,
    sugerir_kb,
)
from app.estate.ticket_intelligence import (
    calcular_prioridad,
    explicar_escalamiento,
    ordenar_por_riesgo,
)
from app.services import ticket_bridge
from app.services.ticket_queue import filtrar_tickets

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
        "asignado_a": getattr(t, "asignado_a", "") or "",
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


def _ver_timeline_interno(ctx: TenantContext) -> bool:
    """Admin y supervisor ven notas internas / trazabilidad operativa completa."""
    return bool(
        ctx.es_admin_imowi
        or ctx.puede("tickets.reassign")
        or ctx.puede("orgs.manage")
    )


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
def list_tickets(
    estado: str = "",
    nivel: str = "",
    sla: str = "",
    categoria: str = "",
    q: str = "",
    solo_abiertos: bool = False,
    asignacion: str = "",
    asignado_a: str = "",
    limit: int = 50,
    offset: int = 0,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    if not ctx.puede("tickets.queue.view") and not ctx.puede("tickets.view"):
        raise HTTPException(403, "Sin permiso para ver la cola de tickets")
    admin_global = ctx.es_admin_imowi and ctx.organizacion_slug == "imowi"
    tickets = ticket_bridge.listar_tickets(db, ctx.organizacion_id, admin_global=admin_global)
    pool = tickets
    tickets = filtrar_tickets(
        tickets,
        estado=estado,
        nivel=nivel,
        sla=sla,
        categoria=categoria,
        q=q,
        solo_abiertos=solo_abiertos,
        asignacion=asignacion,
        asignado_a=asignado_a,
    )
    scored = ordenar_por_riesgo(tickets, pool=pool)
    open_ids = {t.id for t, _ in scored}
    rest = [t for t in tickets if t.id not in open_ids]
    ordered = [t for t, _ in scored] + rest
    lim = max(1, min(int(limit or 50), 100))
    off = max(0, int(offset or 0))
    total = len(ordered)
    page = ordered[off : off + lim]
    return {
        "tenant": ctx.organizacion_slug,
        "filtros": {
            "estado": estado,
            "nivel": nivel,
            "sla": sla,
            "categoria": categoria,
            "q": q,
            "solo_abiertos": solo_abiertos,
            "asignacion": asignacion,
            "asignado_a": asignado_a,
        },
        "tickets": [_ticket_out(t, pool=pool, db=db) for t in page],
        "total": total,
        "limit": lim,
        "offset": off,
    }


def _puede_cierre_masivo(ctx: TenantContext) -> bool:
    if ctx.es_admin_imowi or ctx.puede("orgs.manage"):
        return True
    if ctx.rol in ("admin", "supervisor"):
        return True
    return ctx.puede("tickets.reassign") and ctx.puede("tickets.update")


@router.post("/tickets/bulk-close")
def bulk_close_tickets(
    body: TicketBulkClose,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Cierra todos los tickets no cerrados del tenant (limpieza operativa).

    No genera propuestas KB ni encuestas CSAT. Usar dry_run=true para previsualizar.
    """
    if not _puede_cierre_masivo(ctx):
        raise HTTPException(403, "Solo admin/supervisor puede hacer cierre masivo")
    if ctx.es_admin_imowi and ctx.organizacion_slug == "imowi":
        raise HTTPException(
            400,
            "Elegí una cooperativa (tenant) concreta; no se puede cerrar en masa desde vista global imowi.",
        )
    if not body.dry_run and not body.confirmar:
        raise HTTPException(
            400,
            "Para ejecutar el cierre enviá confirmar=true (o dry_run=true para previsualizar).",
        )
    try:
        resultado = repo.cerrar_tickets_abiertos(
            db,
            ctx.organizacion_id,
            resolucion_tecnica=body.resolucion_tecnica,
            actor=ctx.usuario_email or ctx.rol,
            dry_run=body.dry_run,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    if not body.dry_run and resultado.get("tickets_cerrados", 0) > 0:
        log_audit(
            db,
            org_id=ctx.organizacion_id,
            actor=ctx.usuario_email,
            accion="ticket_cierre_masivo",
            recurso=ctx.organizacion_slug,
            detalle=(
                f"cerrados={resultado['tickets_cerrados']} "
                f"convs={resultado.get('conversaciones_cerradas', 0)}"
            ),
        )
    return {
        "status": "ok",
        "tenant": ctx.organizacion_slug,
        **resultado,
    }


@router.get("/tickets/prioritized")
def list_prioritized_tickets(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    if not ctx.puede("tickets.queue.view"):
        raise HTTPException(403, "Sin permiso para ver la cola priorizada")
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
    admin_global = ctx.es_admin_imowi and ctx.organizacion_slug == "imowi"
    ve_alertas_equipo = (
        ctx.es_admin_imowi
        or ctx.puede("stats.agents")
        or ctx.puede("users.manage_agents")
        or ctx.puede("stats.global")
    )
    # Admin: todas. Supervisor: propias + CSAT bajo de la org. Agente: solo propias.
    if ctx.es_admin_imowi:
        destinatario = ""
        incluir_csat_org = False
    elif ve_alertas_equipo:
        destinatario = ctx.usuario_email or ""
        incluir_csat_org = True
    else:
        destinatario = ctx.usuario_email or ""
        incluir_csat_org = False

    # Descarta alertas de tickets ya cerrados (p. ej. asignación vieja); CSAT_BAJO se conserva
    repo.dismiss_notifications_for_closed_tickets(
        db,
        ctx.organizacion_id,
        destinatario="" if ctx.es_admin_imowi else (ctx.usuario_email or ""),
        admin_global=admin_global,
    )
    items = repo.list_ticket_notifications(
        db,
        ctx.organizacion_id,
        destinatario=destinatario,
        solo_no_leidas=unread,
        admin_global=admin_global,
        incluir_csat_org=incluir_csat_org,
    )
    return {"tenant": ctx.organizacion_slug, "notificaciones": [_notification_out(n) for n in items]}


@router.put("/tickets/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    if ctx.es_admin_imowi:
        n = repo.mark_notification_read(
            db,
            ctx.organizacion_id,
            notification_id,
            admin_global=True,
        )
    else:
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
        solo_visibles=not _ver_timeline_interno(ctx),
        admin_global=admin_global,
    )
    org_id = t.organizacion_id
    similares = similares_con_resolucion(db, org_id, t)
    kb = sugerir_kb(db, org_id, t)
    learning = None
    if t.estado == "Cerrado":
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
        solo_visibles=not _ver_timeline_interno(ctx),
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


@router.post("/tickets/{ticket_id}/events")
def add_ticket_event(
    ticket_id: str,
    body: TicketEventCreate,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    admin_global = ctx.es_admin_imowi and ctx.organizacion_slug == "imowi"
    t = repo.get_ticket(db, ctx.organizacion_id, ticket_id, admin_global=admin_global)
    if not t:
        raise HTTPException(404, f"Ticket {ticket_id} no encontrado")
    detalle = (body.detalle or "").strip()
    if not detalle:
        raise HTTPException(400, "El detalle de la nota es obligatorio")
    ev = repo.add_ticket_event(
        db,
        t.organizacion_id,
        ticket_id,
        tipo="nota_interna" if body.interno else "nota",
        titulo=body.titulo or ("Nota interna" if body.interno else "Nota"),
        detalle=detalle,
        nivel=t.nivel or "N1",
        estado=t.estado or "Abierto",
        actor=ctx.usuario_email,
        visible_cliente="No" if body.interno else "Sí",
    )
    log_audit(
        db,
        org_id=t.organizacion_id,
        actor=ctx.usuario_email,
        accion="ticket_nota",
        recurso=ticket_id,
        detalle=detalle[:300],
    )
    return {"status": "ok", "evento": _event_out(ev)}


@router.get("/tickets/{ticket_id}/kb-draft")
def get_ticket_kb_draft(
    ticket_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    admin_global = ctx.es_admin_imowi and ctx.organizacion_slug == "imowi"
    t = repo.get_ticket(db, ctx.organizacion_id, ticket_id, admin_global=admin_global)
    if not t:
        raise HTTPException(404, f"Ticket {ticket_id} no encontrado")
    org = repo.get_org_by_id(db, t.organizacion_id)
    borrador = proponer_articulo_kb(t, org_name=org.nombre if org else "")
    return {"tenant": ctx.organizacion_slug, "ticket_id": ticket_id, "borrador": borrador}


@router.post("/tickets/{ticket_id}/publish-kb")
def publish_ticket_kb(
    ticket_id: str,
    body: TicketKbPublish,
    ctx: TenantContext = Depends(require_kb_proposer),
    db: Session = Depends(get_db),
):
    """Propone artículo KB desde ticket (queda en bandeja admin; no publica directo)."""
    admin_global = ctx.es_admin_imowi and ctx.organizacion_slug == "imowi"
    t = repo.get_ticket(db, ctx.organizacion_id, ticket_id, admin_global=admin_global)
    if not t:
        raise HTTPException(404, f"Ticket {ticket_id} no encontrado")
    org = repo.get_org_by_id(db, t.organizacion_id)
    contrib = crear_propuesta_kb_desde_ticket(
        db,
        t.organizacion_id,
        t,
        org_name=org.nombre if org else "",
        propuesto_por=ctx.usuario_email,
        origen="agente",
        titulo=body.titulo,
        categoria=body.categoria,
        contenido=body.contenido,
        evitar_duplicado_pendiente=False,
    )
    if not contrib:
        raise HTTPException(400, "Título y contenido son obligatorios")
    repo.add_ticket_event(
        db,
        t.organizacion_id,
        ticket_id,
        tipo="kb_propuesta",
        titulo="Propuesta KB enviada a revisión",
        detalle=f"{contrib.titulo} ({contrib.id})",
        nivel=t.nivel or "N1",
        estado=t.estado or "Abierto",
        actor=ctx.usuario_email,
        visible_cliente="No",
    )
    log_audit(
        db,
        org_id=t.organizacion_id,
        actor=ctx.usuario_email,
        accion="kb_propuesta",
        recurso=ticket_id,
        detalle=f"{contrib.id}: {contrib.titulo}",
    )
    return {
        "status": "ok",
        "pendiente_revision": True,
        "contribucion": {
            "id": contrib.id,
            "titulo": contrib.titulo,
            "categoria": contrib.categoria,
            "estado": contrib.estado,
            "origen": contrib.origen,
        },
    }


@router.put("/tickets/{ticket_id}")
def update_ticket(
    ticket_id: str,
    body: TicketUpdateV1,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    admin_global = ctx.es_admin_imowi and ctx.organizacion_slug == "imowi"
    t_existente = repo.get_ticket(db, ctx.organizacion_id, ticket_id, admin_global=admin_global)
    if not t_existente:
        raise HTTPException(404, f"Ticket {ticket_id} no encontrado")

    if not ctx.puede("tickets.update"):
        # Agente: solo puede actualizar tickets asignados a él
        if not ctx.puede("tickets.queue.view"):
            raise HTTPException(403, "Sin permiso para actualizar tickets")
        asignado = (getattr(t_existente, "asignado_a", "") or "").strip().lower()
        yo = (ctx.usuario_email or "").strip().lower()
        alias = yo.split("@", 1)[0]
        if not asignado or (asignado not in {yo, alias} and yo not in asignado):
            raise HTTPException(403, "Solo podés actualizar tickets asignados a vos")
        if body.asignado_a is not None:
            raise HTTPException(403, "Para reasignar usá la derivación del supervisor")
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
        asignado_a=body.asignado_a,
        actor=ctx.usuario_email,
        admin_global=admin_global,
    )
    if not t:
        raise HTTPException(404, f"Ticket {ticket_id} no encontrado")
    accion = "ticket_cierre" if body.estado == "Cerrado" else "ticket_actualizacion"
    # Al cerrar el ticket, cerrar el hilo de canal: el próximo ingreso del abonado abre conversación nueva.
    if body.estado == "Cerrado":
        from app.estate import canal_repo as crepo
        from app.services.encuesta_satisfaccion import ORIGEN_TECNICO, enviar_encuesta_cierre

        conv = crepo.get_conversacion_by_ticket(db, t.organizacion_id, ticket_id)
        if conv and conv.estado != "cerrado":
            conv.estado = "cerrado"
            db.commit()
            crepo.add_mensaje(
                db,
                t.organizacion_id,
                conv.id,
                direccion="out",
                autor="sistema",
                texto="[Sistema] Conversación cerrada al resolver el ticket. Si volvés a escribir, iniciamos un chat nuevo.",
            )
        if conv:
            agente = (
                ctx.usuario_email
                or (getattr(t, "asignado_a", "") or "")
                or conv.agente_id
                or ""
            )
            enviar_encuesta_cierre(
                db,
                conv,
                origen=ORIGEN_TECNICO,
                agente_id=agente,
                enviar_externo=(conv.canal or "") in ("whatsapp", "telegram"),
            )
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


@router.post("/tickets/{ticket_id}/claim")
def claim_ticket(
    ticket_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Agente toma un ticket libre de la cola N2 (queda bloqueado para otros)."""
    if not ctx.puede("tickets.queue.view"):
        raise HTTPException(403, "Sin permiso para tomar tickets de la cola")
    admin_global = ctx.es_admin_imowi and ctx.organizacion_slug == "imowi"
    t = repo.get_ticket(db, ctx.organizacion_id, ticket_id, admin_global=admin_global)
    if not t:
        raise HTTPException(404, f"Ticket {ticket_id} no encontrado")
    if t.estado == "Cerrado":
        raise HTTPException(400, "No se puede tomar un ticket cerrado")
    actual = (getattr(t, "asignado_a", "") or "").strip()
    yo = (ctx.usuario_email or "").strip()
    yo_alias = yo.split("@", 1)[0].lower() if yo else ""
    if actual:
        actual_l = actual.lower()
        if actual_l not in {yo.lower(), yo_alias} and yo.lower() not in actual_l:
            raise HTTPException(409, f"Ticket ya tomado por {actual}")
        pool = _load_pool(db, ctx)
        return {
            "status": "ok",
            "ticket": _ticket_out(t, pool=pool, db=db),
            "ya_asignado": True,
            "conversacion_id": "",
        }

    t = repo.update_ticket(
        db,
        ctx.organizacion_id,
        ticket_id,
        asignado_a=yo,
        actor=yo,
        admin_global=admin_global,
    )
    if not t:
        raise HTTPException(404, f"Ticket {ticket_id} no encontrado")
    # Si hay conversación de canal ligada, también tomarla
    from app.estate import canal_repo as crepo

    conv = crepo.get_conversacion_by_ticket(db, t.organizacion_id, ticket_id)
    if conv and conv.estado != "cerrado":
        conv.estado = "con_agente"
        conv.agente_id = yo
        db.commit()
    log_audit(
        db,
        org_id=t.organizacion_id,
        actor=yo,
        accion="ticket_claim",
        recurso=ticket_id,
        detalle=f"asignado_a={yo}",
    )
    pool = _load_pool(db, ctx)
    return {
        "status": "ok",
        "ticket": _ticket_out(t, pool=pool, db=db),
        "ya_asignado": False,
        "conversacion_id": conv.id if conv else "",
    }


@router.get("/tickets/{ticket_id}/conversation")
def ticket_conversation(
    ticket_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Conversación de canal ligada al ticket (chat con el abonado)."""
    if not (ctx.puede("tickets.view") or ctx.puede("tickets.queue.view")):
        raise HTTPException(403, "Sin permiso")
    admin_global = ctx.es_admin_imowi and ctx.organizacion_slug == "imowi"
    t = repo.get_ticket(db, ctx.organizacion_id, ticket_id, admin_global=admin_global)
    if not t:
        raise HTTPException(404, f"Ticket {ticket_id} no encontrado")
    from app.estate import canal_repo as crepo
    from app.estate.models import Abonado

    conv = crepo.get_conversacion_by_ticket(db, t.organizacion_id, ticket_id)
    if not conv:
        return {
            "tenant": ctx.organizacion_slug,
            "ticket_id": ticket_id,
            "conversacion": None,
            "mensajes": [],
        }
    abo = db.get(Abonado, conv.abonado_id) if conv.abonado_id else None
    mensajes = [crepo.mensaje_to_dict(m) for m in crepo.list_mensajes(db, conv.id)]
    return {
        "tenant": ctx.organizacion_slug,
        "ticket_id": ticket_id,
        "conversacion": crepo.conversacion_to_dict(conv, abonado=abo),
        "mensajes": mensajes,
    }


@router.post("/tickets/{ticket_id}/reassign")
def reassign_ticket(
    ticket_id: str,
    body: TicketReassign,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    if not ctx.puede("tickets.reassign"):
        raise HTTPException(403, "Sin permiso para derivar / reasignar tickets")
    destino = (body.asignado_a or "").strip()
    if not destino:
        raise HTTPException(400, "asignado_a es obligatorio")
    admin_global = ctx.es_admin_imowi and ctx.organizacion_slug == "imowi"
    t = repo.update_ticket(
        db,
        ctx.organizacion_id,
        ticket_id,
        asignado_a=destino,
        actor=ctx.usuario_email,
        admin_global=admin_global,
    )
    if not t:
        raise HTTPException(404, f"Ticket {ticket_id} no encontrado")
    if body.nota.strip():
        repo.add_ticket_event(
            db,
            t.organizacion_id,
            ticket_id,
            tipo="nota",
            titulo="Nota de derivación",
            detalle=body.nota.strip(),
            nivel=t.nivel,
            estado=t.estado,
            actor=ctx.usuario_email,
        )
    log_audit(
        db,
        org_id=t.organizacion_id,
        actor=ctx.usuario_email,
        accion="ticket_reasignacion",
        recurso=ticket_id,
        detalle=f"asignado_a={destino}",
    )
    pool = _load_pool(db, ctx)
    return {"status": "ok", "ticket": _ticket_out(t, pool=pool, db=db)}
