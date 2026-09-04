"""Repositorio inbox / abonados / conversaciones de canal."""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.canales import CANALES_PROPIOS, es_canal_propio
from app.domain.canales import canal_display as etiqueta_canal
from app.estate.models import Abonado, ConversacionCanal, MensajeCanal

_ULTIMO_MSG_PREVIEW_LEN = 120
_ESTADOS_UNREAD = frozenset({"espera_agente", "con_agente"})

# Claim corto en proceso: evita doble Whisper/TTS si Meta reintenta antes del commit.
_CLAIMED_INBOUND_MIDS: dict[str, float] = {}
_CLAIMED_LOCK = threading.Lock()
_CLAIM_TTL_S = 3600.0
_CLAIM_MAX = 8000


def _now():
    return datetime.now(UTC)


def try_claim_inbound_meta(meta_message_id: str) -> bool:
    """True si este proceso puede procesar el wamid (primera vez en la ventana TTL)."""
    mid = (meta_message_id or "").strip()[:191]
    if not mid:
        return True
    now = time.time()
    with _CLAIMED_LOCK:
        if len(_CLAIMED_INBOUND_MIDS) > _CLAIM_MAX:
            expired = [
                k for k, ts in _CLAIMED_INBOUND_MIDS.items() if now - ts > _CLAIM_TTL_S
            ]
            for k in expired:
                _CLAIMED_INBOUND_MIDS.pop(k, None)
        prev = _CLAIMED_INBOUND_MIDS.get(mid)
        if prev is not None and now - prev < _CLAIM_TTL_S:
            return False
        _CLAIMED_INBOUND_MIDS[mid] = now
        return True


def release_inbound_meta_claim(meta_message_id: str) -> None:
    """Libera claim si falló el procesamiento (permite reintento local)."""
    mid = (meta_message_id or "").strip()[:191]
    if not mid:
        return
    with _CLAIMED_LOCK:
        _CLAIMED_INBOUND_MIDS.pop(mid, None)


def normalizar_telefono(raw: str) -> str:
    s = (raw or "").strip()
    # IDs sintéticos del portal (invitado) — no strippear letras
    if s.startswith("guest"):
        return s
    digitos = re.sub(r"\D", "", s)
    if digitos.startswith("54") and len(digitos) >= 12:
        return digitos
    if len(digitos) == 10:
        return "54" + digitos
    if len(digitos) == 11 and digitos.startswith("0"):
        return "54" + digitos[1:]
    return digitos


def normalizar_identidad(canal: str, raw: str) -> str:
    """Identidad por canal: E.164 (WA/web/app) o chat_id (Telegram)."""
    s = (raw or "").strip()
    if (canal or "") == "telegram":
        if s.startswith("tg:"):
            s = s[3:].strip()
        # chat_id puede ser negativo (grupos); preservar signo
        if re.fullmatch(r"-?\d+", s):
            return s
        return s[:40]
    return normalizar_telefono(s)


def _session_prefix(canal: str) -> str:
    return {
        "whatsapp": "wa",
        "simulate": "wa",
        "telegram": "tg",
        "web": "web",
        "app": "app",
    }.get(canal or "whatsapp", "ch")


def normalizar_dni(raw: str) -> str:
    return re.sub(r"\D", "", raw or "")


def find_abonado_por_telefono(db: Session, org_id: str, telefono: str) -> Abonado | None:
    tel = normalizar_telefono(telefono)
    if not tel:
        return None
    rows = list(db.scalars(select(Abonado).where(Abonado.organizacion_id == org_id)).all())
    for a in rows:
        if normalizar_telefono(a.telefono_e164) == tel:
            return a
        if a.linea_msisdn and normalizar_telefono(a.linea_msisdn) == tel:
            return a
    # match sufijo 10 dígitos
    suf = tel[-10:] if len(tel) >= 10 else tel
    for a in rows:
        if normalizar_telefono(a.telefono_e164).endswith(suf):
            return a
    return None


def find_abonado_por_dni(db: Session, org_id: str, dni: str) -> Abonado | None:
    d = normalizar_dni(dni)
    if not d:
        return None
    return db.scalar(
        select(Abonado).where(Abonado.organizacion_id == org_id, Abonado.dni == d)
    )


