"""No cerrar titularidad virtual/fallecimiento si el abonado no mandó docs al chat."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.flujos_abonado import parse_modalidad_titularidad, solicita_cambio_titularidad
from app.estate import canal_repo as crepo
from app.estate.models import ConversacionCanal

MSG_CIERRE_DOCS_TITULARIDAD = (
    "Este trámite de titularidad es virtual y todavía no hay documentación "
    "en el chat (foto o PDF del abonado). Pedile que la mande por acá antes de cerrar."
)


def _es_cliente(autor: str) -> bool:
    return str(autor or "").strip().lower() in ("cliente", "user", "abonado")


def _modalidad_titularidad(ctx: dict, textos_cliente: list[str]) -> str | None:
    stored = str(ctx.get("titularidad_modalidad") or "").strip().lower()
    if stored in ("virtual", "presencial", "fallecimiento"):
        return stored
    for texto in textos_cliente:
        mod = parse_modalidad_titularidad(texto)
        if mod:
            return mod
    return None


def _es_tramite_titularidad(ctx: dict, textos_cliente: list[str]) -> bool:
    if str(ctx.get("intencion") or "").strip() == "cambio_titularidad":
        return True
    return any(solicita_cambio_titularidad(t) for t in textos_cliente)


def motivo_bloqueo_cierre_tramite(db: Session, conv: ConversacionCanal) -> str | None:
    """Texto para HTTP 400, o None si el agente puede cerrar."""
    ctx = crepo.get_contexto(conv)
    mensajes = list(crepo.list_mensajes(db, conv.id))
    textos = [
        str(getattr(m, "texto", "") or "")
        for m in mensajes
        if _es_cliente(str(getattr(m, "autor", "") or ""))
    ]
    if not _es_tramite_titularidad(ctx, textos):
        return None
    mod = _modalidad_titularidad(ctx, textos)
    if mod not in ("virtual", "fallecimiento"):
        return None
    for m in mensajes:
        if not _es_cliente(str(getattr(m, "autor", "") or "")):
            continue
        if str(getattr(m, "media_relpath", "") or "").strip():
            return None
    return MSG_CIERRE_DOCS_TITULARIDAD


def dict_conversacion_con_cierre(
    db: Session,
    conv: ConversacionCanal,
    data: dict,
) -> dict:
    data["cierre_bloqueado_motivo"] = motivo_bloqueo_cierre_tramite(db, conv) or ""
    return data
