"""Cliente WhatsApp Cloud API (Meta). Sin token: solo log / no-op."""

from __future__ import annotations

import logging

import httpx

from app.config import (
    WHATSAPP_PHONE_NUMBER_ID,
    WHATSAPP_TOKEN,
)

logger = logging.getLogger("operations_hub")

_GRAPH = "https://graph.facebook.com/v22.0"


def _wa_cfg() -> dict[str, str]:
    try:
        from app.estate.database import get_session_factory
        from app.services.platform_settings import resolve_whatsapp

        db = get_session_factory()()
        try:
            return resolve_whatsapp(db)
        finally:
            db.close()
    except Exception:
        return {
            "token": WHATSAPP_TOKEN,
            "phone_number_id": WHATSAPP_PHONE_NUMBER_ID,
            "verify_token": "",
            "app_secret": "",
            "default_org_slug": "",
        }


def whatsapp_configurado() -> bool:
    cfg = _wa_cfg()
    return bool(cfg.get("token") and cfg.get("phone_number_id"))


def normalizar_destino_wa(telefono: str) -> str:
    """Destino para Cloud API: solo dígitos; móviles AR como 549…"""
    to = "".join(c for c in (telefono or "") if c.isdigit())
    if not to:
        return ""
    # 54 + 10 dígitos nacionales sin el 9 de móvil → insertar 9 (WhatsApp AR)
    if to.startswith("54") and not to.startswith("549") and len(to) == 12:
        to = "549" + to[2:]
    return to


def verificar_credenciales() -> dict:
    """GET al Phone Number ID en Graph API (no envía mensaje)."""
    cfg = _wa_cfg()
    token = (cfg.get("token") or "").strip()
    phone_id = (cfg.get("phone_number_id") or "").strip()
    if not token or not phone_id:
        return {
            "ok": False,
            "error": "faltan token o phone_number_id",
            "phone_number_id_set": bool(phone_id),
            "token_set": bool(token),
        }
    url = (
        f"{_GRAPH}/{phone_id}"
        f"?fields=display_phone_number,verified_name,quality_rating,code_verification_status"
    )
    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.get(url, headers={"Authorization": f"Bearer {token}"})
        if r.status_code >= 400:
            detail = r.text[:400]
            logger.warning("WhatsApp verify creds error %s: %s", r.status_code, detail)
            return {
                "ok": False,
                "status": r.status_code,
                "error": detail,
                "phone_number_id": phone_id,
                "phone_number_id_set": True,
                "token_set": True,
            }
        data = r.json()
        return {
            "ok": True,
            "phone_number_id": phone_id,
            "phone_number_id_set": True,
            "token_set": True,
            "display_phone_number": data.get("display_phone_number") or "",
            "verified_name": data.get("verified_name") or "",
            "quality_rating": data.get("quality_rating") or "",
            "code_verification_status": data.get("code_verification_status") or "",
        }
    except Exception as e:
        logger.exception("WhatsApp verify creds failed")
        return {
            "ok": False,
            "error": str(e),
            "phone_number_id_set": True,
            "token_set": True,
        }


def _post_messages(payload: dict) -> dict:
    cfg = _wa_cfg()
    to = str(payload.get("to") or "")
    if not (cfg.get("token") and cfg.get("phone_number_id")):
        logger.info(
            "WhatsApp no configurado — mensaje simulado a %s type=%s",
            to,
            payload.get("type"),
        )
        return {"ok": True, "simulated": True, "to": to}
    url = f"{_GRAPH}/{cfg['phone_number_id']}/messages"
    headers = {
        "Authorization": f"Bearer {cfg['token']}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.post(url, json=payload, headers=headers)
        if r.status_code >= 400:
            logger.warning(
                "WhatsApp send error %s to=%s: %s",
                r.status_code,
                to,
                r.text[:300],
            )
            return {"ok": False, "status": r.status_code, "detail": r.text[:300], "to": to}
        data = r.json()
        mid = ""
        try:
            mid = data["messages"][0]["id"]
        except (KeyError, IndexError, TypeError):
            pass
        return {"ok": True, "meta_message_id": mid, "raw": data, "to": to}
    except Exception as e:
        logger.exception("WhatsApp send failed to=%s", to)
        return {"ok": False, "reason": str(e), "to": to}


def enviar_texto(telefono_e164: str, texto: str) -> dict:
    """Envía mensaje de texto. telefono sin + preferido (solo dígitos)."""
    to = normalizar_destino_wa(telefono_e164)
    if not to or not texto.strip():
        return {"ok": False, "reason": "destino_o_texto_vacio"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": texto[:4096]},
    }
    return _post_messages(payload)


def descargar_media(media_id: str) -> bytes:
    """Descarga bytes de un media_id de Cloud API (audio, imagen, etc.)."""
    mid = (media_id or "").strip()
    if not mid:
        return b""
    cfg = _wa_cfg()
    token = (cfg.get("token") or "").strip()
    if not token:
        logger.info("WhatsApp no configurado — no se puede descargar media %s", mid[:24])
        return b""
    headers = {"Authorization": f"Bearer {token}"}
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            meta = client.get(f"{_GRAPH}/{mid}", headers=headers)
            if meta.status_code >= 400:
                logger.warning(
                    "WhatsApp media meta error %s: %s",
                    meta.status_code,
                    meta.text[:300],
                )
                return b""
            url = str((meta.json() or {}).get("url") or "").strip()
            if not url:
                logger.warning("WhatsApp media sin url id=%s", mid[:24])
                return b""
            r = client.get(url, headers=headers)
            if r.status_code >= 400:
                logger.warning(
                    "WhatsApp media download error %s id=%s",
                    r.status_code,
                    mid[:24],
                )
                return b""
            return bytes(r.content or b"")
    except Exception:
        logger.exception("WhatsApp descargar_media falló id=%s", mid[:24])
        return b""


def enviar_encuesta_csat(telefono_e164: str, texto: str) -> dict:
    """Lista sutil 1–5 (WA no permite hover; máximo 3 reply buttons)."""
    to = normalizar_destino_wa(telefono_e164)
    if not to:
        return {"ok": False, "reason": "destino_vacio"}
    body = (texto or "").strip() or "¿Cómo calificarías la atención recibida hoy?"
    body_short = body[:1024]
    rows = [
        {"id": "1", "title": "☆☆☆☆☆", "description": "1 estrella"},
        {"id": "2", "title": "★★☆☆☆", "description": "2 estrellas"},
        {"id": "3", "title": "★★★☆☆", "description": "3 estrellas"},
        {"id": "4", "title": "★★★★☆", "description": "4 estrellas"},
        {"id": "5", "title": "★★★★★", "description": "5 estrellas"},
    ]
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": body_short},
            "action": {
                "button": "☆ Calificar",
                "sections": [{"title": "Elegí tu puntuación", "rows": rows}],
            },
        },
    }
    result = _post_messages(payload)
    if result.get("ok"):
        return result
    logger.warning("WhatsApp lista CSAT falló; fallback texto to=%s", to)
    return enviar_texto(telefono_e164, texto)
