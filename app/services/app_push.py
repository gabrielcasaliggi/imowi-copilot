"""Push Expo hacia la app abonado (canal=app)."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import httpx
from sqlalchemy import select, update
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

# Solo DeviceNotRegistered marca token muerto (higiene). Nunca por timeout/5xx.
_EXPO_TOKEN_DEAD = frozenset({"devicenotregistered"})

TITLE_DECLARED = "Corte en la red"
TITLE_RESOLVED = "Servicio restablecido"
TITLE_UPDATED = "Actualización del incidente"
BODY_RESOLVED = (
    "El inconveniente de red informado anteriormente fue resuelto."
)


def token_push_valido(token: str) -> bool:
    t = (token or "").strip()
    return any(t.startswith(p) and t.endswith("]") for p in _TOKEN_PREFIXES)


def token_fingerprint(token: str) -> str:
    """Identificador no sensible para logs (no es el token completo)."""
    t = (token or "").strip()
    if not t:
        return ""
    return hashlib.sha256(t.encode("utf-8")).hexdigest()[:12]


def material_update_fingerprint(body: str) -> str:
    """Identidad de un material_update concreto (contenido customer-safe)."""
    norm = " ".join((body or "").strip().split())
    if not norm:
        return ""
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def classify_expo_error(error_code: str) -> str:
    """Clasifica error Expo: invalid_token | permanent | transient | unknown."""
    code = (error_code or "").strip().lower().replace(" ", "")
    if code in _EXPO_TOKEN_DEAD:
        return "invalid_token"
    if code in (
        "messagetoomanyrequests",
        "serviceunavailable",
        "internalservererror",
        "timeout",
    ):
        return "transient"
    if "invalid" in code or code == "invalidcredentials":
        return "permanent"
    if code:
        return "unknown"
    return "unknown"


def parse_expo_push_tickets(
    tokens: list[str],
    payload: Any,
) -> dict[str, Any]:
    """Parsea respuesta Expo tickets. No inventa message ids."""
    tickets: list[Any] = []
    if isinstance(payload, dict):
        raw = payload.get("data")
        if isinstance(raw, list):
            tickets = raw
        elif isinstance(raw, dict):
            tickets = [raw]
    ok_n = 0
    err_n = 0
    message_ids: list[str] = []
    invalid_tokens: list[str] = []
    error_categories: list[str] = []
    for i, ticket in enumerate(tickets):
        if not isinstance(ticket, dict):
            continue
        status = str(ticket.get("status") or "").lower()
        tok = tokens[i] if i < len(tokens) else ""
        if status == "ok":
            ok_n += 1
            mid = str(ticket.get("id") or "").strip()
            if mid:
                message_ids.append(mid)
            continue
        err_n += 1
        details = ticket.get("details") if isinstance(ticket.get("details"), dict) else {}
        err = str(
            details.get("error") or ticket.get("message") or ticket.get("error") or ""
        )
        cat = classify_expo_error(err)
        error_categories.append(cat)
        if cat == "invalid_token" and tok and token_push_valido(tok):
            invalid_tokens.append(tok)
    category = "ok"
    if err_n and not ok_n:
        category = error_categories[0] if error_categories else "unknown"
    elif err_n and ok_n:
        category = "partial"
    return {
        "tickets_ok": ok_n,
        "tickets_error": err_n,
        "provider_message_ids": message_ids,
        "invalid_tokens": invalid_tokens,
        "error_category": category,
    }


def deactivate_invalid_push_tokens(db: Session, tokens: list[str]) -> int:
    """Marca activo=No solo para tokens con evidencia DeviceNotRegistered.

    No borra filas. No actúa ante errores transitorios.
    """
    clean = [t.strip() for t in tokens if t and token_push_valido(t.strip())]
    if not clean:
        return 0
    result = db.execute(
        update(PortalDevice)
        .where(
            PortalDevice.expo_push_token.in_(clean),
            PortalDevice.activo == "Sí",
        )
        .values(activo="No")
    )
    db.commit()
    n = int(result.rowcount or 0)
    if n:
        fps = [token_fingerprint(t) for t in clean[:5]]
        logger.info(
            "push_token_hygiene deactivated=%s token_fps=%s",
            n,
            ",".join(fps),
        )
    return n


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


def listar_tokens_duenos_ticket(
    db: Session,
    org_id: str,
    ticket_id: str,
) -> tuple[list[str], int]:
    """Tokens de PortalDevice de abonados dueños del ticket (regla portal).

    Returns:
        (tokens_dedup, owner_abonados_count)
    """
    from sqlalchemy import or_

    from app.estate import canal_repo as crepo
    from app.estate import repository as repo
    from app.estate.models import Abonado, ConversacionCanal
    from app.estate.security import normalizar_dni
    from app.services.abonado_tickets import ticket_pertenece_abonado

    tid = (ticket_id or "").strip()
    if not tid:
        return [], 0
    ticket = repo.get_ticket(db, org_id, tid)
    if not ticket:
        return [], 0

    candidates: list[Abonado] = []
    seen_abo: set[str] = set()

    for c in db.scalars(
        select(ConversacionCanal).where(
            ConversacionCanal.organizacion_id == org_id,
            ConversacionCanal.ticket_id == tid,
            ConversacionCanal.abonado_id != "",
        )
    ).all():
        aid = str(c.abonado_id or "").strip()
        if not aid or aid in seen_abo:
            continue
        abo = db.get(Abonado, aid)
        if abo and abo.organizacion_id == org_id:
            seen_abo.add(aid)
            candidates.append(abo)

    linea = (ticket.linea or "").strip()
    if linea:
        nlinea = crepo.normalizar_telefono(linea) or ""
        keys = {k for k in (linea, nlinea) if k}
        if keys:
            for abo in db.scalars(
                select(Abonado).where(
                    Abonado.organizacion_id == org_id,
                    or_(
                        Abonado.linea_msisdn.in_(list(keys)),
                        Abonado.telefono_e164.in_(list(keys)),
                    ),
                )
            ).all():
                if abo.id not in seen_abo:
                    seen_abo.add(abo.id)
                    candidates.append(abo)

    owners = [
        abo
        for abo in candidates
        if ticket_pertenece_abonado(db, org_id, abo, ticket)
    ]
    if not owners:
        return [], 0

    dnis = {
        normalizar_dni(str(a.dni or ""))
        for a in owners
        if str(a.dni or "").strip()
    }
    dnis.discard("")
    if not dnis:
        return [], 0

    rows = list(
        db.scalars(
            select(PortalDevice).where(
                PortalDevice.organizacion_id == org_id,
                PortalDevice.activo == "Sí",
                PortalDevice.dni_normalized.in_(list(dnis)),
            )
        ).all()
    )
    tokens: list[str] = []
    seen_tok: set[str] = set()
    for row in rows:
        tok = (row.expo_push_token or "").strip()
        if tok and tok not in seen_tok and token_push_valido(tok):
            seen_tok.add(tok)
            tokens.append(tok)
    return tokens, len(owners)


def enviar_push_expo(
    tokens: list[str],
    *,
    title: str,
    body: str,
    data: dict | None = None,
) -> dict:
    """Envía a Expo. Nunca marca éxito sin evidencia HTTP+tickets.

    Returns: ok, sent, error_category, provider_message_ids,
    invalid_tokens (tokens crudos DeviceNotRegistered — caller decide higiene),
    invalid_token_fps (para logs), retryable, http_status.
    """
    if not tokens:
        return {
            "ok": True,
            "sent": 0,
            "error_category": "no_tokens",
            "provider_message_ids": [],
            "invalid_tokens": [],
            "retryable": False,
            "http_status": None,
        }
    valid: list[str] = []
    invalid_shape = 0
    for t in tokens:
        if token_push_valido(t):
            valid.append(t)
        else:
            invalid_shape += 1
    if not valid:
        return {
            "ok": False,
            "sent": 0,
            "error_category": "invalid_token",
            "provider_message_ids": [],
            "invalid_tokens": [],
            "retryable": False,
            "http_status": None,
            "skipped_malformed": invalid_shape,
        }

    messages = [
        {
            "to": tok,
            "title": title[:80],
            "body": (body or "")[:180],
            "sound": "default",
            "channelId": "eko",
            "data": data or {},
        }
        for tok in valid
    ]
    try:
        with httpx.Client(timeout=12.0) as client:
            r = client.post(_EXPO_PUSH_URL, json=messages)
        if r.status_code >= 500:
            logger.warning("Expo push HTTP %s (transient)", r.status_code)
            return {
                "ok": False,
                "sent": 0,
                "error_category": "transient",
                "provider_message_ids": [],
                "invalid_tokens": [],
                "retryable": True,
                "http_status": r.status_code,
            }
        if r.status_code >= 400:
            logger.warning("Expo push HTTP %s: %s", r.status_code, r.text[:300])
            return {
                "ok": False,
                "sent": 0,
                "error_category": "permanent",
                "provider_message_ids": [],
                "invalid_tokens": [],
                "retryable": False,
                "http_status": r.status_code,
            }
        try:
            payload = r.json()
        except Exception:
            logger.warning("Expo push: respuesta no JSON")
            return {
                "ok": False,
                "sent": 0,
                "error_category": "unknown",
                "provider_message_ids": [],
                "invalid_tokens": [],
                "retryable": True,
                "http_status": r.status_code,
            }
        parsed = parse_expo_push_tickets(valid, payload)
        dead = list(parsed["invalid_tokens"])
        dead_fps = [token_fingerprint(t) for t in dead]

        tickets_present = isinstance(payload.get("data"), (list, dict))
        if not tickets_present and len(valid) > 0:
            return {
                "ok": False,
                "sent": 0,
                "error_category": "unknown",
                "provider_message_ids": [],
                "invalid_tokens": [],
                "invalid_token_fps": [],
                "retryable": True,
                "http_status": r.status_code,
            }

        sent = int(parsed["tickets_ok"])
        all_failed = parsed["tickets_error"] > 0 and parsed["tickets_ok"] == 0
        if all_failed:
            cat = (
                parsed["error_category"]
                if parsed["error_category"] not in ("ok",)
                else "permanent"
            )
            return {
                "ok": False,
                "sent": 0,
                "error_category": cat,
                "provider_message_ids": parsed["provider_message_ids"],
                "invalid_tokens": dead,
                "invalid_token_fps": dead_fps,
                "retryable": cat == "transient",
                "http_status": r.status_code,
                "device_tokens": len(valid),
            }
        if sent == 0 and parsed["tickets_error"] == 0 and len(valid) > 0:
            return {
                "ok": False,
                "sent": 0,
                "error_category": "unknown",
                "provider_message_ids": [],
                "invalid_tokens": [],
                "invalid_token_fps": [],
                "retryable": True,
                "http_status": r.status_code,
                "device_tokens": len(valid),
            }
        return {
            "ok": sent > 0,
            "sent": sent,
            "error_category": parsed["error_category"] if sent else "unknown",
            "provider_message_ids": parsed["provider_message_ids"],
            "invalid_tokens": dead,
            "invalid_token_fps": dead_fps,
            "retryable": False,
            "http_status": r.status_code,
            "device_tokens": len(valid),
        }
    except httpx.TimeoutException:
        logger.warning("Expo push timeout")
        return {
            "ok": False,
            "sent": 0,
            "error_category": "timeout",
            "provider_message_ids": [],
            "invalid_tokens": [],
            "retryable": True,
            "http_status": None,
        }
    except Exception:
        logger.exception("Expo push falló")
        return {
            "ok": False,
            "sent": 0,
            "error_category": "unknown",
            "provider_message_ids": [],
            "invalid_tokens": [],
            "retryable": True,
            "http_status": None,
        }


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
    result = enviar_push_expo(tokens, title=title, body=body, data=payload)
    dead = result.get("invalid_tokens") or []
    if dead:
        deactivate_invalid_push_tokens(db, list(dead))
    # No filtrar tokens crudos hacia callers externos en logs; fps sí.
    out = dict(result)
    out["invalid_token_fps"] = result.get("invalid_token_fps") or [
        token_fingerprint(t) for t in dead
    ]
    out["invalid_tokens"] = out["invalid_token_fps"]
    return out


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
    dead = result.get("invalid_tokens") or []
    if dead:
        deactivate_invalid_push_tokens(db, list(dead))
    fps = result.get("invalid_token_fps") or [token_fingerprint(t) for t in dead]
    logger.info(
        "outage_push event=%s outage_id=%s affected_subscribers=%s "
        "device_tokens=%s push_sent=%s push_ok=%s error_category=%s retryable=%s "
        "invalid_token_fps=%s",
        event,
        str(outage_id)[:36],
        affected,
        len(tokens),
        result.get("sent", 0),
        bool(result.get("ok")),
        result.get("error_category"),
        result.get("retryable"),
        ",".join(fps[:5]),
    )
    safe = dict(result)
    safe["invalid_token_fps"] = fps
    safe["invalid_tokens"] = fps  # no exponer tokens crudos al caller
    return {
        **safe,
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
            "error_category": "no_op",
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
            "error_category": "duplicate",
            "retryable": False,
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
            "error_category": "no_op",
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
            "error_category": "duplicate",
            "retryable": False,
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
    """Push updated: E′1 + 2.3E fingerprint dedup (mismo contenido → skip).

    Updates materiales con body distinto siguen notificándose.
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
            "event": "updated",
            "error_category": "no_op",
        }
    msg = (body or "").strip() or TITLE_UPDATED
    fp = material_update_fingerprint(msg)
    if not fp or not repo.claim_outage_push_material(db, oid, fp):
        logger.info(
            "outage_push event=updated outage_id=%s skipped=already_material_fp",
            oid[:36],
        )
        return {
            "ok": True,
            "sent": 0,
            "skipped": "already_material_fp",
            "affected_subscribers": 0,
            "device_tokens": 0,
            "event": "updated",
            "error_category": "duplicate",
            "retryable": False,
            "material_fingerprint": fp[:12] if fp else "",
        }
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


