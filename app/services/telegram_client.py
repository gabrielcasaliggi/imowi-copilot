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


def _normalize_chat_id(chat_id: str) -> str:
    cid = str(chat_id or "").strip()
    if cid.startswith("tg:"):
        cid = cid[3:]
    return cid


def enviar_texto(chat_id: str, texto: str, *, reply_markup: dict | None = None) -> dict:
    """Envía mensaje de texto a un chat_id de Telegram."""
    cid = _normalize_chat_id(chat_id)
    if not cid or not (texto or "").strip():
        return {"ok": False, "reason": "destino_o_texto_vacio"}
    cfg = _tg_cfg()
    token = (cfg.get("bot_token") or "").strip()
    if not token:
        logger.info("Telegram no configurado — mensaje simulado a %s: %s", cid, texto[:120])
        return {"ok": True, "simulated": True, "to": cid}

    url = f"{_API}/bot{token}/sendMessage"
    payload: dict = {
        "chat_id": cid,
        "text": texto[:4096],
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
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


def enviar_encuesta_csat(chat_id: str, texto: str) -> dict:
    """Teclado de respuesta ☆1…☆5 (mensaje normal).

    Usa ReplyKeyboard — no InlineKeyboard — porque muchos webhooks
    históricos solo reciben allowed_updates=[message] y nunca ven callback_query.
    Al tocar, Telegram envía el texto del botón como mensaje del usuario.
    """
    body = (texto or "").strip() or "¿Cómo calificarías la atención recibida hoy?"
    body = f"{body}\n\n☆☆☆☆☆\nElegí una opción abajo."
    keyboard = {
        "keyboard": [
            [
                {"text": "☆ 1"},
                {"text": "☆ 2"},
                {"text": "☆ 3"},
                {"text": "☆ 4"},
                {"text": "☆ 5"},
            ]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True,
        "input_field_placeholder": "Elegí 1 a 5",
    }
    return enviar_texto(chat_id, body, reply_markup=keyboard)


def quitar_teclado(chat_id: str, texto: str) -> dict:
    """Envía texto y oculta el teclado de respuesta."""
    return enviar_texto(
        chat_id,
        texto,
        reply_markup={"remove_keyboard": True},
    )


def edit_message_text(
    chat_id: str,
    message_id: int | str,
    texto: str,
    *,
    reply_markup: dict | None = None,
) -> dict:
    """Edita un mensaje (p. ej. iluminar estrellas CSAT tras el voto)."""
    cid = _normalize_chat_id(chat_id)
    mid = str(message_id or "").strip()
    if not cid or not mid or not (texto or "").strip():
        return {"ok": False, "reason": "params_vacios"}
    cfg = _tg_cfg()
    token = (cfg.get("bot_token") or "").strip()
    if not token:
        return {"ok": True, "simulated": True}
    url = f"{_API}/bot{token}/editMessageText"
    payload: dict = {
        "chat_id": cid,
        "message_id": int(mid) if mid.isdigit() else mid,
        "text": texto[:4096],
        "disable_web_page_preview": True,
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    else:
        payload["reply_markup"] = {"inline_keyboard": []}
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.post(url, json=payload)
        data = r.json() if r.content else {}
        if r.status_code >= 400 or not data.get("ok"):
            return {
                "ok": False,
                "status": r.status_code,
                "detail": str(data.get("description") or r.text)[:300],
            }
        return {"ok": True, "raw": data}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:240]}


def answer_callback_query(callback_query_id: str, text: str = "") -> dict:
    """ACK de callback_query (quita el spinner del botón)."""
    cfg = _tg_cfg()
    token = (cfg.get("bot_token") or "").strip()
    cq = str(callback_query_id or "").strip()
    if not token or not cq:
        return {"ok": False, "reason": "token_o_id_vacio"}
    url = f"{_API}/bot{token}/answerCallbackQuery"
    payload = {"callback_query_id": cq}
    if text:
        payload["text"] = text[:200]
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.post(url, json=payload)
        data = r.json() if r.content else {}
        if r.status_code >= 400 or not data.get("ok"):
            return {
                "ok": False,
                "status": r.status_code,
                "detail": str(data.get("description") or r.text)[:300],
            }
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:240]}


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


# Updates que el bot necesita recibir (CSAT usa callback_query)
TELEGRAM_ALLOWED_UPDATES = ["message", "edited_message", "callback_query"]


def get_webhook_info() -> dict:
    cfg = _tg_cfg()
    token = (cfg.get("bot_token") or "").strip()
    if not token:
        return {"ok": False, "reason": "bot_token_vacio"}
    url = f"{_API}/bot{token}/getWebhookInfo"
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(url)
        data = r.json()
        if r.status_code >= 400 or not data.get("ok"):
            return {
                "ok": False,
                "detail": str(data.get("description") or r.text)[:300],
            }
        result = data.get("result") or {}
        return {
            "ok": True,
            "url": result.get("url") or "",
            "has_custom_certificate": bool(result.get("has_custom_certificate")),
            "pending_update_count": result.get("pending_update_count") or 0,
            "last_error_date": result.get("last_error_date"),
            "last_error_message": result.get("last_error_message") or "",
            "max_connections": result.get("max_connections"),
            "allowed_updates": result.get("allowed_updates") or [],
        }
    except Exception as e:
        return {"ok": False, "reason": str(e)[:240]}


def set_webhook(url: str, *, secret_token: str = "", drop_pending: bool = False) -> dict:
    """Registra webhook incluyendo callback_query (botones CSAT)."""
    cfg = _tg_cfg()
    token = (cfg.get("bot_token") or "").strip()
    if not token:
        return {"ok": False, "reason": "bot_token_vacio"}
    target = (url or "").strip()
    if not target.startswith("https://"):
        return {"ok": False, "reason": "url_debe_ser_https"}
    secret = (secret_token or cfg.get("webhook_secret") or "").strip()
    api = f"{_API}/bot{token}/setWebhook"
    # application/json para pasar allowed_updates como lista real
    payload: dict = {
        "url": target,
        "allowed_updates": TELEGRAM_ALLOWED_UPDATES,
        "drop_pending_updates": bool(drop_pending),
    }
    if secret:
        payload["secret_token"] = secret
    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.post(api, json=payload)
        data = r.json() if r.content else {}
        if r.status_code >= 400 or not data.get("ok"):
            return {
                "ok": False,
                "status": r.status_code,
                "detail": str(data.get("description") or r.text)[:300],
            }
        info = get_webhook_info()
        return {
            "ok": True,
            "description": data.get("description") or "Webhook set",
            "url": target,
            "allowed_updates": TELEGRAM_ALLOWED_UPDATES,
            "webhook_info": info,
        }
    except Exception as e:
        return {"ok": False, "reason": str(e)[:240]}

