"""Push Expo hacia la app abonado (canal=app)."""

from __future__ import annotations

import logging

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.estate.models import PortalDevice

logger = logging.getLogger("operations_hub")

_EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
_TOKEN_PREFIXES = ("ExponentPushToken[", "ExpoPushToken[")


def token_push_valido(token: str) -> bool:
    t = (token or "").strip()
    return any(t.startswith(p) and t.endswith("]") for p in _TOKEN_PREFIXES)


def listar_tokens_org(db: Session, org_id: str, *, conversacion_id: str = "") -> list[str]:
    q = select(PortalDevice).where(
        PortalDevice.organizacion_id == org_id,
        PortalDevice.activo == "Sí",
    )
    if conversacion_id:
        q = q.where(PortalDevice.conversacion_id == conversacion_id)
    rows = db.scalars(q).all()
    out: list[str] = []
    seen: set[str] = set()
    for row in rows:
        tok = (row.expo_push_token or "").strip()
        if tok and tok not in seen and token_push_valido(tok):
            seen.add(tok)
            out.append(tok)
    return out


def enviar_push_expo(
    tokens: list[str],
    *,
    title: str,
    body: str,
    data: dict | None = None,
) -> dict:
    if not tokens:
        return {"ok": True, "sent": 0}
    messages = [
        {
            "to": tok,
            "title": title[:80],
            "body": (body or "")[:180],
            "sound": "default",
            "channelId": "eko",
            "data": data or {},
        }
        for tok in tokens
    ]
    try:
        with httpx.Client(timeout=12.0) as client:
            r = client.post(_EXPO_PUSH_URL, json=messages)
        if r.status_code >= 400:
            logger.warning("Expo push HTTP %s: %s", r.status_code, r.text[:300])
            return {"ok": False, "sent": 0, "status": r.status_code}
        return {"ok": True, "sent": len(messages)}
    except Exception:
        logger.exception("Expo push falló")
        return {"ok": False, "sent": 0}


def notificar_conversacion_app(
    db: Session,
    org_id: str,
    conversacion_id: str,
    *,
    title: str,
    body: str,
    data: dict | None = None,
) -> dict:
    tokens = listar_tokens_org(db, org_id, conversacion_id=conversacion_id)
    payload = {"conversacion_id": conversacion_id, **(data or {})}
    return enviar_push_expo(tokens, title=title, body=body, data=payload)


def notificar_incidente_app(
    db: Session,
    org_id: str,
    *,
    title: str,
    body: str,
    data: dict | None = None,
) -> dict:
    tokens = listar_tokens_org(db, org_id)
    return enviar_push_expo(tokens, title=title, body=body, data=data or {"tipo": "incidente"})
