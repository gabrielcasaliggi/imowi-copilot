"""Persistencia en memoria de tickets."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.config import ESTADOS_TICKET_VALIDOS, supabase_configurado
from app.models import GuardarTicketInput, Ticket, TicketUpdateInput
from app.persistencia import escribir_json, leer_json

_db: list[dict] = []
_contador = 1000
_TICKETS_FILE = "tickets.json"


def _sb():
    from app import tickets_supabase

    return tickets_supabase


def cargar_tickets_desde_disco() -> int:
    """Restaura tickets tras reinicio (JSON local) o cuenta filas (Supabase)."""
    if supabase_configurado():
        return _sb().cargar_tickets_desde_disco()
    global _db, _contador
    raw = leer_json(_TICKETS_FILE, {})
    if not isinstance(raw, dict):
        return 0
    tickets = raw.get("tickets")
    if isinstance(tickets, list):
        _db = [t for t in tickets if isinstance(t, dict) and t.get("id")]
    contador = raw.get("contador")
    if isinstance(contador, int) and contador >= 1000:
        _contador = contador
    elif _db:
        nums = []
        for t in _db:
            tid = str(t.get("id", ""))
            if tid.startswith("JSC-"):
                try:
                    nums.append(int(tid.split("-", 1)[1]))
                except ValueError:
                    pass
        _contador = max(nums) if nums else 1000
    return len(_db)


def _guardar_tickets() -> None:
    escribir_json(_TICKETS_FILE, {"contador": _contador, "tickets": _db})


def _ahora_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _slug_modulo(modulo: str) -> str:
    m = (modulo or "general").strip().lower()
    return re.sub(r"[^\w\-]+", "-", m.replace(" ", "-"))[:80] if m else "general"


def _a_ticket(raw: dict) -> Ticket:
    return Ticket(**raw)


def crear_ticket(data: GuardarTicketInput, creado_por: str = "") -> Ticket:
    if supabase_configurado():
        return _sb().crear_ticket(data, creado_por)
    global _contador
    _contador += 1
    modulo_label = (data.modulo or "General").strip()
    modulo_id = data.modulo_id or _slug_modulo(modulo_label)
    descripcion = data.descripcion or data.falla_exacta
    ticket = {
        "id": f"JSC-{_contador}",
        "cooperativa": data.cooperativa,
        "modulo": modulo_label,
        "modulo_id": modulo_id,
        "linea": data.linea,
        "dispositivo": data.dispositivo,
        "descripcion": descripcion,
        "estado": "Abierto",
        "resolucion": "",
        "fecha": _ahora_iso(),
        "fecha_actualizacion": "",
        "tipo_caso": data.tipo_caso,
        "creado_por": creado_por,
    }
    _db.append(ticket)
    _guardar_tickets()
    return _a_ticket(ticket)


def obtener_ticket(ticket_id: str) -> dict | None:
    if supabase_configurado():
        return _sb().obtener_ticket(ticket_id)
    return next((t for t in _db if t["id"] == ticket_id), None)


def listar_todos() -> list[Ticket]:
    if supabase_configurado():
        return _sb().listar_todos()
    return [_a_ticket(t) for t in reversed(_db)]


def listar_por_cooperativa(cooperativa: str) -> list[Ticket]:
    coop = cooperativa.strip().lower()
    filtrados = [t for t in _db if t["cooperativa"].strip().lower() == coop]
    return [_a_ticket(t) for t in reversed(filtrados)]


def listar_por_operador(usuario: str, cooperativa_sesion: str | None = None) -> list[Ticket]:
    """Tickets creados por este operador (aunque el cliente sea otra cooperativa)."""
    if supabase_configurado():
        return _sb().listar_por_operador(usuario, cooperativa_sesion)
    user = usuario.strip().lower()
    vistos: set[str] = set()
    filtrados: list[dict] = []
    for t in reversed(_db):
        if t.get("creado_por", "").strip().lower() == user:
            filtrados.append(t)
            vistos.add(t["id"])
    # Compat: tickets viejos sin creado_por (sesión perdida al crear)
    if cooperativa_sesion:
        coop = cooperativa_sesion.strip().lower()
        for t in reversed(_db):
            if t["id"] in vistos:
                continue
            if not t.get("creado_por", "").strip() and t["cooperativa"].strip().lower() == coop:
                filtrados.append(t)
                vistos.add(t["id"])
    return [_a_ticket(t) for t in filtrados]


def _aplicar_campos_contenido(ticket: dict, data: TicketUpdateInput) -> bool:
    cambio = False
    if data.cooperativa is not None and data.cooperativa.strip():
        ticket["cooperativa"] = data.cooperativa.strip()
        cambio = True
    if data.linea is not None and data.linea.strip():
        ticket["linea"] = data.linea.strip()
        cambio = True
    if data.dispositivo is not None and data.dispositivo.strip():
        ticket["dispositivo"] = data.dispositivo.strip()
        cambio = True
    if data.descripcion is not None and data.descripcion.strip():
        ticket["descripcion"] = data.descripcion.strip()
        cambio = True
    if data.modulo is not None and data.modulo.strip():
        ticket["modulo"] = data.modulo.strip()
        cambio = True
    if data.modulo_id is not None and data.modulo_id.strip():
        ticket["modulo_id"] = data.modulo_id.strip()
        cambio = True
    if data.tipo_caso is not None and data.tipo_caso.strip():
        ticket["tipo_caso"] = data.tipo_caso.strip()
        cambio = True
    if cambio:
        ticket["fecha_actualizacion"] = _ahora_iso()
    return cambio


def actualizar_ticket(ticket_id: str, data: TicketUpdateInput, solo_contenido: bool = False) -> Ticket:
    if supabase_configurado():
        return _sb().actualizar_ticket(ticket_id, data, solo_contenido)
    ticket = obtener_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Ticket {ticket_id} no encontrado")

    if ticket.get("estado") == "Cerrado" and solo_contenido:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede editar un ticket cerrado",
        )

    cambio = _aplicar_campos_contenido(ticket, data)

    if not solo_contenido:
        if data.estado is not None:
            if data.estado not in ESTADOS_TICKET_VALIDOS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Estado inválido. Use: {', '.join(ESTADOS_TICKET_VALIDOS)}",
                )
            ticket["estado"] = data.estado
            cambio = True

        if data.resolucion is not None:
            ticket["resolucion"] = data.resolucion.strip()
            cambio = True

    if not cambio:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No hay cambios para guardar",
        )

    _guardar_tickets()
    return _a_ticket(ticket)


def cerrar_ticket_legacy(ticket_id: str) -> Ticket:
    if supabase_configurado():
        return _sb().cerrar_ticket_legacy(ticket_id)
    return actualizar_ticket(
        ticket_id,
        TicketUpdateInput(estado="Cerrado", resolucion="Cerrado por OK del operador (flujo legacy)"),
    )
