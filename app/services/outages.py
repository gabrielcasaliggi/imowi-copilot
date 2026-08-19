"""Incidentes masivos por NAS: matching, plantillas y generación de mensaje al cliente."""

from __future__ import annotations

import logging
import re
import time
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.domain.flujos_abonado import INTENCIONES_FACTURACION
from app.estate import repository as repo
from app.estate.models import Abonado, NetworkOutage

logger = logging.getLogger("operations_hub")

_INTENCIONES_NO_OUTAGE = INTENCIONES_FACTURACION | frozenset(
    {"aviso_deuda", "multi_tema"}
)

_TZ_AR = ZoneInfo("America/Argentina/Buenos_Aires")

# Cache corto del inventario NAS (por proceso)
_NAS_CACHE: dict[str, Any] = {"ts": 0.0, "items": []}
_NAS_CACHE_TTL_SEC = 90.0


def normalizar_nas_key(value: str) -> str:
    return (value or "").strip().casefold()


def listar_nas_radius(db: Session | None = None, *, force: bool = False) -> list[dict[str, str]]:
    """Lista NAS desde Radius (cache corto)."""
    now = time.monotonic()
    if (
        not force
        and _NAS_CACHE["items"]
        and (now - float(_NAS_CACHE["ts"])) < _NAS_CACHE_TTL_SEC
    ):
        return list(_NAS_CACHE["items"])

    from app.services.conexion_pppoe import resolve_radius_client

    client = resolve_radius_client(db)
    if client is None:
        raise RuntimeError("API Radius no configurada o deshabilitada")
    items = [n.to_dict() for n in client.get_all_nas()]
    _NAS_CACHE["ts"] = now
    _NAS_CACHE["items"] = items
    return list(items)


def health_nas(db: Session | None, shortname: str) -> dict[str, Any]:
    from app.services.conexion_pppoe import resolve_radius_client

    client = resolve_radius_client(db)
    if client is None:
        raise RuntimeError("API Radius no configurada o deshabilitada")
    status = client.rest_list_resources(shortname)
    return status.to_dict()


def _eta_validada_flag(value: str | None) -> bool:
    """Solo True si operaciones marcó la ETA como validada. Vacío = no inventar."""
    return (value or "").strip().lower() in ("sí", "si", "yes", "1", "true")


def formatear_hora_validacion(dt: datetime | None) -> str:
    """Hora local Argentina de la declaración/carga del incidente."""
    if dt is None:
        return ""
    aware = dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
    return aware.astimezone(_TZ_AR).strftime("%H:%M")


_RE_HORA_VALIDO = re.compile(
    r"(valid[oó]\s+a\s+las\s+)\d{1,2}:\d{2}",
    flags=re.IGNORECASE,
)


def _inyectar_hora_validacion(texto: str, started_at: datetime | None) -> str:
    """Reemplaza cualquier 'validó a las HH:MM' por la hora real de carga."""
    hora = formatear_hora_validacion(started_at)
    if not hora or not (texto or "").strip():
        return texto or ""
    if _RE_HORA_VALIDO.search(texto):
        return _RE_HORA_VALIDO.sub(rf"\g<1>{hora}", texto, count=1)
    # Si dice "validó" sin hora, insertarla
    low = texto.lower()
    if "validó" in low or "valido" in low:
        return re.sub(
            r"(valid[oó])(\s+por operaciones)?(\.)?",
            rf"\1 a las {hora}\3",
            texto,
            count=1,
            flags=re.IGNORECASE,
        )
    return texto


def mensaje_desde_outage(outage: NetworkOutage) -> str:
    """Plantilla determinística autorizada por operaciones (sin inventar).

    La hora de «validó a las HH:MM» sale siempre de outage.started_at
    (momento en que se cargó/declaró el incidente), nunca de un ejemplo fijo.
    """
    hora = formatear_hora_validacion(outage.started_at)
    alcance = (outage.alcance or "total").strip().lower()
    comentario = " ".join((outage.comentario or "").split()).strip()

    if alcance == "parcial":
        intro = "Detectamos una incidencia que afecta de forma parcial a tu zona."
        if comentario:
            det = comentario[:200].rstrip(".")
            intro = f"{intro} {det}."
    else:
        intro = "Detectamos una incidencia que afecta a tu zona."

    if hora:
        validacion = f"El equipo de operaciones la validó a las {hora}."
    else:
        validacion = "El equipo de operaciones la validó."

    if _eta_validada_flag(outage.eta_validada) and (outage.eta_minutos or 0) > 0:
        eta_part = (
            f"La estimación actual de restitución es de {int(outage.eta_minutos)} minutos."
        )
    else:
        eta_part = (
            "Todavía no hay una estimación de restitución confirmada; "
            "te avisamos cuando la tengamos."
        )

    cierre = (
        "Te avisaremos si cambia el estado. "
        "No es necesario generar otro reclamo."
    )
    return f"{intro} {validacion} {eta_part} {cierre}"


