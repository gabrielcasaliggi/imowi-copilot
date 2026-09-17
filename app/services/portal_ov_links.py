"""Portal: links tipados de Oficina Virtual para el abonado autenticado.

Reutiliza ov_batan (mismo criterio que N1). No cachea links (pueden ser temporales).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.estate.models import Abonado

logger = logging.getLogger("operations_hub")

CHAT_HINT = "Si el link no abre, escribinos y te ayudamos."

# Acciones de producto (subset de gestiones OV usadas por N1 facturación).
_ACTIONS: tuple[tuple[str, str, str], ...] = (
    ("pay", "pagar", "Pagar"),
    ("invoice", "my", "Ver factura"),
    ("payment_slip", "talon", "Talón de pago"),
)


def _now() -> datetime:
    return datetime.now(UTC)


def _is_authenticated_ov_link(url: str) -> bool:
    return "tsid=" in (url or "").lower()


def evaluar_ov_links_portal(
    db: Session,
    *,
    abonado: Abonado,
    conversacion_id: str = "",
    canal: str = "app",
) -> dict[str, Any]:
    """Resuelve links OV para el abonado del JWT. Sin IDs externos en query."""
    from app.estate import canal_repo as crepo
    from app.services.ov_batan import (
        candidatos_celular_ov,
        ov_configurado,
        url_ov_para_key,
    )

    checked_at = _now().isoformat()
    actions = {"can_open_chat": True, "chat_hint": CHAT_HINT}

    if not ov_configurado(db):
        logger.info("portal_ov_links: OV no configurado")
        return {
            "status": "unavailable",
            "checked_at": checked_at,
            "actions": actions,
            "links": [
                {"id": i, "label": lab, "url": None, "available": False}
                for i, _k, lab in _ACTIONS
            ],
            "reason_code": "ov_unavailable",
        }

    wa_id = ""
    telefono_hilo = ""
    conv_id = (conversacion_id or "").strip()
    if conv_id:
        try:
            org_id = str(getattr(abonado, "organizacion_id", "") or "")
            conv = crepo.get_conversacion(db, org_id, conv_id) if org_id else None
            if conv is not None and str(getattr(conv, "abonado_id", "") or "") == str(
                abonado.id
            ):
                wa_id = str(getattr(conv, "wa_id", "") or "")
                telefono_hilo = str(getattr(conv, "telefono", "") or "")
                canal = str(getattr(conv, "canal", "") or canal or "app")
        except Exception:
            logger.debug("portal_ov_links: sin conversación para candidatos", exc_info=True)

    try:
        cels = candidatos_celular_ov(
            abonado,
            canal=canal or "app",
            wa_id=wa_id,
            telefono_hilo=telefono_hilo,
            db=db,
        )
    except Exception:
        logger.exception("portal_ov_links: candidatos celular falló")
        return {
            "status": "unavailable",
            "checked_at": checked_at,
            "actions": actions,
            "links": [
                {"id": i, "label": lab, "url": None, "available": False}
                for i, _k, lab in _ACTIONS
            ],
            "reason_code": "ov_unavailable",
        }

    links: list[dict[str, Any]] = []
    auth_count = 0
    available_count = 0

    try:
        for link_id, key, label in _ACTIONS:
            try:
                url = url_ov_para_key(
                    key,
                    cels[0] if cels else "",
                    db=db,
                    celulares=cels,
                )
            except Exception:
                logger.exception("portal_ov_links: url_ov_para_key key=%s", key)
                url = ""
            url_n = (url or "").strip() or None
            available = bool(url_n)
            if available:
                available_count += 1
            if url_n and _is_authenticated_ov_link(url_n):
                auth_count += 1
            links.append(
                {
                    "id": link_id,
                    "label": label,
                    "url": url_n if available else None,
                    "available": available,
                }
            )
    except Exception:
        logger.exception("portal_ov_links: resolución falló")
        return {
            "status": "unavailable",
            "checked_at": checked_at,
            "actions": actions,
            "links": [
                {"id": i, "label": lab, "url": None, "available": False}
                for i, _k, lab in _ACTIONS
            ],
            "reason_code": "ov_unavailable",
        }

    if available_count == 0:
        status = "unavailable"
        reason: str | None = "ov_unavailable"
    elif available_count < len(_ACTIONS):
        status = "partial"
        reason = "partial"
    elif not cels or auth_count == 0:
        # Solo hashes públicos (sin MSISDN usable o OV no emitió tsid).
        status = "partial"
        reason = "insufficient_data"
    else:
        status = "ready"
        reason = None

    logger.info(
        "portal_ov_links status=%s available=%s auth=%s cels=%s abo=%s",
        status,
        available_count,
        auth_count,
        len(cels),
        str(abonado.id)[:8],
    )
    return {
        "status": status,
        "checked_at": checked_at,
        "actions": actions,
        "links": links,
        "reason_code": reason,
    }
