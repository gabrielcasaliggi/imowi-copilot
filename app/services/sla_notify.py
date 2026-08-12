"""Alertas al primer incumplimiento de SLA de un ticket."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.estate import repository as repo
from app.estate.models import Ticket
from app.services.email import send_email

logger = logging.getLogger("operations_hub.sla_notify")

CANAL_SLA = "sla_breach"


def notify_sla_breach(db: Session, t: Ticket, *, was_breached: bool) -> int:
    """Notifica una sola vez cuando sla_breached_at pasa de vacío a seteado.

    was_breached: True si el ticket ya tenía sla_breached_at antes de apply_sla.
    """
    if was_breached:
        return 0
    if not t.sla_breached_at:
        return 0
    if (t.estado or "") == "Cerrado":
        return 0

    org_id = t.organizacion_id
    titulo = f"SLA vencido · {t.id}"
    mensaje = (
        f"Ticket {t.id} ({t.nivel or 'N1'} · {t.categoria or 'General'}) "
        f"superó el plazo SLA ({t.sla_policy or 'n/d'}). "
        f"Estado SLA: {t.estado_sla or 'Vencido'}."
    )

    destinatarios: set[str] = set()
    try:
        for email in repo.destinatarios_alerta_csat(db, org_id):
            destinatarios.add(email)
    except Exception:
        logger.warning("No se pudieron listar destinatarios SLA", exc_info=True)

    asignado = (t.asignado_a or "").strip().lower()
    if asignado and "@" in asignado:
        destinatarios.add(asignado)

    if not destinatarios:
        logger.warning("SLA breach sin destinatarios ticket=%s", t.id)
        return 0

    creadas = 0
    for dest in sorted(destinatarios):
        try:
            repo.add_ticket_notification(
                db,
                org_id,
                t.id,
                destinatario=dest,
                titulo=titulo[:160],
                mensaje=mensaje,
                canal=CANAL_SLA,
            )
            creadas += 1
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
            logger.warning("No se pudo notificar SLA a %s", dest, exc_info=True)
        try:
            send_email(to=dest, subject=titulo[:120], body_text=mensaje)
        except Exception:
            logger.warning("Email SLA falló para %s", dest, exc_info=True)

    logger.info("SLA breach notificado ticket=%s n=%s", t.id, creadas)
    return creadas
