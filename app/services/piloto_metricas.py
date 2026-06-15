"""Telemetría mínima del piloto operativo imowi."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.estate import repository as repo

TIPOS_EVENTO = frozenset({
    "escenario_iniciado",
    "paso_confirmado",
    "ticket_creado",
    "reset_demo",
    "turno_chat",
})


def registrar_evento_piloto(
    db: Session,
    org_id: str,
    tipo: str,
    *,
    session_id: str = "",
    escenario_id: str = "",
    categoria: str = "",
    paso_id: str = "",
    ticket_id: str = "",
    actor: str = "",
    detalle: dict | None = None,
) -> dict:
    if tipo not in TIPOS_EVENTO:
        tipo = "turno_chat"
    return repo.add_pilot_event(
        db,
        org_id,
        tipo,
        session_id=session_id,
        escenario_id=escenario_id,
        categoria=categoria,
        paso_id=paso_id,
        ticket_id=ticket_id,
        actor=actor,
        detalle=detalle or {},
    )


def registrar_turno_piloto(
    db: Session,
    org_id: str,
    *,
    session_id: str,
    actor: str,
    pasos_nuevos: list[str],
    flujo_operativo: dict | None,
    ticket_id: str = "",
    ticket_nuevo: bool = False,
) -> None:
    categoria = (flujo_operativo or {}).get("categoria", "")
    for paso_id in pasos_nuevos:
        registrar_evento_piloto(
            db,
            org_id,
            "paso_confirmado",
            session_id=session_id,
            categoria=categoria,
            paso_id=paso_id,
            ticket_id=ticket_id,
            actor=actor,
        )
    if ticket_nuevo and ticket_id:
        registrar_evento_piloto(
            db,
            org_id,
            "ticket_creado",
            session_id=session_id,
            categoria=categoria,
            ticket_id=ticket_id,
            actor=actor,
            detalle={"origen": "escalamiento_noc"},
        )


def resumen_metricas_piloto(db: Session, org_id: str) -> dict[str, Any]:
    return repo.resumen_pilot_events(db, org_id)
