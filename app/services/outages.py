"""Incidentes masivos por NAS: matching, plantillas y generación de mensaje al cliente."""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from sqlalchemy.orm import Session

from app.estate import repository as repo
from app.estate.models import Abonado, NetworkOutage

logger = logging.getLogger("operations_hub")

_INTENCIONES_NO_OUTAGE = frozenset(
    {"facturacion", "corte_deuda", "aviso_deuda", "multi_tema"}
)

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


def plantilla_mensaje_cliente(
    *,
    alcance: str,
    comentario: str,
    eta_minutos: int,
    nas_shortname: str = "",
) -> str:
    """Fallback determinístico (sin LLM)."""
    eta = max(1, int(eta_minutos or 45))
    comentario_n = " ".join((comentario or "").split()).strip()
    alcance_n = (alcance or "total").strip().lower()
    zona = nas_shortname.strip() or "tu zona de cobertura"

    if alcance_n == "parcial":
        base = (
            f"Detectamos un inconveniente técnico en un sector de la cobertura "
            f"asociada a tu nodo ({zona})."
        )
    else:
        base = (
            f"Detectamos un inconveniente técnico masivo en la zona de cobertura "
            f"de tu nodo ({zona})."
        )

    detalle = ""
    if comentario_n:
        # Resumen corto y seguro para el abonado
        detalle = f" Detalle operativo: {comentario_n[:220]}"
        if not detalle.endswith("."):
            detalle += "."

    return (
        f"{base}{detalle} "
        f"El equipo de guardia ya se encuentra trabajando en el lugar. "
        f"Tiempo estimado de solución: {eta} min. "
        "No es necesario que generes un reclamo."
    )


def generar_mensaje_cliente(
    *,
    alcance: str,
    comentario: str,
    eta_minutos: int,
    nas_shortname: str = "",
    usar_ia: bool = True,
) -> str:
    """Genera una vez el texto para WhatsApp; fallback a plantilla si falla la IA."""
    fallback = plantilla_mensaje_cliente(
        alcance=alcance,
        comentario=comentario,
        eta_minutos=eta_minutos,
        nas_shortname=nas_shortname,
    )
    if not usar_ia:
        return fallback

    comentario_n = (comentario or "").strip()
    if not comentario_n:
        return fallback

    try:
        from app.llm import chat_completion

        prompt = (
            "Redactá UN solo mensaje breve en español rioplatense para un abonado de ISP "
            "por WhatsApp. Tono calmo y claro. Sin saludos largos, sin emojis, sin prometer "
            "cosas no dichas. Incluí: qué tipo de inconveniente (masivo o parcial según alcance), "
            "que la guardia ya trabaja, ETA en minutos, y que NO hace falta generar reclamo. "
            "Si el comentario indica alcance parcial (rama de fibra, calle, NAP), dejalo claro "
            "sin datos internos técnicos innecesarios.\n\n"
            f"NAS: {nas_shortname or 'desconocido'}\n"
            f"Alcance: {alcance}\n"
            f"ETA minutos: {eta_minutos}\n"
            f"Comentario del agente: {comentario_n}\n"
        )
        text = chat_completion(
            [
                {
                    "role": "system",
                    "content": "Sos redactor de avisos operativos de un ISP cooperativo.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        ).strip()
        # Una sola línea/párrafo razonable
        text = " ".join(text.split())
        if len(text) < 40:
            return fallback
        return text[:900]
    except Exception:
        logger.exception("No se pudo generar mensaje_cliente con IA; uso plantilla")
        return fallback


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


def mensaje_para_conversacion(
    outage: NetworkOutage, *, ya_informado: bool
) -> str:
    base = (outage.mensaje_cliente or "").strip()
    if not base:
        base = plantilla_mensaje_cliente(
            alcance=outage.alcance,
            comentario=outage.comentario,
            eta_minutos=outage.eta_minutos,
            nas_shortname=outage.nas_shortname,
        )
    if not ya_informado:
        return base
    eta = outage.eta_minutos or 45
    return (
        f"El equipo de guardia sigue trabajando en el inconveniente de tu zona. "
        f"ETA aproximado: {eta} min. No hace falta generar un reclamo; "
        "si el servicio vuelve, avisame."
    )


def mensaje_ack_outage() -> str:
    return (
        "De nada. Mientras dure el incidente no hace falta que generes un reclamo. "
        "Si después de la reparación sigue fallando, escribime."
    )


def mensaje_ack_outage_corto() -> str:
    return "Perfecto. Cualquier cosa me escribís."


def mensaje_resolucion_outage(outage: NetworkOutage | None = None) -> str:
    zona = ""
    if outage is not None and (outage.nas_shortname or "").strip():
        # Nombre legible sin exponer jerga técnica innecesaria
        zona = " de tu zona de cobertura"
    return (
        f"El incidente{zona} ya fue resuelto por el equipo de guardia. "
        "¿Ya te anda el servicio o necesitás ayuda con otra cosa?"
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
    # "bien gracias", "si gracias", "dale mil gracias"
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
        "nas_reachable_at_declare": o.nas_reachable_at_declare,
        "estado": o.estado,
        "fuente": o.fuente,
        "created_by": o.created_by,
        "started_at": o.started_at.isoformat() if o.started_at else "",
        "resolved_at": o.resolved_at.isoformat() if o.resolved_at else "",
        "created_at": o.created_at.isoformat() if o.created_at else "",
        "updated_at": o.updated_at.isoformat() if o.updated_at else "",
    }
