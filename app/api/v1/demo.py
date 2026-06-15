"""API modo demo validación — escenarios, reset y métricas de piloto."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v1.deps import get_tenant_context
from app.api.v1.schemas import TenantContext
from app.domain.demo_validacion import CHECKLIST_GENERAL_IMOWI, listar_escenarios_demo, obtener_escenario_demo
from app.estate import repository as repo
from app.estate.database import get_db
from app.services import piloto_metricas

router = APIRouter(prefix="/demo", tags=["demo"])


class DemoResetRequest(BaseModel):
    incluir_tickets: bool = True


class DemoEventoRequest(BaseModel):
    tipo: str = "escenario_iniciado"
    session_id: str = ""
    escenario_id: str = ""
    categoria: str = ""
    paso_id: str = ""
    ticket_id: str = ""
    detalle: dict = Field(default_factory=dict)


@router.get("/escenarios")
def get_escenarios_demo(
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Escenarios precargados para sesión de validación con imowi."""
    return {
        "tenant": ctx.organizacion_slug,
        "escenarios": listar_escenarios_demo(),
        "checklist_general": CHECKLIST_GENERAL_IMOWI,
    }


@router.get("/escenarios/{escenario_id}")
def get_escenario_demo(
    escenario_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    esc = obtener_escenario_demo(escenario_id)
    if not esc:
        raise HTTPException(404, f"Escenario '{escenario_id}' no encontrado")
    return {"tenant": ctx.organizacion_slug, "escenario": esc}


@router.get("/metricas")
def get_metricas_piloto(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Resumen de eventos del piloto operativo para revisión con imowi."""
    return {
        "tenant": ctx.organizacion_slug,
        "metricas": piloto_metricas.resumen_metricas_piloto(db, ctx.organizacion_id),
    }


@router.post("/evento")
def registrar_evento_piloto(
    body: DemoEventoRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Registra evento de piloto (escenario iniciado, etc.)."""
    evento = piloto_metricas.registrar_evento_piloto(
        db,
        ctx.organizacion_id,
        body.tipo,
        session_id=body.session_id,
        escenario_id=body.escenario_id,
        categoria=body.categoria,
        paso_id=body.paso_id,
        ticket_id=body.ticket_id,
        actor=ctx.usuario_email,
        detalle=body.detalle,
    )
    return {"status": "ok", "tenant": ctx.organizacion_slug, "evento": evento}


@router.post("/reset")
def reset_demo_validacion(
    body: DemoResetRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Limpia casos conversacionales y tickets de la cooperativa para reintentar escenarios."""
    resultado = repo.reset_demo_validacion(
        db,
        ctx.organizacion_id,
        incluir_tickets=body.incluir_tickets,
    )
    piloto_metricas.registrar_evento_piloto(
        db,
        ctx.organizacion_id,
        "reset_demo",
        actor=ctx.usuario_email,
        detalle={
            "casos_eliminados": resultado.get("casos_eliminados", 0),
            "tickets_eliminados": resultado.get("tickets_eliminados", 0),
        },
    )
    return {
        "status": "ok",
        "tenant": ctx.organizacion_slug,
        **resultado,
    }
