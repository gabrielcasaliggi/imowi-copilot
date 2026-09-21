"""Portal: links tipados de Oficina Virtual para el abonado autenticado.

Handoff de producto = hash público verificado (``ov.batan.coop/#/…``).
El cliente se identifica en la OV. Un ``tsid`` legado nunca implica AUTH/ready.
No exige credenciales de API OV. No cachea links.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.estate.models import Abonado
from app.services.ov_handoff import (
    MODE_AUTHENTICATED,
    MODE_FAILED,
    MODE_PUBLIC,
    HandoffOutcome,
    resolve_handoff,
)

logger = logging.getLogger("operations_hub")

CHAT_HINT = "Si el link no abre, escribinos y te ayudamos."
CHAT_HINT_PUBLIC = (
    "Estos links abren la oficina virtual. Ahí vas a identificarte "
    "(DNI o usuario). No es un acceso ya autenticado."
)

# Acciones de producto (subset de gestiones OV usadas por N1 facturación).
_ACTIONS: tuple[tuple[str, str, str], ...] = (
    ("pay", "pay", "Pagar"),
    ("invoice", "invoice", "Ver factura"),
    ("payment_slip", "payment_slip", "Talón de pago"),
)


def _now() -> datetime:
    return datetime.now(UTC)


def _payload(
    *,
    status: str,
    checked_at: str,
    links: list[dict[str, Any]],
    reason: str | None,
    mode: str,
    authenticated: bool,
    chat_hint: str = CHAT_HINT,
) -> dict[str, Any]:
    return {
        "status": status,
        "checked_at": checked_at,
        "actions": {"can_open_chat": True, "chat_hint": chat_hint},
        "links": links,
        "reason_code": reason,
        "mode": mode,
        "authenticated": authenticated,
    }


def evaluar_ov_links_portal(
    db: Session,
    *,
    abonado: Abonado,
    conversacion_id: str = "",
    canal: str = "app",
) -> dict[str, Any]:
    """Resuelve links OV para el abonado del JWT. Sin IDs externos en query.

    Los hashes públicos no dependen de credenciales de API OV (JSAT).
    """
    from app.estate import canal_repo as crepo

    checked_at = _now().isoformat()

    phone_candidates = None
    conv_id = (conversacion_id or "").strip()
    if conv_id:
        try:
            org_id = str(getattr(abonado, "organizacion_id", "") or "")
            conv = crepo.get_conversacion(db, org_id, conv_id) if org_id else None
            if conv is not None and str(getattr(conv, "abonado_id", "") or "") == str(
                abonado.id
            ):
                canal = str(getattr(conv, "canal", "") or canal or "app")
                ctx = crepo.get_contexto(conv)
                phone_candidates = ctx.get("phone_candidates")
        except Exception:
            logger.debug("portal_ov_links: sin conversación", exc_info=True)

    outcomes: list[tuple[str, str, HandoffOutcome]] = []
    try:
        for link_id, intent, label in _ACTIONS:
            out = resolve_handoff(
                intent,
                abonado,
                db=db,
                canal=canal or "app",
                phone_candidates=phone_candidates,
            )
            outcomes.append((link_id, label, out))
    except Exception:
        logger.exception("portal_ov_links: resolución falló")
        return _payload(
            status="unavailable",
            checked_at=checked_at,
            links=[
                {"id": i, "label": lab, "url": None, "available": False, "mode": MODE_FAILED}
                for i, _k, lab in _ACTIONS
            ],
            reason="ov_unavailable",
            mode=MODE_FAILED,
            authenticated=False,
        )

    links: list[dict[str, Any]] = []
    auth_count = 0
    available_count = 0
    public_count = 0
    reasons: list[str] = []
    for link_id, label, out in outcomes:
        url_n = (out.url or "").strip() or None
        available = bool(url_n)
        if available:
            available_count += 1
        if out.mode == MODE_AUTHENTICATED:
            auth_count += 1
        elif out.mode == MODE_PUBLIC:
            public_count += 1
        if out.reason:
            reasons.append(out.reason)
        links.append(
            {
                "id": link_id,
                "label": label,
                "url": url_n if available else None,
                "available": available,
                "mode": out.mode,
            }
        )

    reason_primary = reasons[0] if reasons else None
    authenticated = auth_count == len(_ACTIONS) and auth_count > 0
    if authenticated:
        status = "ready"
        mode = MODE_AUTHENTICATED
        reason: str | None = None
        hint = CHAT_HINT
    elif available_count == 0:
        status = "unavailable"
        mode = MODE_FAILED
        reason = "ov_unavailable"
        hint = CHAT_HINT
    else:
        # Hash público de OV: el abonado se identifica allá. Nunca ready.
        status = "partial"
        mode = MODE_PUBLIC
        reason = reason_primary if reason_primary in (
            "ov_unavailable",
            "partial",
            "insufficient_data",
            "identity_ambiguous",
        ) else "insufficient_data"
        hint = CHAT_HINT_PUBLIC

    logger.info(
        "portal_ov_links status=%s mode=%s auth=%s available=%s abo=%s",
        status,
        mode,
        authenticated,
        available_count,
        str(getattr(abonado, "id", "") or "")[:8],
    )
    return _payload(
        status=status,
        checked_at=checked_at,
        links=links,
        reason=reason,
        mode=mode,
        authenticated=authenticated,
        chat_hint=hint,
    )
