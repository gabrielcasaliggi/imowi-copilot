"""Notificaciones al pasar una conversación a espera_agente."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.estate import repository as repo
from app.estate.models import ConversacionCanal
from app.rbac import normalizar_rol_consola
from app.services.email import send_email

logger = logging.getLogger("operations_hub.handoff_notify")

CANAL_HANDOFF = "inbox_handoff"


def destinatarios_alerta_handoff(db: Session, org_id: str) -> list[str]:
    """Emails a notificar: agentes disponibles de la org; si no hay, supervisores/admins."""
    users = repo.list_users_for_org(db, org_id)
    disponibles: set[str] = set()
    supervisores: set[str] = set()
    for u in users:
        if (u.activo or "Sí") == "No":
            continue
        email = (u.email or "").strip().lower()
        if not email or "@" not in email:
            continue
        rol = normalizar_rol_consola(u.rol or "")
        if rol in ("supervisor", "admin", "ejecutivo"):
            supervisores.add(email)
        if rol in ("agente", "supervisor", "admin") and (u.disponibilidad or "disponible") == "disponible":
            disponibles.add(email)
    chosen = disponibles or supervisores
    if not chosen:
        # Fallback al mismo set que CSAT (supervisores org + admins plataforma)
        return repo.destinatarios_alerta_csat(db, org_id)
    # Incluir también admins plataforma para visibilidad NOC
    for u in repo.list_admins_plataforma(db):
        email = (u.email or "").strip().lower()
        if email and "@" in email:
            chosen.add(email)
    return sorted(chosen)


def notify_espera_agente(
    db: Session,
    conv: ConversacionCanal,
    *,
    prev_estado: str,
) -> int:
    """Crea notificaciones in-app (+ email si SMTP) solo si el estado cambió a espera_agente.

    Idempotente: si ya estaba en espera_agente, no hace nada.
    No propaga errores al caller (el handoff no debe fallar por notificaciones).
    """
    if (prev_estado or "") == "espera_agente":
        return 0
    if (conv.estado or "") != "espera_agente":
        return 0

    org_id = conv.organizacion_id
    canal = (conv.canal or "web").strip() or "web"
    quien = (conv.telefono or "").strip() or "Cliente"
    titulo = f"Cliente espera agente · {canal}"
    mensaje = (
        f"Conversación {conv.id[:8]}… ({quien}) pasó a cola de agentes "
        f"(canal {canal}). Abrí la bandeja para tomarla."
    )
    if conv.ticket_id:
        mensaje = f"{mensaje} Ticket asociado: {conv.ticket_id}."

    try:
        destinatarios = destinatarios_alerta_handoff(db, org_id)
    except Exception:
        logger.warning("No se pudieron listar destinatarios handoff", exc_info=True)
        return 0

    if not destinatarios:
        logger.warning(
            "Handoff sin destinatarios org=%s conv=%s",
            org_id,
            conv.id,
        )
        return 0

    creadas = 0
    for dest in destinatarios:
        try:
            repo.add_ticket_notification(
                db,
                org_id,
                conv.ticket_id or None,
                destinatario=dest,
                titulo=titulo[:160],
                mensaje=mensaje,
                canal=CANAL_HANDOFF,
            )
            creadas += 1
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
            logger.warning("No se pudo notificar handoff a %s", dest, exc_info=True)

        try:
            # send_email simula outbox en non-prod; en prod sin SMTP no bloquea el handoff
            send_email(to=dest, subject=titulo[:120], body_text=mensaje)
        except Exception:
            logger.warning("Email handoff falló para %s", dest, exc_info=True)

    logger.info(
        "Handoff notificado conv=%s prev=%s n=%s",
        conv.id,
        prev_estado,
        creadas,
    )
    return creadas