def list_abonados(db: Session, org_id: str) -> list[Abonado]:
    return list(db.scalars(select(Abonado).where(Abonado.organizacion_id == org_id)).all())


def get_contexto(conv: ConversacionCanal) -> dict:
    try:
        return json.loads(conv.contexto_json or "{}")
    except json.JSONDecodeError:
        return {}


def set_contexto(conv: ConversacionCanal, ctx: dict) -> None:
    conv.contexto_json = json.dumps(ctx, ensure_ascii=False)


def get_or_create_conversacion(
    db: Session,
    org_id: str,
    *,
    telefono: str,
    canal: str = "whatsapp",
    wa_id: str = "",
) -> ConversacionCanal:
    canal_norm = (canal or "whatsapp").strip() or "whatsapp"
    tel = normalizar_identidad(canal_norm, telefono)
    wa = (wa_id or "").strip() or tel
    if canal_norm == "telegram":
        wa = normalizar_identidad("telegram", wa)
    canal_filter = (
        ConversacionCanal.canal.in_(tuple(CANALES_PROPIOS))
        if es_canal_propio(canal_norm)
        else ConversacionCanal.canal == canal_norm
    )
    existing = db.scalar(
        select(ConversacionCanal)
        .where(
            ConversacionCanal.organizacion_id == org_id,
            canal_filter,
            ConversacionCanal.telefono == tel,
            ConversacionCanal.estado != "cerrado",
        )
        .order_by(ConversacionCanal.updated_at.desc())
    )
    if existing:
        # Ticket ya cerrado pero el hilo quedó abierto → cerrar y abrir uno nuevo
        if (existing.ticket_id or "").strip():
            from app.estate.models import Ticket

            t = db.get(Ticket, existing.ticket_id)
            if t is not None and (t.estado or "") == "Cerrado":
                existing.estado = "cerrado"
                db.commit()
                existing = None
    if existing:
        if existing.canal != canal_norm:
            existing.canal = canal_norm
            db.commit()
        return existing
    prefix = _session_prefix(canal_norm)
    conv = ConversacionCanal(
        organizacion_id=org_id,
        canal=canal_norm,
        wa_id=wa[:40],
        telefono=tel[:40],
        session_id=f"{prefix}:{org_id}:{tel}"[:80],
        estado="bot",
        contexto_json="{}",
        ticket_id="",
        agente_id="",
    )
    db.add(conv)
    # flush (no commit): el commit lo hace add_mensaje / caller.
    # Evita hilos vacíos si falla el insert del primer mensaje (p.ej. wamid largo).
    db.flush()
    db.refresh(conv)
    return conv


def inbound_meta_ya_procesado(db: Session, org_id: str, meta_message_id: str) -> bool:
    """True si ya guardamos un inbound con ese wamid/meta id (idempotencia webhook)."""
    mid = (meta_message_id or "").strip()[:191]
    if not mid:
        return False
    return (
        db.scalar(
            select(MensajeCanal.id)
            .where(
                MensajeCanal.organizacion_id == org_id,
                MensajeCanal.meta_message_id == mid,
                MensajeCanal.direccion == "in",
            )
            .limit(1)
        )
        is not None
    )


def add_mensaje(
    db: Session,
    org_id: str,
    conversacion_id: str,
    *,
    direccion: str,
    autor: str,
    texto: str,
    meta_message_id: str = "",
) -> MensajeCanal:
    m = MensajeCanal(
        organizacion_id=org_id,
        conversacion_id=conversacion_id,
        direccion=direccion,
        autor=autor,
        texto=texto or "",
        meta_message_id=(meta_message_id or "")[:191],
    )
    db.add(m)
    conv = db.get(ConversacionCanal, conversacion_id)
    if conv:
        conv.updated_at = _now()
    db.commit()
    db.refresh(m)
    return m


