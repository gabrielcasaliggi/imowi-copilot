from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.deps import get_tenant_context, require_kb_proposer, require_kb_reviewer
from app.api.v1.schemas import (
    KBContributionCreate,
    KBContributionReview,
    KBCreate,
    TenantContext,
)
from app.estate import repository as repo
from app.estate.audit import log_audit
from app.estate.database import get_db
from app.estate.learning_loop import crear_propuesta_kb_desde_ticket

router = APIRouter(tags=["Knowledge Estate"])


def _contrib_out(c, db: Session | None = None) -> dict:
    org_slug = ""
    org_nombre = ""
    if db is not None and getattr(c, "organizacion_id", None):
        org = repo.get_org_by_id(db, c.organizacion_id)
        if org:
            org_slug = org.slug or ""
            org_nombre = org.nombre or ""
    return {
        "id": c.id,
        "ticket_id": c.ticket_id,
        "titulo": c.titulo,
        "categoria": c.categoria,
        "contenido": c.contenido,
        "estado": c.estado,
        "origen": c.origen,
        "nivel_ticket": c.nivel_ticket,
        "propuesto_por": c.propuesto_por,
        "revisado_por": c.revisado_por,
        "motivo_revision": c.motivo_revision,
        "articulo_id": c.articulo_id,
        "organizacion_id": getattr(c, "organizacion_id", "") or "",
        "organizacion_slug": org_slug,
        "organizacion_nombre": org_nombre,
        "created_at": c.created_at.isoformat() if c.created_at else "",
        "updated_at": c.updated_at.isoformat() if c.updated_at else "",
    }


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
    ctx: TenantContext = Depends(require_kb_reviewer),
    db: Session = Depends(get_db),
):
    """Alta directa de artículo — solo admin (sin bandeja)."""
    art = repo.add_kb(db, ctx.organizacion_id, body.titulo, body.categoria, body.contenido)
    log_audit(
        db,
        org_id=ctx.organizacion_id,
        actor=ctx.usuario_email,
        accion="kb_alta_directa",
        recurso=art.id,
        detalle=art.titulo,
    )
    return {
        "status": "ok",
        "articulo": {
            "id": art.id,
            "titulo": art.titulo,
            "categoria": art.categoria,
        },
    }


@router.delete("/kb/{articulo_id}")
def delete_kb(
    articulo_id: str,
    ctx: TenantContext = Depends(require_kb_reviewer),
    db: Session = Depends(get_db),
):
    """Baja de artículo — solo admin (p.ej. subido por error)."""
    art = repo.get_kb(db, ctx.organizacion_id, articulo_id)
    if not art:
        raise HTTPException(404, "Artículo no encontrado")
    titulo = art.titulo
    ok = repo.delete_kb(db, ctx.organizacion_id, articulo_id)
    if not ok:
        raise HTTPException(404, "Artículo no encontrado")
    log_audit(
        db,
        org_id=ctx.organizacion_id,
        actor=ctx.usuario_email,
        accion="kb_baja",
        recurso=articulo_id,
        detalle=titulo,
    )
    return {"status": "ok", "id": articulo_id}


