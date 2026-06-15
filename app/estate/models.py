"""Modelo relacional multitenant — Data Estate OSS/BSS."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.estate.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    logo_label: Mapped[str] = mapped_column(String(8), default="i")
    brand_color: Mapped[str] = mapped_column(String(16), default="#22d3ee")

    usuarios: Mapped[list["User"]] = relationship(back_populates="organizacion")
    articulos_kb: Mapped[list["KnowledgeArticle"]] = relationship(back_populates="organizacion")
    elementos_red: Mapped[list["NetworkElement"]] = relationship(back_populates="organizacion")
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="organizacion")
    ticket_events: Mapped[list["TicketEvent"]] = relationship(back_populates="organizacion")
    ticket_notifications: Mapped[list["TicketNotification"]] = relationship(back_populates="organizacion")
    casos_conversacion: Mapped[list["CasoConversacion"]] = relationship(back_populates="organizacion")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organizacion_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(120), nullable=False)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    password: Mapped[str] = mapped_column(String(120), default="demo")
    rol: Mapped[str] = mapped_column(String(32), nullable=False)

    organizacion: Mapped["Organization"] = relationship(back_populates="usuarios")


class KnowledgeArticle(Base):
    __tablename__ = "knowledge_articles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organizacion_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    categoria: Mapped[str] = mapped_column(String(80), default="General")
    contenido: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    organizacion: Mapped["Organization"] = relationship(back_populates="articulos_kb")


class NetworkElement(Base):
    __tablename__ = "network_elements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organizacion_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    elemento_red: Mapped[str] = mapped_column(String(160), nullable=False)
    metrica: Mapped[str] = mapped_column(String(80), default="latencia")
    valor_actual: Mapped[str] = mapped_column(String(80), default="12ms")
    estado_actual: Mapped[str] = mapped_column(String(40), default="Normal")
    ultima_actualizacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    organizacion: Mapped["Organization"] = relationship(back_populates="elementos_red")


class LineaJSC(Base):
    """Réplica demo de líneas/abonados sincronizados desde JSC (proveedor infra)."""

    __tablename__ = "lineas_jsc"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organizacion_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    msisdn: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    jsc_ref: Mapped[str] = mapped_column(String(32), default="")
    abonado: Mapped[str] = mapped_column(String(120), default="")
    plan: Mapped[str] = mapped_column(String(80), default="")
    estado_linea: Mapped[str] = mapped_column(String(32), default="Activa")
    iccid: Mapped[str] = mapped_column(String(24), default="")
    roaming_habilitado: Mapped[str] = mapped_column(String(8), default="Sí")
    apn: Mapped[str] = mapped_column(String(80), default="")
    estado_cuenta: Mapped[str] = mapped_column(String(32), default="Al día")
    saldo_resumen: Mapped[str] = mapped_column(String(40), default="$0")
    ultima_sync: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    organizacion: Mapped["Organization"] = relationship()


class Ticket(Base):
    __tablename__ = "tickets_estate"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    organizacion_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    linea: Mapped[str] = mapped_column(String(32), default="")
    dispositivo: Mapped[str] = mapped_column(String(120), default="")
    descripcion_falla: Mapped[str] = mapped_column(Text, default="")
    origen: Mapped[str] = mapped_column(String(40), default="Reporte Cliente")
    estado: Mapped[str] = mapped_column(String(32), default="Abierto")
    resolucion_tecnica: Mapped[str] = mapped_column(Text, default="")
    categoria: Mapped[str] = mapped_column(String(80), default="General")
    intent_ejecutado: Mapped[str] = mapped_column(String(80), default="")
    creado_por: Mapped[str] = mapped_column(String(120), default="")
    # Clasificación operativa N1 / N2 / Proveedor
    nivel: Mapped[str] = mapped_column(String(16), default="N1")
    destino: Mapped[str] = mapped_column(String(32), default="cooperativa")
    proveedor: Mapped[str] = mapped_column(String(120), default="")
    motivo_escalamiento: Mapped[str] = mapped_column(Text, default="")
    evidencia: Mapped[str] = mapped_column(Text, default="")
    acciones_n1_realizadas: Mapped[str] = mapped_column(Text, default="")
    estado_sla: Mapped[str] = mapped_column(String(32), default="Pendiente")
    ticket_externo_id: Mapped[str] = mapped_column(String(64), default="")
    regla_clasificacion: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    organizacion: Mapped["Organization"] = relationship(back_populates="tickets")
    eventos: Mapped[list["TicketEvent"]] = relationship(back_populates="ticket", cascade="all, delete-orphan")
    notificaciones: Mapped[list["TicketNotification"]] = relationship(back_populates="ticket", cascade="all, delete-orphan")


class TicketEvent(Base):
    """Timeline auditable del ticket para la demo de seguimiento."""

    __tablename__ = "ticket_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organizacion_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets_estate.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(40), default="actualizacion")
    titulo: Mapped[str] = mapped_column(String(160), default="")
    detalle: Mapped[str] = mapped_column(Text, default="")
    nivel: Mapped[str] = mapped_column(String(16), default="")
    estado: Mapped[str] = mapped_column(String(32), default="")
    actor: Mapped[str] = mapped_column(String(120), default="sistema")
    visible_cliente: Mapped[str] = mapped_column(String(8), default="Sí")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    organizacion: Mapped["Organization"] = relationship(back_populates="ticket_events")
    ticket: Mapped["Ticket"] = relationship(back_populates="eventos")


class CasoConversacion(Base):
    """Estado persistido del diálogo cooperativa por sesión."""

    __tablename__ = "casos_conversacion"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organizacion_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    usuario: Mapped[str] = mapped_column(String(120), default="")
    estado: Mapped[str] = mapped_column(String(40), default="nuevo_reclamo")
    datos_triaje_json: Mapped[str] = mapped_column(Text, default="{}")
    clasificacion_json: Mapped[str] = mapped_column(Text, default="{}")
    linea_msisdn: Mapped[str] = mapped_column(String(16), default="", index=True)
    intencion_pendiente: Mapped[str] = mapped_column(String(32), default="")
    paso_kb_idx: Mapped[str] = mapped_column(String(8), default="0")
    kb_agotada: Mapped[str] = mapped_column(String(8), default="No")
    ticket_id: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    organizacion: Mapped["Organization"] = relationship(back_populates="casos_conversacion")


class TicketNotification(Base):
    """Notificación local para quien originó el reclamo."""

    __tablename__ = "ticket_notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organizacion_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets_estate.id"), index=True)
    destinatario: Mapped[str] = mapped_column(String(120), default="")
    canal: Mapped[str] = mapped_column(String(40), default="consola")
    titulo: Mapped[str] = mapped_column(String(160), default="")
    mensaje: Mapped[str] = mapped_column(Text, default="")
    leida: Mapped[str] = mapped_column(String(8), default="No")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    organizacion: Mapped["Organization"] = relationship(back_populates="ticket_notifications")
    ticket: Mapped["Ticket"] = relationship(back_populates="notificaciones")


class PilotEvent(Base):
    """Eventos de telemetría del piloto operativo imowi."""

    __tablename__ = "pilot_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organizacion_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    session_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    tipo: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    escenario_id: Mapped[str] = mapped_column(String(64), default="")
    categoria: Mapped[str] = mapped_column(String(40), default="")
    paso_id: Mapped[str] = mapped_column(String(64), default="")
    ticket_id: Mapped[str] = mapped_column(String(32), default="")
    actor: Mapped[str] = mapped_column(String(120), default="")
    detalle_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    organizacion: Mapped["Organization"] = relationship()