def mensaje_seguimiento_outage(outage: NetworkOutage) -> str:
    """Recordatorio factual mientras el incidente sigue activo."""
    hora = formatear_hora_validacion(outage.started_at)
    if hora:
        base = f"Seguimos con la incidencia validada a las {hora}."
    else:
        base = "Seguimos con la incidencia validada por operaciones."
    if _eta_validada_flag(outage.eta_validada) and (outage.eta_minutos or 0) > 0:
        eta = f" Estimación actual de restitución: {int(outage.eta_minutos)} min."
    else:
        eta = " Aún sin estimación de restitución confirmada; te avisamos ante novedades."
    individual = (
        " Si el problema parece solo en tu domicilio, decime y revisamos tu conexión."
    )
    return f"{base}{eta}{individual}"


def plantilla_mensaje_cliente(
    *,
    alcance: str,
    comentario: str,
    eta_minutos: int,
    nas_shortname: str = "",
    started_at: datetime | None = None,
    eta_validada: str = "No",
) -> str:
    """Compat tests/API: delega en mensaje_desde_outage."""
    stub = SimpleNamespaceOutage(
        alcance=alcance,
        comentario=comentario,
        eta_minutos=eta_minutos,
        eta_validada=eta_validada,
        started_at=started_at or datetime.now(UTC),
        nas_shortname=nas_shortname,
    )
    return mensaje_desde_outage(stub)  # type: ignore[arg-type]


