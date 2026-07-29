"""Cliente WhatsApp Cloud API (Meta). Sin token: solo log / no-op."""

from __future__ import annotations

import logging

import httpx

from app.config import (
    WHATSAPP_PHONE_NUMBER_ID,
    WHATSAPP_TOKEN,
)

logger = logging.getLogger("operations_hub")

_GRAPH = "https://graph.facebook.com/v21.0"


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


def enviar_texto(telefono_e164: str, texto: str) -> dict:
    """Envía mensaje de texto. telefono sin + preferido (solo dígitos)."""
    to = "".join(c for c in (telefono_e164 or "") if c.isdigit())
    if not to or not texto.strip():
        return {"ok": False, "reason": "destino_o_texto_vacio"}
    cfg = _wa_cfg()
    if not (cfg.get("token") and cfg.get("phone_number_id")):
        logger.info("WhatsApp no configurado — mensaje simulado a %s: %s", to, texto[:120])
        return {"ok": True, "simulated": True, "to": to}

    url = f"{_GRAPH}/{cfg['phone_number_id']}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": texto[:4096]},
    }
    headers = {
        "Authorization": f"Bearer {cfg['token']}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.post(url, json=payload, headers=headers)
        if r.status_code >= 400:
            logger.warning("WhatsApp send error %s: %s", r.status_code, r.text[:300])
            return {"ok": False, "status": r.status_code, "detail": r.text[:300]}
        data = r.json()
        mid = ""
        try:
            mid = data["messages"][0]["id"]
        except (KeyError, IndexError, TypeError):
            pass
        return {"ok": True, "meta_message_id": mid, "raw": data}
    except Exception as e:
        logger.exception("WhatsApp send failed")
        return {"ok": False, "reason": str(e)}
