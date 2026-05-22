"""Persistencia de tickets en Supabase (PostgreSQL)."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.config import ESTADOS_TICKET_VALIDOS, supabase_configurado
from app.models import GuardarTicketInput, Ticket, TicketUpdateInput

_client = None
_TABLA = "tickets"


def _sb():
    global _client
    if _client is None:
        from supabase import create_client

        from app.config import SUPABASE_SERVICE_KEY, SUPABASE_URL

        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _client


def _ahora_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _slug_modulo(modulo: str) -> str:
    m = (modulo or "general").strip().lower()
    return re.sub(r"[^\w\-]+", "-", m.replace(" ", "-"))[:80] if m else "general"


def _row_a_dict(row: dict) -> dict:
    fecha = row.get("fecha") or ""
    if hasattr(fecha, "isoformat"):
        fecha = fecha.isoformat().replace("+00:00", "")[:19]
    else:
        fecha = str(fecha).replace("T", " ")[:19].replace(" ", "T")

    actualizacion = row.get("fecha_actualizacion") or ""
    if hasattr(actualizacion, "isoformat"):
        actualizacion = actualizacion.isoformat().replace("+00:00", "")[:19]
    elif actualizacion:
        actualizacion = str(actualizacion).replace("T", " ")[:19].replace(" ", "T")

    return {
        "id": row["id"],
        "cooperativa": row.get("cooperativa", ""),
        "modulo": row.get("modulo", ""),
        "modulo_id": row.get("modulo_id", ""),
        "linea": row.get("linea", ""),
        "dispositivo": row.get("dispositivo", ""),
        "descripcion": row.get("descripcion", ""),
        "estado": row.get("estado", "Abierto"),
        "resolucion": row.get("resolucion", ""),
        "fecha": fecha,
        "fecha_actualizacion": actualizacion,
        "tipo_caso": row.get("tipo_caso", "escalamiento"),
        "creado_por": row.get("creado_por", ""),
    }


def _a_ticket(raw: dict) -> Ticket:
    return Ticket(**raw)


def _siguiente_id() -> str:
    r = (
        _sb()
        .table(_TABLA)
        .select("id")
        .like("id", "JSC-%")
        .order("id", desc=True)
        .limit(1)
        .execute()
    )
    if r.data:
        ultimo = r.data[0]["id"]
        try:
            n = int(str(ultimo).split("-", 1)[1])
            return f"JSC-{n + 1}"
        except (ValueError, IndexError):
            pass
    return "JSC-1001"


def cargar_tickets_desde_disco() -> int:
    """Compat startup: cuenta tickets en Supabase."""
    if not supabase_configurado():
        return 0
    r = _sb().table(_TABLA).select("id", count="exact").execute()
    return r.count or len(r.data or [])


def crear_ticket(data: GuardarTicketInput, creado_por: str = "") -> Ticket:
    ticket_id = _siguiente_id()
    modulo_label = (data.modulo or "General").strip()
    row = {
        "id": ticket_id,
        "cooperativa": data.cooperativa,
        "modulo": modulo_label,
        "modulo_id": data.modulo_id or _slug_modulo(modulo_label),
        "linea": data.linea,
        "dispositivo": data.dispositivo,
        "descripcion": data.descripcion or data.falla_exacta,
        "estado": "Abierto",
        "resolucion": "",
        "tipo_caso": data.tipo_caso,
        "creado_por": creado_por,
        "fecha": _ahora_iso(),
        "fecha_actualizacion": None,
    }
    _sb().table(_TABLA).insert(row).execute()
    return _a_ticket(_row_a_dict(row))


def obtener_ticket(ticket_id: str) -> dict | None:
    r = _sb().table(_TABLA).select("*").eq("id", ticket_id).limit(1).execute()
    if not r.data:
        return None
    return _row_a_dict(r.data[0])


def listar_todos() -> list[Ticket]:
    r = _sb().table(_TABLA).select("*").order("fecha", desc=True).execute()
    return [_a_ticket(_row_a_dict(row)) for row in (r.data or [])]


def listar_por_operador(usuario: str, cooperativa_sesion: str | None = None) -> list[Ticket]:
    r = (
        _sb()
        .table(_TABLA)
        .select("*")
        .eq("creado_por", usuario)
        .order("fecha", desc=True)
        .execute()
    )
    tickets = [_a_ticket(_row_a_dict(row)) for row in (r.data or [])]
    if cooperativa_sesion and not tickets:
        coop = cooperativa_sesion.strip()
        r2 = (
            _sb()
            .table(_TABLA)
            .select("*")
            .eq("cooperativa", coop)
            .eq("creado_por", "")
            .order("fecha", desc=True)
            .execute()
        )
        tickets = [_a_ticket(_row_a_dict(row)) for row in (r2.data or [])]
    return tickets


def _aplicar_campos_contenido(ticket: dict, data: TicketUpdateInput) -> dict:
    patch: dict = {}
    if data.cooperativa is not None and data.cooperativa.strip():
        patch["cooperativa"] = data.cooperativa.strip()
    if data.linea is not None and data.linea.strip():
        patch["linea"] = data.linea.strip()
    if data.dispositivo is not None and data.dispositivo.strip():
        patch["dispositivo"] = data.dispositivo.strip()
    if data.descripcion is not None and data.descripcion.strip():
        patch["descripcion"] = data.descripcion.strip()
    if data.modulo is not None and data.modulo.strip():
        patch["modulo"] = data.modulo.strip()
    if data.modulo_id is not None and data.modulo_id.strip():
        patch["modulo_id"] = data.modulo_id.strip()
    if data.tipo_caso is not None and data.tipo_caso.strip():
        patch["tipo_caso"] = data.tipo_caso.strip()
    if patch:
        patch["fecha_actualizacion"] = _ahora_iso()
    return patch


def actualizar_ticket(ticket_id: str, data: TicketUpdateInput, solo_contenido: bool = False) -> Ticket:
    ticket = obtener_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Ticket {ticket_id} no encontrado")

    if ticket.get("estado") == "Cerrado" and solo_contenido:
        raise HTTPException(status_code=400, detail="No se puede editar un ticket cerrado")

    patch = _aplicar_campos_contenido(ticket, data)

    if not solo_contenido:
        if data.estado is not None:
            if data.estado not in ESTADOS_TICKET_VALIDOS:
                raise HTTPException(status_code=400, detail="Estado inválido")
            patch["estado"] = data.estado
        if data.resolucion is not None:
            patch["resolucion"] = data.resolucion.strip()

    if not patch:
        raise HTTPException(status_code=400, detail="No hay cambios para guardar")

    _sb().table(_TABLA).update(patch).eq("id", ticket_id).execute()
    actualizado = obtener_ticket(ticket_id)
    return _a_ticket(actualizado or ticket)


def cerrar_ticket_legacy(ticket_id: str) -> Ticket:
    return actualizar_ticket(
        ticket_id,
        TicketUpdateInput(estado="Cerrado", resolucion="Cerrado por OK del operador (flujo legacy)"),
    )
