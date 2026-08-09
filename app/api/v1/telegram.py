"""Webhook Telegram Bot API."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import TELEGRAM_DEFAULT_ORG_SLUG, es_produccion
from app.estate import repository as repo
from app.estate.database import get_db
from app.services.canal_abonado import procesar_mensaje_entrante
from app.services.platform_settings import resolve_telegram
from app.services.telegram_client import answer_callback_query

logger = logging.getLogger("operations_hub")

router = APIRouter(tags=["Telegram"])


def _secret_ok(header_value: str | None, expected: str) -> bool:
    if not expected:
        return True
    return (header_value or "").strip() == expected.strip()


@router.post("/telegram/webhook")
async def receive_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_telegram_bot_api_secret_token: str | None = Header(None),
):
    tg = resolve_telegram(db)
    secret = (tg.get("webhook_secret") or "").strip()

    if secret:
        if not _secret_ok(x_telegram_bot_api_secret_token, secret):
            raise HTTPException(403, "Secret token inválido")
    elif es_produccion():
        logger.error("Telegram webhook sin TELEGRAM_WEBHOOK_SECRET en production")
        raise HTTPException(503, "Webhook Telegram no configurado")

    try:
        payload = json.loads((await request.body()).decode("utf-8") or "{}")
    except json.JSONDecodeError:
        raise HTTPException(400, "JSON inválido") from None

    org_slug = tg.get("default_org_slug") or TELEGRAM_DEFAULT_ORG_SLUG
    org = repo.get_org_by_slug(db, org_slug)
    if not org:
        logger.error("Org Telegram no encontrada: %s", org_slug)
        return {"status": "ok"}

    try:
        # Botones inline CSAT — al tocar, iluminar ★ de 1…N y quitar teclado
        cq = payload.get("callback_query")
        if isinstance(cq, dict):
            cq_id = str(cq.get("id") or "")
            data = str(cq.get("data") or "").strip()
            msg = cq.get("message") or {}
            chat = msg.get("chat") or cq.get("from") or {}
            chat_id = chat.get("id")
            message_id = msg.get("message_id")
            from app.services.encuesta_satisfaccion import (
                parse_puntuacion,
                texto_encuesta_confirmacion,
            )
            from app.services.telegram_client import edit_message_text

            puntuacion = parse_puntuacion(data)
            if puntuacion:
                answer_callback_query(cq_id, text=f"{'★' * puntuacion}")
            else:
                answer_callback_query(cq_id, text="¡Gracias!")

            if chat_id is not None and data:
                from app.services.prompt_safety import clamp_message

                text = clamp_message(data, max_chars=64)
                result = procesar_mensaje_entrante(
                    db,
                    org.id,
                    telefono=str(chat_id),
                    texto=text,
                    canal="telegram",
                    wa_id=str(chat_id),
                    meta_message_id=f"cq:{cq_id}"[:80],
                    usar_llama=True,
                )
                if (
                    puntuacion
                    and message_id is not None
                    and isinstance(result, dict)
                    and result.get("ok")
                    and result.get("modo") == "encuesta"
                ):
                    edit_message_text(
                        str(chat_id),
                        message_id,
                        texto_encuesta_confirmacion(puntuacion),
                    )
            return {"status": "ok"}

        message = payload.get("message") or payload.get("edited_message")
        if not isinstance(message, dict):
            return {"status": "ok"}
        text = (message.get("text") or "").strip()
        if not text:
            # Ignorar stickers, fotos, etc. en el MVP
            return {"status": "ok"}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            return {"status": "ok"}
        mid = str(message.get("message_id") or "")
        from app.services.prompt_safety import clamp_message

        text = clamp_message(text, max_chars=4000)
        procesar_mensaje_entrante(
            db,
            org.id,
            telefono=str(chat_id),
            texto=text,
            canal="telegram",
            wa_id=str(chat_id),
            meta_message_id=mid,
            usar_llama=True,
        )
    except Exception:
        logger.exception("Error procesando webhook Telegram")
    return {"status": "ok"}
