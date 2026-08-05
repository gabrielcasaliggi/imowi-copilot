"""Cliente Telegram Bot API. Sin token: solo log / no-op."""

from __future__ import annotations

import logging

import httpx

from app.config import TELEGRAM_BOT_TOKEN

logger = logging.getLogger("operations_hub")

_API = "https://api.telegram.org"


def _tg_cfg() -> dict[str, str]:
    try:
        from app.estate.database import get_session_factory
        from app.services.platform_settings import resolve_telegram

        db = get_session_factory()()
        try:
            return resolve_telegram(db)
        finally:
            db.close()
    except Exception:
        return {
            "bot_token": TELEGRAM_BOT_TOKEN,
            "webhook_secret": "",
            "default_org_slug": "",
        }


def telegram_configurado() -> bool:
    return bool((_tg_cfg().get("bot_token") or "").strip())


def enviar_texto(chat_id: str, texto: str) -> dict:
    """Envía mensaje de texto a un chat_id de Telegram."""
    cid = str(chat_id or "").strip()
    if cid.startswith("tg:"):
        cid = cid[3:]
    if not cid or not (texto or "").strip():
        return {"ok": False, "reason": "destino_o_texto_vacio"}
    cfg = _tg_cfg()
    token = (cfg.get("bot_token") or "").strip()
    if not token:
        logger.info("Telegram no configurado — mensaje simulado a %s: %s", cid, texto[:120])
        return {"ok": True, "simulated": True, "to": cid}

    url = f"{_API}/bot{token}/sendMessage"
    payload = {
        "chat_id": cid,
        "text": texto[:4096],
        "disable_web_page_preview": True,
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.post(url, json=payload)
        if r.status_code >= 400:
            logger.warning("Telegram send error %s: %s", r.status_code, r.text[:300])
            return {"ok": False, "status": r.status_code, "detail": r.text[:300]}
        data = r.json()
        if not data.get("ok"):
            return {"ok": False, "detail": str(data.get("description") or data)[:300]}
        mid = ""
        try:
            mid = str(data["result"]["message_id"])
        except (KeyError, TypeError):
            pass
        return {"ok": True, "meta_message_id": mid, "raw": data}
    except Exception as e:
        logger.exception("Telegram send failed")
        return {"ok": False, "reason": str(e)}


def get_me() -> dict:
    """Valida el bot token contra getMe."""
    cfg = _tg_cfg()
    token = (cfg.get("bot_token") or "").strip()
    if not token:
        return {"ok": False, "reason": "bot_token_vacio"}
    url = f"{_API}/bot{token}/getMe"
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(url)
        data = r.json()
        if r.status_code >= 400 or not data.get("ok"):
            return {
                "ok": False,
                "status": r.status_code,
                "detail": str(data.get("description") or r.text)[:300],
            }
        result = data.get("result") or {}
        return {
            "ok": True,
            "id": result.get("id"),
            "username": result.get("username") or "",
            "first_name": result.get("first_name") or "",
        }
    except Exception as e:
        return {"ok": False, "reason": str(e)[:240]}
