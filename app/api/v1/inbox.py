"""Inbox de agentes — conversaciones canal abonado (Web / WhatsApp)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v1.deps import get_tenant_context
from app.api.v1.schemas import TenantContext
from app.estate import canal_repo as crepo
from app.estate.database import get_db
from app.estate.models import Abonado
from app.services.canal_abonado import procesar_mensaje_entrante
from app.services.whatsapp_client import enviar_texto

router = APIRouter(tags=["Inbox"])


class SimulateIn(BaseModel):
    telefono: str = Field(..., min_length=8, max_length=40)
    texto: str = Field(..., min_length=1, max_length=4000)
    usar_llama: bool = False


class AgentMessageIn(BaseModel):
    texto: str = Field(..., min_length=1, max_length=4000)


def _org_id(ctx: TenantContext) -> str:
    return ctx.organizacion_id


@router.get("/inbox/conversations")
def list_inbox(
    estado: str = "",
    mias: bool = False,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    agente = ctx.usuario_email if mias else ""
    rows = crepo.list_conversaciones(db, _org_id(ctx), estado=estado, agente_id=agente)
    out = []
    for c in rows:
        abo = db.get(Abonado, c.abonado_id) if c.abonado_id else None
        out.append(crepo.conversacion_to_dict(c, abonado=abo))

    # Clientes / prioridad alta primero; visitantes (cola baja) al final
    def _es_baja(item: dict) -> bool:
        return bool(item.get("es_visitante") or item.get("cola_prioridad") == "baja")

    alta = [d for d in out if not _es_baja(d)]
    baja = [d for d in out if _es_baja(d)]
    alta.sort(key=lambda d: d.get("updated_at") or "", reverse=True)
    baja.sort(key=lambda d: d.get("updated_at") or "", reverse=True)
    return {"tenant": ctx.organizacion_slug, "conversaciones": alta + baja}


@router.get("/inbox/conversations/{conv_id}")
def get_inbox_conversation(
    conv_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    c = crepo.get_conversacion(db, _org_id(ctx), conv_id)
    if not c:
        raise HTTPException(404, "Conversación no encontrada")
    abo = db.get(Abonado, c.abonado_id) if c.abonado_id else None
    mensajes = [crepo.mensaje_to_dict(m) for m in crepo.list_mensajes(db, c.id)]
    return {
        "tenant": ctx.organizacion_slug,
        "conversacion": crepo.conversacion_to_dict(c, abonado=abo),
        "mensajes": mensajes,
    }


@router.post("/inbox/conversations/{conv_id}/claim")
def claim_conversation(
    conv_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    c = crepo.get_conversacion(db, _org_id(ctx), conv_id)
    if not c:
        raise HTTPException(404, "Conversación no encontrada")
    if c.estado == "cerrado":
        raise HTTPException(400, "La conversación está cerrada")
    if c.estado == "con_agente" and c.agente_id and c.agente_id != ctx.usuario_email:
        raise HTTPException(409, f"Ya tomada por {c.agente_id}")
    c.estado = "con_agente"
    c.agente_id = ctx.usuario_email
    db.commit()
    db.refresh(c)
    crepo.add_mensaje(
        db,
        _org_id(ctx),
        c.id,
        direccion="out",
        autor="agente",
        texto=f"[Sistema] Agente {ctx.usuario_nombre} tomó el caso.",
    )
    abo = db.get(Abonado, c.abonado_id) if c.abonado_id else None
    return {
        "status": "ok",
        "conversacion": crepo.conversacion_to_dict(c, abonado=abo),
    }


@router.post("/inbox/conversations/{conv_id}/release")
def release_conversation(
    conv_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    c = crepo.get_conversacion(db, _org_id(ctx), conv_id)
    if not c:
        raise HTTPException(404, "Conversación no encontrada")
    c.estado = "espera_agente" if c.ticket_id else "bot"
    c.agente_id = ""
    db.commit()
    return {"status": "ok", "conversacion": crepo.conversacion_to_dict(c)}


@router.post("/inbox/conversations/{conv_id}/messages")
def agent_send_message(
    conv_id: str,
    body: AgentMessageIn,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    c = crepo.get_conversacion(db, _org_id(ctx), conv_id)
    if not c:
        raise HTTPException(404, "Conversación no encontrada")
    if c.estado not in ("con_agente", "espera_agente", "bot"):
        raise HTTPException(400, "Tomá el caso antes de responder")
    if c.estado != "con_agente":
        c.estado = "con_agente"
        c.agente_id = ctx.usuario_email
        db.commit()
    texto = body.texto.strip()
    m = crepo.add_mensaje(
        db,
        _org_id(ctx),
        c.id,
        direccion="out",
        autor="agente",
        texto=texto,
    )
    wa = enviar_texto(c.telefono, texto) if c.canal == "whatsapp" else {"ok": True, "simulated": True}
    if wa.get("meta_message_id"):
        m.meta_message_id = wa["meta_message_id"]
        db.commit()
    return {"status": "ok", "mensaje": crepo.mensaje_to_dict(m), "whatsapp": wa}


@router.post("/inbox/conversations/{conv_id}/close")
def close_conversation(
    conv_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    c = crepo.get_conversacion(db, _org_id(ctx), conv_id)
    if not c:
        raise HTTPException(404, "Conversación no encontrada")
    c.estado = "cerrado"
    db.commit()
    crepo.add_mensaje(
        db,
        _org_id(ctx),
        c.id,
        direccion="out",
        autor="agente",
        texto="[Sistema] Conversación cerrada por el agente.",
    )
    return {"status": "ok", "conversacion": crepo.conversacion_to_dict(c)}


class AssignIn(BaseModel):
    agente_id: str = Field(..., min_length=1)
    agente_nombre: str = Field(default="")


@router.post("/inbox/conversations/{conv_id}/assign")
def assign_conversation(
    conv_id: str,
    body: AssignIn,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Reasigna un hilo a un agente (solo admin)."""
    if not ctx.es_admin_imowi:
        raise HTTPException(403, "Solo administración puede reasignar conversaciones")
    c = crepo.get_conversacion(db, _org_id(ctx), conv_id)
    if not c:
        raise HTTPException(404, "Conversación no encontrada")
    if c.estado == "cerrado":
        raise HTTPException(400, "La conversación está cerrada")
    c.estado = "con_agente"
    c.agente_id = body.agente_id.strip()
    db.commit()
    nombre = body.agente_nombre.strip() or body.agente_id
    crepo.add_mensaje(
        db,
        _org_id(ctx),
        c.id,
        direccion="out",
        autor="agente",
        texto=f"[Sistema] Conversación asignada a {nombre}.",
    )
    return {"status": "ok", "conversacion": crepo.conversacion_to_dict(c)}


@router.post("/inbox/simulate")
def simulate_inbound(
    body: SimulateIn,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Inyecta un mensaje entrante (solo admin plataforma · sin Meta)."""
    if not ctx.es_admin_imowi:
        raise HTTPException(403, "Solo administración puede inyectar entradas de canal")
    result = procesar_mensaje_entrante(
        db,
        _org_id(ctx),
        telefono=body.telefono,
        texto=body.texto,
        canal="whatsapp",
        usar_llama=body.usar_llama,
    )
    return {"tenant": ctx.organizacion_slug, **result}


@router.get("/inbox/abonados")
def list_abonados_inbox(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    rows = crepo.list_abonados(db, _org_id(ctx))
    return {"tenant": ctx.organizacion_slug, "abonados": [crepo.abonado_to_dict(a) for a in rows]}
