"""Estados del caso conversacional cooperativa."""

from __future__ import annotations

import re
from enum import Enum


class EstadoConversacion(str, Enum):
    NUEVO_RECLAMO = "nuevo_reclamo"
    RECOLECTANDO_DATOS = "recolectando_datos"
    BUSCANDO_KB = "buscando_kb"
    GUIANDO_RESOLUCION = "guiando_resolucion"
    ESPERANDO_CONFIRMACION = "esperando_confirmacion"
    TICKET_CREADO = "ticket_creado"
    CERRADO_RESUELTO = "cerrado_resuelto"


class AccionOperador(str, Enum):
    CONFIRMAR_TICKET = "confirmar_ticket"
    CASO_RESUELTO = "caso_resuelto"
    CONTINUAR_KB = "continuar_kb"
    NUEVO_RECLAMO = "nuevo_reclamo"
    CANCELAR = "cancelar"


class IntencionPendiente(str, Enum):
    NINGUNA = ""
    CONFIRMAR_TICKET = "confirmar_ticket"
    CONFIRMAR_RESOLUCION = "confirmar_resolucion"
    CONTINUAR_KB = "continuar_kb"


class PolaridadMensaje(str, Enum):
    AFIRMACION = "afirmacion"
    NEGACION = "negacion"
    PERSISTENCIA = "persistencia"
    RESUELTO = "resuelto"
    AMBIGUO = "ambiguo"


ESTADOS_CASO_CERRADO = {EstadoConversacion.CERRADO_RESUELTO.value}

CONFIRMACION_RESOLUCION = (
    "ok",
    "listo",
    "confirmado",
    "resuelto",
    "solucionado",
    "solucionó",
    "quedo resuelto",
    "quedó resuelto",
    "problema resuelto",
    "ya funciona",
    "funciona bien",
    "caso cerrado",
    "podemos cerrar",
    "gracias ya anda",
    "ya anda",
)

CONFIRMACION_TICKET = (
    "sí",
    "si",
    "confirmo",
    "confirmado",
    "dale",
    "de acuerdo",
    "ok registrar",
    "registralo",
    "regístralo",
    "generá el ticket",
    "genera el ticket",
    "creá el ticket",
    "crea el ticket",
    "hacelo",
    "adelante",
)

PERSISTENCIA_FRASES = (
    "sigue",
    "persiste",
    "no funciona",
    "no anda",
    "no sirvió",
    "no sirvio",
    "todavía",
    "todavia",
    "aún",
    "aun",
    "mismo problema",
    "sigue igual",
)

NEGACION_CORTA = ("no", "nop", "nope", "no.", "nah", "negativo")

AFIRMACION_CORTA = (
    "sí",
    "si",
    "sip",
    "dale",
    "ok",
    "okay",
    "confirmo",
    "de acuerdo",
    "correcto",
    "exacto",
    "hacelo",
    "adelante",
)


def _ultimo_mensaje_usuario(historial: list[dict]) -> str:
    for m in reversed(historial):
        if m.get("rol") == "usuario":
            return (m.get("contenido") or "").lower().strip()
    return ""


def clasificar_polaridad(historial: list[dict], intencion_pendiente: str = "") -> PolaridadMensaje:
    """Clasifica el último mensaje del operador sin depender solo de frases literales."""
    msg = _ultimo_mensaje_usuario(historial)
    if not msg:
        return PolaridadMensaje.AMBIGUO

    if msg in NEGACION_CORTA:
        return PolaridadMensaje.NEGACION

    if any(frase in msg for frase in PERSISTENCIA_FRASES):
        return PolaridadMensaje.PERSISTENCIA

    if any(frase in msg for frase in CONFIRMACION_RESOLUCION):
        return PolaridadMensaje.RESUELTO

    if intencion_pendiente == IntencionPendiente.CONFIRMAR_TICKET.value:
        if msg in AFIRMACION_CORTA or any(f in msg for f in CONFIRMACION_TICKET):
            return PolaridadMensaje.AFIRMACION
        if msg in NEGACION_CORTA:
            return PolaridadMensaje.NEGACION

    if intencion_pendiente == IntencionPendiente.CONFIRMAR_RESOLUCION.value:
        if msg in AFIRMACION_CORTA or any(f in msg for f in CONFIRMACION_RESOLUCION):
            return PolaridadMensaje.RESUELTO
        if any(f in msg for f in PERSISTENCIA_FRASES):
            return PolaridadMensaje.PERSISTENCIA

    if msg in AFIRMACION_CORTA:
        return PolaridadMensaje.AFIRMACION

    return PolaridadMensaje.AMBIGUO


def interpretar_accion_operador(accion: str | None) -> AccionOperador | None:
    if not accion:
        return None
    try:
        return AccionOperador(accion)
    except ValueError:
        return None


def usuario_confirmo_ticket(historial: list[dict], intencion_pendiente: str = "") -> bool:
    polaridad = clasificar_polaridad(historial, intencion_pendiente)
    if polaridad == PolaridadMensaje.AFIRMACION:
        return True
    ultimo = _ultimo_mensaje_usuario(historial)

    for frase in CONFIRMACION_TICKET:
        if len(frase) <= 3:
            if re.search(rf"\b{re.escape(frase)}\b", ultimo):
                return True
        elif frase in ultimo:
            return True
    return False


def usuario_confirmo_resolucion(historial: list[dict], intencion_pendiente: str = "") -> bool:
    polaridad = clasificar_polaridad(historial, intencion_pendiente)
    if polaridad == PolaridadMensaje.RESUELTO:
        return True
    if polaridad in (PolaridadMensaje.NEGACION, PolaridadMensaje.PERSISTENCIA):
        return False
    mensajes = [m.get("contenido", "").lower().strip() for m in historial if m.get("rol") == "usuario"]
    if not mensajes:
        return False
    for msg in reversed(mensajes[-3:]):
        if msg in NEGACION_CORTA:
            return False
        if msg in ("gracias", "muchas gracias", "de nada", "chau", "adiós", "adios"):
            return False
        if any(frase in msg for frase in CONFIRMACION_RESOLUCION):
            return True
    return False