@router.get("/kb/contributions")
def list_kb_contributions(
    estado: str = "pendiente",
    ticket_id: str = "",
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Bandeja de propuestas KB. Por defecto solo pendientes (revisión admin)."""
    if ctx.rol == "cliente":
        raise HTTPException(403, "Sin permiso para ver contribuciones KB")
    admin_global = ctx.es_admin_imowi and ctx.organizacion_slug == "imowi"
    # Agentes ven bandeja; filtro de estado vacío = todas
    filtro = estado if estado != "todas" else ""
    items = repo.list_kb_contributions(
        db,
        ctx.organizacion_id,
        estado=filtro,
        ticket_id=ticket_id,
        admin_global=admin_global,
    )
    return {
        "tenant": ctx.organizacion_slug,
        "estado": estado,
        "contribuciones": [_contrib_out(c, db) for c in items],
    }


@router.post("/kb/contributions")
def create_kb_contribution(
    body: KBContributionCreate,
    ctx: TenantContext = Depends(require_kb_proposer),
    db: Session = Depends(get_db),
):
    """Agente/N2 informa una mejora a KB → queda pendiente de admin."""
    titulo = body.titulo.strip()
    contenido = body.contenido.strip()
    if not titulo or not contenido:
        raise HTTPException(400, "Título y contenido son obligatorios")

    ticket_id = (body.ticket_id or "").strip()
    nivel = ""
    if ticket_id:
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
            origen=body.origen or "agente",
            titulo=titulo,
            categoria=body.categoria,
            contenido=contenido,
            evitar_duplicado_pendiente=False,
        )
        if not contrib:
            raise HTTPException(400, "No se pudo crear la propuesta")
        nivel = t.nivel or "N1"
        repo.add_ticket_event(
            db,
            t.organizacion_id,
            ticket_id,
            tipo="kb_propuesta",
            titulo="Propuesta KB de agente",
            detalle=f"{contrib.titulo} ({contrib.id})",
            nivel=nivel,
            estado=t.estado or "Abierto",
            actor=ctx.usuario_email,
            visible_cliente="No",
        )
        org_id = t.organizacion_id
    else:
        org_id = ctx.organizacion_id
        contrib = repo.add_kb_contribution(
            db,
            org_id,
            titulo=titulo,
            categoria=body.categoria,
            contenido=contenido,
            ticket_id="",
            origen=body.origen or "manual",
            nivel_ticket="",
            propuesto_por=ctx.usuario_email,
        )

    log_audit(
        db,
        org_id=org_id,
        actor=ctx.usuario_email,
        accion="kb_propuesta",
        recurso=contrib.id,
        detalle=f"{contrib.titulo} origen={contrib.origen}",
    )
    return {"status": "ok", "contribucion": _contrib_out(contrib, db)}


@router.get("/kb/contributions/{contrib_id}")
def get_kb_contribution(
    contrib_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    if ctx.rol == "cliente":
        raise HTTPException(403, "Sin permiso para ver contribuciones KB")
    admin_global = ctx.es_admin_imowi and ctx.organizacion_slug == "imowi"
    c = repo.get_kb_contribution(db, ctx.organizacion_id, contrib_id, admin_global=admin_global)
    if not c:
        raise HTTPException(404, f"Contribución {contrib_id} no encontrada")
    return {"tenant": ctx.organizacion_slug, "contribucion": _contrib_out(c, db)}


@router.post("/kb/contributions/{contrib_id}/approve")
def approve_kb_contribution(
    contrib_id: str,
    body: KBContributionReview | None = None,
    ctx: TenantContext = Depends(require_kb_reviewer),
    db: Session = Depends(get_db),
):
    admin_global = ctx.es_admin_imowi and ctx.organizacion_slug == "imowi"
    c = repo.get_kb_contribution(db, ctx.organizacion_id, contrib_id, admin_global=admin_global)
    if not c:
        raise HTTPException(404, f"Contribución {contrib_id} no encontrada")
    if c.estado != "pendiente":
        raise HTTPException(409, f"La contribución ya está {c.estado}")
    body = body or KBContributionReview()
    contrib, art = repo.approve_kb_contribution(
        db,
        c,
        revisado_por=ctx.usuario_email,
        titulo=body.titulo,
        categoria=body.categoria,
        contenido=body.contenido,
        motivo_revision=body.motivo_revision,
    )
    if contrib.ticket_id:
        repo.add_ticket_event(
            db,
            contrib.organizacion_id,
            contrib.ticket_id,
            tipo="kb_publicada",
            titulo="Artículo KB aprobado y publicado",
            detalle=f"{art.titulo} ({art.id})",
            nivel=contrib.nivel_ticket or "N1",
            estado="Cerrado",
            actor=ctx.usuario_email,
            visible_cliente="Sí",
        )
    log_audit(
        db,
        org_id=contrib.organizacion_id,
        actor=ctx.usuario_email,
        accion="kb_aprobacion",
        recurso=contrib.id,
        detalle=f"articulo={art.id} {art.titulo}",
    )
    org = repo.get_org_by_id(db, contrib.organizacion_id)
    return {
        "status": "ok",
        "contribucion": _contrib_out(contrib, db),
        "articulo": {
            "id": art.id,
            "titulo": art.titulo,
            "categoria": art.categoria,
            "organizacion_id": contrib.organizacion_id,
            "organizacion_slug": org.slug if org else "",
            "organizacion_nombre": org.nombre if org else "",
        },
    }


@router.post("/kb/contributions/{contrib_id}/reject")
def reject_kb_contribution(
    contrib_id: str,
    body: KBContributionReview | None = None,
    ctx: TenantContext = Depends(require_kb_reviewer),
    db: Session = Depends(get_db),
):
    admin_global = ctx.es_admin_imowi and ctx.organizacion_slug == "imowi"
    c = repo.get_kb_contribution(db, ctx.organizacion_id, contrib_id, admin_global=admin_global)
    if not c:
        raise HTTPException(404, f"Contribución {contrib_id} no encontrada")
    if c.estado != "pendiente":
        raise HTTPException(409, f"La contribución ya está {c.estado}")
    body = body or KBContributionReview()
    contrib = repo.reject_kb_contribution(
        db,
        c,
        revisado_por=ctx.usuario_email,
        motivo_revision=body.motivo_revision or "Rechazada por administrador",
    )
    if contrib.ticket_id:
        repo.add_ticket_event(
            db,
            contrib.organizacion_id,
            contrib.ticket_id,
            tipo="kb_rechazada",
            titulo="Propuesta KB rechazada",
            detalle=(contrib.motivo_revision or "")[:300],
            nivel=contrib.nivel_ticket or "N1",
            estado="Cerrado",
            actor=ctx.usuario_email,
            visible_cliente="No",
        )
    log_audit(
        db,
        org_id=contrib.organizacion_id,
        actor=ctx.usuario_email,
        accion="kb_rechazo",
        recurso=contrib.id,
        detalle=contrib.motivo_revision[:500],
    )
    return {"status": "ok", "contribucion": _contrib_out(contrib, db)}
