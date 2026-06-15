"""Puente de tickets: Data Estate local + Supabase (JSC) cuando está configurado."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.config import es_mirror_supabase_activo
from app.estate import repository as repo
from app.estate.models import Ticket

logger = logging.getLogger("imowi")


def _cooperativa_nombre(db: Session, org_id: str) -> str:
    org = repo.get_org_by_id(db, org_id)
    return org.nombre if org else ""


def crear_ticket(
    db: Session,
    org_id: str,
    *,
    linea: str,
    dispositivo: str,
    descripcion_falla: str,
    origen: str,
    categoria: str = "General",
    intent_ejecutado: str = "",
    creado_por: str = "",
    nivel: str = "N1",
    destino: str = "cooperativa",
    proveedor: str = "",
    motivo_escalamiento: str = "",
    evidencia: str = "",
    acciones_n1_realizadas: str = "",
    estado_sla: str = "Pendiente",
    ticket_externo_id: str = "",
    regla_clasificacion: str = "",
) -> Ticket:
    t = repo.create_ticket(
        db,
        org_id,
        linea=linea,
        dispositivo=dispositivo,
        descripcion_falla=descripcion_falla,
        origen=origen,
        categoria=categoria,
        intent_ejecutado=intent_ejecutado,
        creado_por=creado_por,
        nivel=nivel,
        destino=destino,
        proveedor=proveedor,
        motivo_escalamiento=motivo_escalamiento,
        evidencia=evidencia,
        acciones_n1_realizadas=acciones_n1_realizadas,
        estado_sla=estado_sla,
        ticket_externo_id=ticket_externo_id,
        regla_clasificacion=regla_clasificacion,
    )
    if es_mirror_supabase_activo():
        try:
            from app.models import GuardarTicketInput
            from app import tickets_supabase as sb

            coop = _cooperativa_nombre(db, org_id)
            sb.crear_ticket(
                GuardarTicketInput(
                    cooperativa=coop,
                    modulo=categoria,
                    modulo_id=categoria.lower().replace(" ", "-"),
                    linea=linea,
                    dispositivo=dispositivo,
                    descripcion=descripcion_falla,
                    falla_exacta=descripcion_falla,
                    tipo_caso="autonomo" if origen == "Autónomo Predictivo" else "escalamiento",
                ),
                creado_por=creado_por,
            )
        except Exception as e:
            logger.warning("Supabase ticket mirror falló: %s", e)
    return t


def listar_tickets(db: Session, org_id: str, *, admin_global: bool = False) -> list[Ticket]:
    if admin_global:
        return repo.list_tickets_all(db)
    return repo.list_tickets(db, org_id)