def _payload_ticket_seguro(
    *,
    ticket_id: str,
    event: str,
) -> dict:
    """Contrato mobile 2.3G-M + 2.6A. Sin detalle interno ni texto de TicketEvent."""
    ev = (event or "").strip().lower()
    if ev not in ("created", "updated", "resolved", "closed", "sla_breached"):
        ev = ""
    return {
        "tipo": "ticket",
        "ticket_id": str(ticket_id or "").strip(),
        "event": ev,
    }


def notificar_ticket_app(
    db: Session,
    org_id: str,
    *,
    ticket_id: str,
    ticket_event_id: str,
    event: str,
    title: str,
    body: str,
) -> dict:
    """Push ticket (2.3G-B). Claim por TicketEvent.id — no usa campos de outage."""
    from app.estate import repository as repo

    teid = str(ticket_event_id or "").strip()
    tid = str(ticket_id or "").strip()
    if not teid or not tid:
        return {
            "ok": True,
            "sent": 0,
            "skipped": "missing_ticket_or_event_id",
            "owner_abonados": 0,
            "device_tokens": 0,
            "event": event,
            "error_category": "no_op",
        }

    tokens, owners = listar_tokens_duenos_ticket(db, org_id, tid)
    if owners == 0:
        logger.info(
            "ticket_push event=%s ticket_id=%s ticket_event_id=%s "
            "skipped=ownership_unresolved",
            event,
            tid[:32],
            teid[:36],
        )
        return {
            "ok": True,
            "sent": 0,
            "skipped": "OWNERSHIP_UNRESOLVED",
            "owner_abonados": 0,
            "device_tokens": 0,
            "event": event,
            "error_category": "no_op",
            "retryable": False,
        }

    if not repo.claim_ticket_event_push(db, teid):
        logger.info(
            "ticket_push event=%s ticket_id=%s ticket_event_id=%s skipped=already_claimed",
            event,
            tid[:32],
            teid[:36],
        )
        return {
            "ok": True,
            "sent": 0,
            "skipped": "already_claimed",
            "owner_abonados": owners,
            "device_tokens": len(tokens),
            "event": event,
            "error_category": "duplicate",
            "retryable": False,
        }

    payload = _payload_ticket_seguro(ticket_id=tid, event=event)
    result = enviar_push_expo(
        tokens,
        title=title or "Tu solicitud",
        body=body or "Hay una novedad en tu solicitud.",
        data=payload,
    )
    dead = result.get("invalid_tokens") or []
    if dead:
        deactivate_invalid_push_tokens(db, list(dead))
    fps = result.get("invalid_token_fps") or [token_fingerprint(t) for t in dead]
    logger.info(
        "ticket_push event=%s ticket_id=%s ticket_event_id=%s owner_abonados=%s "
        "device_tokens=%s push_sent=%s push_ok=%s error_category=%s "
        "invalid_token_fps=%s",
        event,
        tid[:32],
        teid[:36],
        owners,
        len(tokens),
        result.get("sent", 0),
        bool(result.get("ok")),
        result.get("error_category"),
        ",".join(fps[:5]),
    )
    safe = dict(result)
    safe["invalid_token_fps"] = fps
    safe["invalid_tokens"] = fps
    return {
        **safe,
        "owner_abonados": owners,
        "device_tokens": len(tokens),
        "event": event,
        "ticket_id": tid,
        "ticket_event_id": teid,
    }
