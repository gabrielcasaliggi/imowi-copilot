"""Repositorio inbox / abonados / conversaciones de canal."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.estate.models import Abonado, ConversacionCanal, MensajeCanal


def _now():
    return datetime.now(timezone.utc)


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
    tel = normalizar_telefono(telefono)
    wa = wa_id or tel
    existing = db.scalar(
        select(ConversacionCanal)
        .where(
            ConversacionCanal.organizacion_id == org_id,
            ConversacionCanal.telefono == tel,
            ConversacionCanal.estado != "cerrado",
        )
        .order_by(ConversacionCanal.updated_at.desc())
    )
    if existing:
        return existing
    conv = ConversacionCanal(
        organizacion_id=org_id,
        canal=canal,
        wa_id=wa,
        telefono=tel,
        session_id=f"wa:{org_id}:{tel}",
        estado="bot",
        contexto_json="{}",
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


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
        texto=texto,
        meta_message_id=meta_message_id,
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
    limit: int = 50,
) -> list[ConversacionCanal]:
    stmt = (
        select(ConversacionCanal)
        .where(ConversacionCanal.organizacion_id == org_id)
        .order_by(ConversacionCanal.updated_at.desc())
        .limit(limit)
    )
    rows = list(db.scalars(stmt).all())
    if estado:
        rows = [c for c in rows if c.estado == estado]
    if agente_id:
        rows = [c for c in rows if c.agente_id == agente_id]
    return rows


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
    }


def conversacion_to_dict(c: ConversacionCanal, *, abonado: Abonado | None = None) -> dict:
    canal_raw = c.canal or "whatsapp"
    if canal_raw in ("whatsapp", "simulate"):
        canal_display = "WhatsApp"
    elif canal_raw == "web":
        canal_display = "Web"
    else:
        canal_display = canal_raw
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
        "contexto": get_contexto(c),
        "created_at": c.created_at.isoformat() if c.created_at else "",
        "updated_at": c.updated_at.isoformat() if c.updated_at else "",
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
