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
_PAYLOAD_FORBIDDEN = frozenset(
    {
        "nas",
        "nas_shortname",
        "nas_ip",
        "olt",
        "serial",
        "comentario",
        "created_by",
        "ip",
        "public_ip",
    }
)

TITLE_DECLARED = "Corte en la red"
TITLE_RESOLVED = "Servicio restablecido"
TITLE_UPDATED = "Actualización del incidente"
BODY_RESOLVED = (
    "El inconveniente de red informado anteriormente fue resuelto."
)


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


def listar_tokens_afectados_por_nas(
    db: Session,
    org_id: str,
    nas_shortname: str,
    *,
    nas_ip: str = "",
) -> tuple[list[str], int]:
    """Tokens de devices activos cuyo abonado matchea el NAS del outage.

    Returns:
        (tokens_dedup, affected_subscribers_count)
    """
    from app.estate import canal_repo as crepo
    from app.services.outages import abonado_afectado_por_nas

    nas = (nas_shortname or "").strip()
    if not nas:
        return [], 0

    rows = list(
        db.scalars(
            select(PortalDevice).where(
                PortalDevice.organizacion_id == org_id,
                PortalDevice.activo == "Sí",
            )
        ).all()
    )
    if not rows:
        return [], 0

    by_dni: dict[str, list[PortalDevice]] = {}
    for row in rows:
        dni = str(row.dni_normalized or "").strip()
        if not dni:
            continue
        by_dni.setdefault(dni, []).append(row)

    tokens: list[str] = []
    seen_tok: set[str] = set()
    affected = 0

    for dni, devices in by_dni.items():
        abo = crepo.find_abonado_por_dni(db, org_id, dni)
        if abo is None:
            continue
        try:
            hit = abonado_afectado_por_nas(
                db, abo, nas, nas_ip_outage=nas_ip
            )
        except Exception:
            logger.exception(
                "listar_tokens_afectados_por_nas: match falló dni_len=%s",
                len(dni),
            )
            continue
        if not hit:
            continue
        affected += 1
        for row in devices:
            tok = (row.expo_push_token or "").strip()
            if tok and tok not in seen_tok and token_push_valido(tok):
                seen_tok.add(tok)
                tokens.append(tok)

    return tokens, affected


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


def _payload_incidente_seguro(
    *,
    outage_id: str,
    event: str,
    data: dict | None = None,
) -> dict:
    """Solo campos abonado-safe. Nunca incluye NAS ni infraestructura."""
    ev = (event or "declared").strip() or "declared"
    payload: dict = {
        "tipo": "incidente",
        "outage_id": str(outage_id or "").strip(),
        "event": ev,
    }
    if data:
        for k, v in data.items():
            key = str(k)
            if key.lower() in _PAYLOAD_FORBIDDEN:
                continue
            if key in ("tipo", "outage_id", "event"):
                continue
            payload[key] = v
    return payload


def _enviar_incidente_segmentado(
    db: Session,
    org_id: str,
    *,
    event: str,
    title: str,
    body: str,
    outage_id: str,
    nas_shortname: str,
    nas_ip: str = "",
    data: dict | None = None,
) -> dict:
    tokens, affected = listar_tokens_afectados_por_nas(
        db,
        org_id,
        nas_shortname,
        nas_ip=nas_ip,
    )
    payload = _payload_incidente_seguro(
        outage_id=outage_id, event=event, data=data
    )
    result = enviar_push_expo(tokens, title=title, body=body, data=payload)
    logger.info(
        "outage_push event=%s outage_id=%s affected_subscribers=%s "
        "device_tokens=%s push_sent=%s push_ok=%s",
        event,
        str(outage_id)[:36],
        affected,
        len(tokens),
        result.get("sent", 0),
        bool(result.get("ok")),
    )
    return {
        **result,
        "affected_subscribers": affected,
        "device_tokens": len(tokens),
        "event": event,
    }


def notificar_incidente_app(
    db: Session,
    org_id: str,
    *,
    title: str,
    body: str,
    outage_id: str,
    nas_shortname: str,
    nas_ip: str = "",
    data: dict | None = None,
) -> dict:
    """Push declared (E′1 segmentación + E′2 dedup persistente).

    Claim atómico de push_declared_at antes del envío: como máximo un declared
    por outage. El timestamp = intento reclamado, no entrega Expo.
    """
    from app.estate import repository as repo

    oid = str(outage_id or "").strip()
    if not oid:
        return {
            "ok": True,
            "sent": 0,
            "skipped": "missing_outage_id",
            "affected_subscribers": 0,
            "device_tokens": 0,
            "event": "declared",
        }
    if not repo.claim_outage_push_declared(db, oid):
        logger.info(
            "outage_push event=declared outage_id=%s skipped=already_declared",
            oid[:36],
        )
        return {
            "ok": True,
            "sent": 0,
            "skipped": "already_declared",
            "affected_subscribers": 0,
            "device_tokens": 0,
            "event": "declared",
        }
    return _enviar_incidente_segmentado(
        db,
        org_id,
        event="declared",
        title=title or TITLE_DECLARED,
        body=body,
        outage_id=oid,
        nas_shortname=nas_shortname,
        nas_ip=nas_ip,
        data=data,
    )


def notificar_incidente_resuelto_app(
    db: Session,
    org_id: str,
    *,
    outage_id: str,
    nas_shortname: str,
    nas_ip: str = "",
    title: str = TITLE_RESOLVED,
    body: str = BODY_RESOLVED,
) -> dict:
    """Push resolved: misma segmentación E′1; como máximo uno por outage."""
    from app.estate import repository as repo

    oid = str(outage_id or "").strip()
    if not oid:
        return {
            "ok": True,
            "sent": 0,
            "skipped": "missing_outage_id",
            "affected_subscribers": 0,
            "device_tokens": 0,
            "event": "resolved",
        }
    if not repo.claim_outage_push_resolved(db, oid):
        logger.info(
            "outage_push event=resolved outage_id=%s skipped=already_resolved",
            oid[:36],
        )
        return {
            "ok": True,
            "sent": 0,
            "skipped": "already_resolved",
            "affected_subscribers": 0,
            "device_tokens": 0,
            "event": "resolved",
        }
    return _enviar_incidente_segmentado(
        db,
        org_id,
        event="resolved",
        title=title or TITLE_RESOLVED,
        body=body or BODY_RESOLVED,
        outage_id=oid,
        nas_shortname=nas_shortname,
        nas_ip=nas_ip,
    )


def notificar_incidente_actualizado_app(
    db: Session,
    org_id: str,
    *,
    outage_id: str,
    nas_shortname: str,
    nas_ip: str = "",
    body: str,
    title: str = TITLE_UPDATED,
) -> dict:
    """Push updated: misma segmentación E′1. Sin dedup de ciclo (varios updates OK)."""
    oid = str(outage_id or "").strip()
    if not oid:
        return {
            "ok": True,
            "sent": 0,
            "skipped": "missing_outage_id",
            "affected_subscribers": 0,
            "device_tokens": 0,
            "event": "updated",
        }
    msg = (body or "").strip() or TITLE_UPDATED
    return _enviar_incidente_segmentado(
        db,
        org_id,
        event="updated",
        title=title or TITLE_UPDATED,
        body=msg,
        outage_id=oid,
        nas_shortname=nas_shortname,
        nas_ip=nas_ip,
    )
