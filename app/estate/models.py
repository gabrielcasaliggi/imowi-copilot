"""Modelo relacional multitenant — Data Estate OSS/BSS."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.estate.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    logo_label: Mapped[str] = mapped_column(String(8), default="i")
    brand_color: Mapped[str] = mapped_column(String(16), default="#2298A6")

    usuarios: Mapped[list[User]] = relationship(back_populates="organizacion")
    articulos_kb: Mapped[list[KnowledgeArticle]] = relationship(back_populates="organizacion")
    contribuciones_kb: Mapped[list[KnowledgeContribution]] = relationship(
        back_populates="organizacion"
    )
    elementos_red: Mapped[list[NetworkElement]] = relationship(back_populates="organizacion")
    tickets: Mapped[list[Ticket]] = relationship(back_populates="organizacion")
    ticket_events: Mapped[list[TicketEvent]] = relationship(back_populates="organizacion")
    ticket_notifications: Mapped[list[TicketNotification]] = relationship(back_populates="organizacion")
    casos_conversacion: Mapped[list[CasoConversacion]] = relationship(back_populates="organizacion")
    abonados: Mapped[list[Abonado]] = relationship(back_populates="organizacion")
    conversaciones_canal: Mapped[list[ConversacionCanal]] = relationship(back_populates="organizacion")
    encuestas_satisfaccion: Mapped[list[EncuestaSatisfaccion]] = relationship(
        back_populates="organizacion"
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organizacion_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(120), nullable=False)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    password: Mapped[str] = mapped_column(String(255), default="demo")
    rol: Mapped[str] = mapped_column(String(32), nullable=False)
    telefono: Mapped[str] = mapped_column(String(32), default="")
    linea_principal: Mapped[str] = mapped_column(String(16), default="")
    must_change_password: Mapped[str] = mapped_column(String(8), default="No")
    activo: Mapped[str] = mapped_column(String(8), default="Sí")
    disponibilidad: Mapped[str] = mapped_column(String(24), default="disponible")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organizacion: Mapped[Organization] = relationship(back_populates="usuarios")


class KnowledgeArticle(Base):
    __tablename__ = "knowledge_articles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organizacion_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    categoria: Mapped[str] = mapped_column(String(80), default="General")
    contenido: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    organizacion: Mapped[Organization] = relationship(back_populates="articulos_kb")


class KnowledgeContribution(Base):
    """Propuesta a KB pendiente de revisión admin (cierres N1/N2 o aporte de agente)."""

    __tablename__ = "knowledge_contributions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organizacion_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    ticket_id: Mapped[str] = mapped_column(String(32), default="", index=True)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    categoria: Mapped[str] = mapped_column(String(80), default="General")
    contenido: Mapped[str] = mapped_column(Text, nullable=False)
    estado: Mapped[str] = mapped_column(String(24), default="pendiente", index=True)
    origen: Mapped[str] = mapped_column(String(32), default="cierre")  # cierre|agente|manual
    nivel_ticket: Mapped[str] = mapped_column(String(16), default="")
    propuesto_por: Mapped[str] = mapped_column(String(120), default="")
    revisado_por: Mapped[str] = mapped_column(String(120), default="")
    motivo_revision: Mapped[str] = mapped_column(Text, default="")
    articulo_id: Mapped[str] = mapped_column(String(36), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    organizacion: Mapped[Organization] = relationship(back_populates="contribuciones_kb")


class NetworkElement(Base):
    __tablename__ = "network_elements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organizacion_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    elemento_red: Mapped[str] = mapped_column(String(160), nullable=False)
    metrica: Mapped[str] = mapped_column(String(80), default="latencia")
    valor_actual: Mapped[str] = mapped_column(String(80), default="12ms")
    estado_actual: Mapped[str] = mapped_column(String(40), default="Normal")
    ultima_actualizacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    organizacion: Mapped[Organization] = relationship(back_populates="elementos_red")


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

    organizacion: Mapped[Organization] = relationship()


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
    asignado_a: Mapped[str] = mapped_column(String(120), default="")
    # Clasificación operativa N1 / N2 / Proveedor
    nivel: Mapped[str] = mapped_column(String(16), default="N1")
    destino: Mapped[str] = mapped_column(String(32), default="cooperativa")
    proveedor: Mapped[str] = mapped_column(String(120), default="")
    motivo_escalamiento: Mapped[str] = mapped_column(Text, default="")
    evidencia: Mapped[str] = mapped_column(Text, default="")
    acciones_n1_realizadas: Mapped[str] = mapped_column(Text, default="")
    estado_sla: Mapped[str] = mapped_column(String(32), default="Pendiente")
    sla_policy: Mapped[str] = mapped_column(String(32), default="")
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sla_breached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ticket_externo_id: Mapped[str] = mapped_column(String(64), default="")
    regla_clasificacion: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    organizacion: Mapped[Organization] = relationship(back_populates="tickets")
    eventos: Mapped[list[TicketEvent]] = relationship(back_populates="ticket", cascade="all, delete-orphan")
    notificaciones: Mapped[list[TicketNotification]] = relationship(
        back_populates="ticket",
        primaryjoin="Ticket.id == foreign(TicketNotification.ticket_id)",
        viewonly=True,
    )


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

    organizacion: Mapped[Organization] = relationship(back_populates="ticket_events")
    ticket: Mapped[Ticket] = relationship(back_populates="eventos")


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

    organizacion: Mapped[Organization] = relationship(back_populates="casos_conversacion")


class TicketNotification(Base):
    """Notificación local para quien originó el reclamo."""

    __tablename__ = "ticket_notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organizacion_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    # Nullable y sin FK obligatorio: alertas CSAT tras cierre N1 sin ticket N2
    ticket_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True, default=None)
    destinatario: Mapped[str] = mapped_column(String(120), default="")
    canal: Mapped[str] = mapped_column(String(40), default="consola")
    titulo: Mapped[str] = mapped_column(String(160), default="")
    mensaje: Mapped[str] = mapped_column(Text, default="")
    leida: Mapped[str] = mapped_column(String(8), default="No")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    organizacion: Mapped[Organization] = relationship(back_populates="ticket_notifications")
    ticket: Mapped[Ticket | None] = relationship(
        back_populates="notificaciones",
        primaryjoin="foreign(TicketNotification.ticket_id) == Ticket.id",
        viewonly=True,
    )


class AuditEvent(Base):
    """Auditoría operativa de acciones sensibles."""

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organizacion_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    actor: Mapped[str] = mapped_column(String(120), default="sistema")
    accion: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    recurso: Mapped[str] = mapped_column(String(160), default="")
    detalle: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    organizacion: Mapped[Organization] = relationship()


class AuthLoginEvent(Base):
    """Auditoría de intentos de login (consola y portal)."""

    __tablename__ = "auth_login_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    superficie: Mapped[str] = mapped_column(String(16), default="console", index=True)  # console|portal
    actor: Mapped[str] = mapped_column(String(160), default="", index=True)
    ip: Mapped[str] = mapped_column(String(64), default="", index=True)
    ok: Mapped[str] = mapped_column(String(8), default="No")
    reason: Mapped[str] = mapped_column(String(80), default="")
    org_slug: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class AuthLockout(Base):
    """Bloqueo temporal por intentos fallidos (IP + actor)."""

    __tablename__ = "auth_lockouts"
    __table_args__ = (UniqueConstraint("superficie", "actor_key", name="uq_auth_lockout_actor"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    superficie: Mapped[str] = mapped_column(String(16), default="console", index=True)
    actor_key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class AuthTokenDenylist(Base):
    """JWT jti invalidados (logout)."""

    __tablename__ = "auth_token_denylist"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    exp_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class UserInvite(Base):
    """Invitación por email a consola (alta operador/coop)."""

    __tablename__ = "user_invites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organizacion_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(120), default="")
    rol: Mapped[str] = mapped_column(String(32), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    invited_by: Mapped[str] = mapped_column(String(120), default="")
    purpose: Mapped[str] = mapped_column(String(32), default="invite")  # invite | password_reset
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    organizacion: Mapped[Organization] = relationship()


class PortalAbonadoLink(Base):
    """Vínculo mínimo local abonado↔portal (sin padrón completo)."""

    __tablename__ = "portal_abonado_links"
    __table_args__ = (UniqueConstraint("organizacion_id", "dni_normalized", name="uq_portal_link_org_dni"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organizacion_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    dni_normalized: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    dni_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    abonado_ref: Mapped[str] = mapped_column(String(80), default="")
    pin_hash: Mapped[str] = mapped_column(String(255), default="")
    contacto_email_masked: Mapped[str] = mapped_column(String(120), default="")
    enrolled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activo: Mapped[str] = mapped_column(String(8), default="Sí")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    organizacion: Mapped[Organization] = relationship()


class PortalOtpChallenge(Base):
    """Desafío OTP email para auth portal."""

    __tablename__ = "portal_otp_challenges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organizacion_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    dni_normalized: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    contact_masked: Mapped[str] = mapped_column(String(120), default="")
    abonado_ref: Mapped[str] = mapped_column(String(80), default="")
    email_destino: Mapped[str] = mapped_column(String(160), default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Abonado(Base):
    """Abonado cooperativa (internet / móvil) para canal WhatsApp y N1."""

    __tablename__ = "abonados"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organizacion_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    dni: Mapped[str] = mapped_column(String(20), default="", index=True)
    telefono_e164: Mapped[str] = mapped_column(String(20), default="", index=True)
    nombre: Mapped[str] = mapped_column(String(120), default="")
    servicio: Mapped[str] = mapped_column(String(20), default="internet")  # internet|movil|ambos
    estado: Mapped[str] = mapped_column(String(32), default="activo")  # activo|corte|suspendido
    deuda_monto: Mapped[str] = mapped_column(String(40), default="0")
    plan: Mapped[str] = mapped_column(String(80), default="")
    linea_msisdn: Mapped[str] = mapped_column(String(16), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    organizacion: Mapped[Organization] = relationship(back_populates="abonados")


class ConversacionCanal(Base):
    """Hilo canal abonado (WhatsApp / Telegram / web / simulador) para inbox."""

    __tablename__ = "conversaciones_canal"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organizacion_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    canal: Mapped[str] = mapped_column(String(20), default="whatsapp")  # whatsapp|telegram|web|simulate
    wa_id: Mapped[str] = mapped_column(String(40), default="", index=True)  # wa_id o chat_id TG
    telefono: Mapped[str] = mapped_column(String(40), default="", index=True)  # E.164 o chat_id TG
    abonado_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    estado: Mapped[str] = mapped_column(String(24), default="bot", index=True)  # bot|espera_agente|con_agente|cerrado
    agente_id: Mapped[str] = mapped_column(String(120), default="")
    session_id: Mapped[str] = mapped_column(String(80), default="", index=True)
    servicio_detectado: Mapped[str] = mapped_column(String(20), default="")
    ticket_id: Mapped[str] = mapped_column(String(32), default="")
    contexto_json: Mapped[str] = mapped_column(Text, default="{}")
    agente_last_read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    organizacion: Mapped[Organization] = relationship(back_populates="conversaciones_canal")
    mensajes: Mapped[list[MensajeCanal]] = relationship(
        back_populates="conversacion", cascade="all, delete-orphan"
    )


class MensajeCanal(Base):
    """Mensaje de un hilo de canal (cliente / bot / agente)."""

    __tablename__ = "mensajes_canal"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organizacion_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    conversacion_id: Mapped[str] = mapped_column(ForeignKey("conversaciones_canal.id"), index=True)
    direccion: Mapped[str] = mapped_column(String(8), default="in")  # in|out
    autor: Mapped[str] = mapped_column(String(16), default="cliente")  # cliente|bot|agente
    texto: Mapped[str] = mapped_column(Text, default="")
    # wamid de Meta puede superar 80 chars; truncamos al persistir por seguridad
    meta_message_id: Mapped[str] = mapped_column(String(191), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    conversacion: Mapped[ConversacionCanal] = relationship(back_populates="mensajes")


class PlatformConfig(Base):
    """Configuración de plataforma editable por admin (IA, WhatsApp, KB, playbooks)."""

    __tablename__ = "platform_config"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default="default")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    updated_by: Mapped[str] = mapped_column(String(120), default="")


class EncuestaSatisfaccion(Base):
    """Voto CSAT 1–5 del abonado tras cierre N1 (bot) o atención humana."""

    __tablename__ = "encuestas_satisfaccion"
    __table_args__ = (UniqueConstraint("conversacion_id", name="uq_encuesta_conversacion"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organizacion_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    abonado_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    conversacion_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    ticket_id: Mapped[str] = mapped_column(String(32), default="", index=True)
    origen: Mapped[str] = mapped_column(String(16), default="[BOT]", index=True)  # [BOT]|[TECNICO]
    puntuacion: Mapped[int] = mapped_column(Integer, nullable=False)
    canal: Mapped[str] = mapped_column(String(20), default="")
    agente_id: Mapped[str] = mapped_column(String(120), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    organizacion: Mapped[Organization] = relationship(back_populates="encuestas_satisfaccion")


class PilotEvent(Base):
    """Eventos de telemetría del piloto operativo."""

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

    organizacion: Mapped[Organization] = relationship()