def list_conversaciones(
    db: Session,
    org_id: str,
    *,
    estado: str = "",
    agente_id: str = "",
    excluir_cerrado: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[ConversacionCanal]:
    stmt = (
        select(ConversacionCanal)
        .where(ConversacionCanal.organizacion_id == org_id)
        .order_by(ConversacionCanal.updated_at.desc())
    )
    if estado:
        stmt = stmt.where(ConversacionCanal.estado == estado)
    elif excluir_cerrado:
        stmt = stmt.where(ConversacionCanal.estado != "cerrado")
    if agente_id:
        stmt = stmt.where(ConversacionCanal.agente_id == agente_id)
    if offset:
        stmt = stmt.offset(max(0, offset))
    stmt = stmt.limit(max(1, min(limit, 100)))
    return list(db.scalars(stmt).all())


def count_conversaciones(
    db: Session,
    org_id: str,
    *,
    estado: str = "",
    agente_id: str = "",
    excluir_cerrado: bool = False,
) -> int:
    stmt = (
        select(func.count())
        .select_from(ConversacionCanal)
        .where(ConversacionCanal.organizacion_id == org_id)
    )
    if estado:
        stmt = stmt.where(ConversacionCanal.estado == estado)
    elif excluir_cerrado:
        stmt = stmt.where(ConversacionCanal.estado != "cerrado")
    if agente_id:
        stmt = stmt.where(ConversacionCanal.agente_id == agente_id)
    return int(db.scalar(stmt) or 0)


def last_messages_by_conversacion(
    db: Session,
    conversacion_ids: list[str],
) -> dict[str, MensajeCanal]:
    """Último mensaje por conversación (1 query, compatible SQLite/Postgres)."""
    ids = [cid for cid in conversacion_ids if cid]
    if not ids:
        return {}
    rows = list(
        db.scalars(
            select(MensajeCanal)
            .where(MensajeCanal.conversacion_id.in_(ids))
            .order_by(MensajeCanal.conversacion_id.asc(), MensajeCanal.created_at.desc())
        ).all()
    )
    out: dict[str, MensajeCanal] = {}
    for m in rows:
        if m.conversacion_id not in out:
            out[m.conversacion_id] = m
    return out


def unread_flags_by_conversacion(
    db: Session,
    convs: list[ConversacionCanal],
) -> dict[str, bool]:
    """True si hay mensaje del cliente posterior a agente_last_read_at."""
    actionable = [c for c in convs if c.estado in _ESTADOS_UNREAD]
    if not actionable:
        return {}
    ids = [c.id for c in actionable]
    last_read = {c.id: c.agente_last_read_at for c in actionable}
    rows = list(
        db.scalars(
            select(MensajeCanal)
            .where(
                MensajeCanal.conversacion_id.in_(ids),
                MensajeCanal.autor == "cliente",
            )
            .order_by(MensajeCanal.conversacion_id.asc(), MensajeCanal.created_at.desc())
        ).all()
    )
    last_cliente: dict[str, datetime] = {}
    for m in rows:
        if m.conversacion_id not in last_cliente and m.created_at:
            last_cliente[m.conversacion_id] = m.created_at

    out: dict[str, bool] = {}
    for c in actionable:
        msg_at = last_cliente.get(c.id)
        if not msg_at:
            out[c.id] = False
            continue
        lr = last_read.get(c.id)
        if lr is None:
            out[c.id] = True
        else:
            # normalizar naive/aware
            lr_cmp = lr
            msg_cmp = msg_at
            if lr_cmp.tzinfo is None and msg_cmp.tzinfo is not None:
                lr_cmp = lr_cmp.replace(tzinfo=UTC)
            if msg_cmp.tzinfo is None and lr_cmp.tzinfo is not None:
                msg_cmp = msg_cmp.replace(tzinfo=UTC)
            out[c.id] = msg_cmp > lr_cmp
    return out


def mark_conversacion_read(
    db: Session,
    org_id: str,
    conv_id: str,
    *,
    when: datetime | None = None,
) -> ConversacionCanal | None:
    c = get_conversacion(db, org_id, conv_id)
    if not c:
        return None
    c.agente_last_read_at = when or _now()
    db.commit()
    db.refresh(c)
    return c


def _truncate_preview(texto: str, max_len: int = _ULTIMO_MSG_PREVIEW_LEN) -> str:
    t = (texto or "").strip().replace("\n", " ")
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rstrip() + "…"


def get_conversacion(db: Session, org_id: str, conv_id: str) -> ConversacionCanal | None:
    c = db.get(ConversacionCanal, conv_id)
    if not c or c.organizacion_id != org_id:
        return None
    return c


def get_conversacion_by_ticket(
    db: Session, org_id: str, ticket_id: str
) -> ConversacionCanal | None:
    tid = (ticket_id or "").strip()
    if not tid:
        return None
    return db.scalar(
        select(ConversacionCanal)
        .where(
            ConversacionCanal.organizacion_id == org_id,
            ConversacionCanal.ticket_id == tid,
        )
        .order_by(ConversacionCanal.updated_at.desc())
    )


def list_mensajes(db: Session, conversacion_id: str) -> list[MensajeCanal]:
    return list(
        db.scalars(
            select(MensajeCanal)
            .where(MensajeCanal.conversacion_id == conversacion_id)
            .order_by(MensajeCanal.created_at.asc())
        ).all()
    )


def abonado_to_dict(a: Abonado | None) -> dict | None:
    if not a:
        return None
    return {
        "id": a.id,
        "dni": a.dni,
        "telefono_e164": a.telefono_e164,
        "nombre": a.nombre,
        "servicio": a.servicio,
        "estado": a.estado,
        "deuda_monto": a.deuda_monto,
        "plan": a.plan,
        "linea_msisdn": a.linea_msisdn,
        "client_number": str(getattr(a, "client_number", "") or "").strip(),
    }


def conversacion_to_dict(
    c: ConversacionCanal,
    *,
    abonado: Abonado | None = None,
    ultimo: MensajeCanal | None = None,
    tiene_no_leidos: bool = False,
) -> dict:
    canal_raw = c.canal or "whatsapp"
    canal_display = etiqueta_canal(canal_raw)
    ctx = get_contexto(c)
    es_visitante = bool(
        ctx.get("visitante")
        or (ctx.get("cola_prioridad") == "baja" and not c.abonado_id)
        or (ctx.get("invitado") and not c.abonado_id and c.estado in ("espera_agente", "con_agente"))
    )
    cola_prioridad = str(ctx.get("cola_prioridad") or ("baja" if es_visitante else "alta"))
    ultimo_texto = _truncate_preview(ultimo.texto) if ultimo else ""
    ultimo_autor = (ultimo.autor if ultimo else "") or ""
    ultimo_at = ""
    if ultimo and ultimo.created_at:
        ultimo_at = ultimo.created_at.isoformat()
    elif c.updated_at:
        ultimo_at = c.updated_at.isoformat()
    last_read = getattr(c, "agente_last_read_at", None)
    return {
        "id": c.id,
        "canal": canal_raw,
        "canal_display": canal_display,
        "wa_id": c.wa_id,
        "telefono": c.telefono,
        "abonado_id": c.abonado_id,
        "abonado": abonado_to_dict(abonado),
        "estado": c.estado,
        "agente_id": c.agente_id,
        "session_id": c.session_id,
        "servicio_detectado": c.servicio_detectado,
        "ticket_id": c.ticket_id,
        "contexto": ctx,
        "es_visitante": es_visitante,
        "cola_prioridad": cola_prioridad,
        "created_at": c.created_at.isoformat() if c.created_at else "",
        "updated_at": c.updated_at.isoformat() if c.updated_at else "",
        "ultimo_mensaje_texto": ultimo_texto,
        "ultimo_mensaje_autor": ultimo_autor,
        "ultimo_mensaje_at": ultimo_at,
        "agente_last_read_at": last_read.isoformat() if last_read else "",
        "tiene_no_leidos": bool(tiene_no_leidos),
    }


def mensaje_to_dict(m: MensajeCanal) -> dict:
    return {
        "id": m.id,
        "conversacion_id": m.conversacion_id,
        "direccion": m.direccion,
        "autor": m.autor,
        "texto": m.texto,
        "meta_message_id": m.meta_message_id,
        "created_at": m.created_at.isoformat() if m.created_at else "",
    }
