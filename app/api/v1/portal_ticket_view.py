"""Vista del ticket para el abonado (portal web y app). Sin base de datos.

Los TicketEvent guardan títulos y detalles escritos para agentes (nivel, destino, proveedor,
regla, asignado_a, fechas crudas). El abonado nunca ve ese texto: cada evento permitido se
proyecta a un título fijo y solo las notas conservan su texto.

Dos capas, en orden:
1. ``is_portal_customer_event`` (2.6E): flag visible_cliente + tipos de cliente.
2. Lista blanca de esta vista: tipo → título fijo; cualquier otro tipo se descarta.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from typing import Any

from app.services.eko_ticket_proactive import (
    is_portal_customer_event,
    is_self_note_actor,
    sanitize_customer_note_message,
)

TITULO_CREACION = "Recibimos tu reclamo"
TITULO_CIERRE = "Tu reclamo se cerró"
TITULO_DEMORA = "Tu reclamo está demorando más de lo previsto"
TITULO_NOTA_EQUIPO = "Novedad del equipo"
TITULO_NOTA_PROPIA = "Tu comentario"


def _texto(valor: Any) -> str:
    return str(valor or "").strip()


def _iso(valor: Any) -> str:
    return valor.isoformat() if valor else ""


def evento_cliente(ev: Any) -> dict[str, str] | None:
    """Evento visible para el abonado, o None si no pasa la lista blanca.

    Claves iguales a las que ya consumen la app y el portal: id, titulo, detalle,
    estado, created_at. ``detalle`` es "" salvo en las notas.
    """
    if not is_portal_customer_event(ev):
        return None
    tipo = _texto(getattr(ev, "tipo", "")).lower()
    estado = _texto(getattr(ev, "estado", ""))
    detalle = ""
    if tipo == "creacion":
        titulo = TITULO_CREACION
    elif tipo == "actualizacion" and estado == "Cerrado":
        titulo = TITULO_CIERRE
    elif tipo == "sla_breach":
        titulo = TITULO_DEMORA
    elif tipo == "nota":
        detalle = sanitize_customer_note_message(getattr(ev, "detalle", ""))
        if not detalle:
            return None
        propia = is_self_note_actor(getattr(ev, "actor", ""))
        titulo = TITULO_NOTA_PROPIA if propia else TITULO_NOTA_EQUIPO
    else:
        return None
    return {
        "id": _texto(getattr(ev, "id", "")),
        "titulo": titulo,
        "detalle": detalle,
        "estado": estado,
        "created_at": _iso(getattr(ev, "created_at", None)),
    }


def eventos_cliente(eventos: Iterable[Any]) -> list[dict[str, str]]:
    """Proyección en el mismo orden de entrada, sin los eventos descartados."""
    out: list[dict[str, str]] = []
    for ev in eventos:
        item = evento_cliente(ev)
        if item is not None:
            out.append(item)
    return out


def ultimo_movimiento(eventos: Iterable[Any]) -> dict[str, str] | None:
    """Último evento visible (eventos en orden cronológico), con la misma proyección."""
    visibles = eventos_cliente(eventos)
    if not visibles:
        return None
    ultimo = visibles[-1]
    return {"titulo": ultimo["titulo"], "created_at": ultimo["created_at"]}


# --- Título legible del ticket ---

TITULO_GENERICO = "Reclamo"

# Clave = categoría normalizada (ver normalizar_categoria). Las categorías de Eko salen de
# la intención ("movil_llamadas" → "Movil Llamadas"); las de consola, de la taxonomía.
TITULOS_CATEGORIA: dict[str, str] = {
    "movil_llamadas": "Llamadas en tu línea móvil",
    "movil_datos": "Datos móviles",
    "corte_deuda": "Consulta por corte del servicio",
    "internet_lento": "Internet lento",
    "facturacion_reclamo": "Reclamo de factura",
    "voz": "Llamadas",
    "apn_/_datos": "Datos móviles",
}

# creado_por del POST /portal/tickets: el abonado escribió el motivo. No alcanza con
# `origen`: Eko también marca "Portal" en las derivaciones desde el chat web.
_PREFIJO_RECLAMO_ABONADO = "portal:"


def normalizar_categoria(raw: Any) -> str:
    """Minúsculas, sin tildes, espacios a "_": "Móvil  Llamadas" → "movil_llamadas"."""
    sin_tildes = unicodedata.normalize("NFKD", _texto(raw).lower())
    base = "".join(c for c in sin_tildes if not unicodedata.combining(c))
    return "_".join(base.split())


def es_reclamo_del_abonado(ticket: Any) -> bool:
    return _texto(getattr(ticket, "creado_por", "")).startswith(_PREFIJO_RECLAMO_ABONADO)


def titulo_ticket(ticket: Any) -> str:
    """Motivo tal cual si lo escribió el abonado; si no, etiqueta del mapa o "Reclamo"."""
    categoria = _texto(getattr(ticket, "categoria", ""))
    if es_reclamo_del_abonado(ticket):
        return categoria or TITULO_GENERICO
    return TITULOS_CATEGORIA.get(normalizar_categoria(categoria), TITULO_GENERICO)