class SimpleNamespaceOutage:
    """Stub mínimo para plantilla sin persistir."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def generar_mensaje_cliente(
    *,
    alcance: str,
    comentario: str,
    eta_minutos: int,
    nas_shortname: str = "",
    usar_ia: bool = False,
    started_at: datetime | None = None,
    eta_validada: str = "No",
) -> str:
    """Genera el texto para WhatsApp. Por defecto determinístico (no inventa)."""
    base = plantilla_mensaje_cliente(
        alcance=alcance,
        comentario=comentario,
        eta_minutos=eta_minutos,
        nas_shortname=nas_shortname,
        started_at=started_at,
        eta_validada=eta_validada,
    )
    if not usar_ia:
        return base

    comentario_n = (comentario or "").strip()
    if not comentario_n:
        return base

    hora = formatear_hora_validacion(started_at)
    eta_txt = (
        f"{eta_minutos} minutos (validada por operaciones)"
        if _eta_validada_flag(eta_validada)
        else "sin confirmar aún"
    )
    try:
        from app.llm import chat_completion

        prompt = (
            "Redactá UN mensaje breve en español rioplatense para WhatsApp. "
            "Tono calmo. NO inventes datos: usá SOLO los hechos provistos.\n"
            "Debe incluir: incidencia en la zona, que operaciones VALIDÓ el incidente "
            f"(hora {hora or 'no indicada'}), ETA ({eta_txt}), aviso de cambios, "
            "y que no hace falta otro reclamo.\n"
            "Si la ETA no está confirmada, NO menciones minutos concretos.\n"
            f"Alcance: {alcance}\n"
            f"Comentario operativo (puede resumirse): {comentario_n}\n"
        )
        text = chat_completion(
            [
                {
                    "role": "system",
                    "content": (
                        "Sos redactor de avisos operativos. Nunca inventes horarios ni ETAs."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        ).strip()
        text = " ".join(text.split())
        if len(text) < 40:
            return base
        # Guardrail: no publicar ETA inventada por el LLM
        if not _eta_validada_flag(eta_validada) and re.search(
            r"\b\d+\s*min", text, flags=re.IGNORECASE
        ):
            return base
        if "validó" not in text.lower() and "valido" not in text.lower():
            return base
        # Forzar la hora real de carga (nunca dejar HH:MM inventada por la IA)
        return _inyectar_hora_validacion(text[:900], started_at)
    except Exception:
        logger.exception("No se pudo generar mensaje_cliente con IA; uso plantilla")
        return base


def mensaje_para_conversacion(
    outage: NetworkOutage, *, ya_informado: bool
) -> str:
    """Mensaje al abonado siempre desde datos vivos del incidente.

    No reutilizar mensaje_cliente cacheado: ahí podía quedar una hora vieja o
    inventada por IA. La hora de validación = started_at (carga del incidente).
    """
    if not ya_informado:
        return mensaje_desde_outage(outage)
    return mensaje_seguimiento_outage(outage)


def resolver_nas_abonado(db: Session, abonado: Abonado | None) -> str:
    """Obtiene shortname/NAS del abonado vía Radius. Vacío si no hay dato."""
    if abonado is None:
        return ""
    dni = str(getattr(abonado, "dni", "") or "").strip()
    client_number = str(getattr(abonado, "client_number", "") or "").strip()
    if not dni and not client_number:
        return ""

    from app.services.conexion_pppoe import consultar_conexion_pppoe, resolve_radius_client

    if resolve_radius_client(db) is None:
        return ""
    try:
        estado = consultar_conexion_pppoe(dni=dni, client_number=client_number, db=db)
    except Exception:
        logger.exception("resolver_nas_abonado falló")
        return ""
    if estado.sesion and estado.sesion.nas:
        return (estado.sesion.nas or "").strip()
    return ""


def outage_activo_para_nas(
    db: Session, org_id: str, nas: str
) -> NetworkOutage | None:
    """Un solo incidente activo por NAS. Si hay varios registros, gana el match exacto."""
    key = normalizar_nas_key(nas)
    if not key:
        return None
    activos = repo.list_network_outages(db, org_id, estado="activo")
    for o in activos:
        if normalizar_nas_key(o.nas_shortname) == key:
            return o
        if o.nas_ip and normalizar_nas_key(o.nas_ip) == key:
            return o
    return None


def intencion_bloquea_outage(intencion: str) -> bool:
    return (intencion or "").strip() in _INTENCIONES_NO_OUTAGE


def buscar_outage_para_abonado(
    db: Session,
    org_id: str,
    abonado: Abonado | None,
    ctx: dict[str, Any] | None = None,
) -> tuple[NetworkOutage | None, str]:
    """Retorna (outage, nas_resuelto). Usa cache de contexto si el outage sigue activo."""
    ctx = ctx or {}
    cached_id = str(ctx.get("outage_id") or "").strip()
    cached_nas = str(ctx.get("outage_nas") or "").strip()
    if cached_id:
        o = repo.get_network_outage(db, org_id, cached_id)
        if o and o.estado == "activo":
            return o, cached_nas or o.nas_shortname

    nas = cached_nas or resolver_nas_abonado(db, abonado)
    if not nas:
        return None, ""
    o = outage_activo_para_nas(db, org_id, nas)
    return o, nas


def mensaje_ack_outage() -> str:
    return (
        "De nada. Mientras dure el incidente no hace falta que generes un reclamo. "
        "Si después de la reparación sigue fallando solo en tu casa, escribime."
    )


def mensaje_ack_outage_corto() -> str:
    return "Perfecto. Cualquier cosa me escribís."


def mensaje_resolucion_outage(outage: NetworkOutage | None = None) -> str:
    zona = ""
    if outage is not None and (outage.nas_shortname or "").strip():
        zona = " de tu zona de cobertura"
    return (
        f"El incidente{zona} ya fue resuelto por el equipo de guardia. "
        "¿Ya te anda el servicio?"
    )


def niega_servicio_ok_post_outage(texto: str) -> bool:
    """Tras '¿Ya te anda?': No / sigue mal → seguir con diagnóstico N1."""
    t = (texto or "").lower().strip()
    t = re.sub(r"[¡!.,¿?😊]+", " ", t)
    t = " ".join(t.split())
    if not t or len(t) > 80:
        return False
    if es_ack_outage(texto) and t not in ("no", "nop", "nope", "nah"):
        # "sí", "gracias", "ya anda" no son negación
        return False
    if t in {
        "no",
        "nop",
        "nope",
        "nah",
        "noo",
        "nooo",
        "sigue",
        "igual",
        "nada",
        "tampoco",
    }:
        return True
    return any(
        k in t
        for k in (
            "no anda",
            "no funciona",
            "sigue sin",
            "sigue igual",
            "sigue mal",
            "sigue el problema",
            "sigue la falla",
            "sigue fallando",
            "todavía no",
            "todavia no",
            "aún no",
            "aun no",
            "sin servicio",
            "sin internet",
            "no me anda",
            "no me funciona",
            "no volvió",
            "no volvio",
            "no recuperó",
            "no recupero",
        )
    )


def es_ack_outage(texto: str) -> bool:
    """Confirmaciones cortas tras el aviso (ok, gracias, dale…)."""
    t = (texto or "").lower().strip()
    t = re.sub(r"[¡!.,¿?😊👍✅]+", " ", t)
    t = " ".join(t.split())
    if not t or len(t) > 48:
        return False
    # Si insiste con el síntoma, no es ack
    if any(
        k in t
        for k in (
            "no anda",
            "no funciona",
            "sigue sin",
            "sin internet",
            "sin servicio",
            "no tengo",
            "sigue igual",
            "todavía no",
            "todavia no",
            "sigue la falla",
            "sigue fallando",
            "reclamo",
            "agente",
        )
    ):
        return False
    exactos = {
        "ok",
        "okay",
        "okey",
        "oka",
        "dale",
        "gracias",
        "graciass",
        "muchas gracias",
        "mil gracias",
        "listo",
        "perfecto",
        "bien",
        "bueno",
        "genial",
        "bárbaro",
        "barbaro",
        "joya",
        "copado",
        "si",
        "sí",
        "sip",
        "sep",
        "va",
        "de nada",
        "entendí",
        "entendi",
        "entendido",
        "dale gracias",
        "ok gracias",
        "okey gracias",
        "gracias ok",
        "bueno gracias",
        "bien gracias",
        "perfecto gracias",
        "listo gracias",
        "si gracias",
        "sí gracias",
        "sip gracias",
        "ya anda",
        "ya anduvo",
        "ya volvió",
        "ya volvio",
        "ya me anda",
        "me anda",
        "anda bien",
        "todo bien",
    }
    if t in exactos:
        return True
    if t.startswith("gracias") and len(t) <= 24:
        return True
    if t.startswith("ok ") and len(t) <= 20:
        return True
    parts = t.split()
    if 1 < len(parts) <= 4 and parts[-1] in ("gracias", "graciass"):
        return True
    return False


def mensaje_cierre_post_resolucion(nombre: str = "") -> str:
    nom = (nombre or "").strip()
    if nom:
        return (
            f"Me alegra {nom}. Cualquier otra consulta, no dudes en escribirme. "
            "¡Que tengas un lindo día!"
        )
    return (
        "Me alegra. Cualquier otra consulta, no dudes en escribirme. "
        "¡Que tengas un lindo día!"
    )


def pide_estado_outage(texto: str) -> bool:
    t = (texto or "").lower().strip()
    t = re.sub(r"[¡!.,¿?]+", " ", t)
    t = " ".join(t.split())
    if not t:
        return False
    return any(
        k in t
        for k in (
            "sigue el",
            "sigue la",
            "siguen con",
            "sigue la falla",
            "sigue fallando",
            "sigue el problema",
            "sigue el corte",
            "ya lo resolvieron",
            "ya está resuelto",
            "ya esta resuelto",
            "cuánto falta",
            "cuanto falta",
            "eta",
            "novedades",
            "alguna novedad",
            "ya volvió",
            "ya volvio",
            "ya anduvo",
            "ya anda",
            "siguen trabajando",
            "sigue el incidente",
        )
    )


def cliente_indica_problema_individual(texto: str) -> bool:
    """El abonado cree que la falla es solo suya (no masiva)."""
    t = (texto or "").lower()
    return any(
        k in t
        for k in (
            "solo a mi",
            "solo en mi",
            "solo mi casa",
            "solo en casa",
            "mis vecinos",
            "vecinos tienen",
            "vecinos si",
            "a los demás",
            "a los demas",
            "problema individual",
            "solo yo",
        )
    )


def outage_to_dict(o: NetworkOutage) -> dict[str, Any]:
    return {
        "id": o.id,
        "nas_shortname": o.nas_shortname,
        "nas_ip": o.nas_ip,
        "alcance": o.alcance,
        "tipo": o.tipo,
        "comentario": o.comentario,
        "mensaje_cliente": o.mensaje_cliente,
        "eta_minutos": o.eta_minutos,
        "eta_validada": o.eta_validada,
        "validado_a": formatear_hora_validacion(o.started_at),
        "nas_reachable_at_declare": o.nas_reachable_at_declare,
        "estado": o.estado,
        "fuente": o.fuente,
        "created_by": o.created_by,
        "started_at": o.started_at.isoformat() if o.started_at else "",
        "resolved_at": o.resolved_at.isoformat() if o.resolved_at else "",
        "created_at": o.created_at.isoformat() if o.created_at else "",
        "updated_at": o.updated_at.isoformat() if o.updated_at else "",
    }
