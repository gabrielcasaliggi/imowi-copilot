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
from app.services.telegram_client import answer_callback_query, edit_message_text

logger = logging.getLogger("operations_hub")

router = APIRouter(tags=["Telegram"])


def _secret_ok(header_value: str | None, expected: str) -> bool:
    if not expected:
        return True
    return (header_value or "").strip() == expected.strip()


def _handle_csat_callback(db: Session, org_id: str, cq: dict) -> None:
    """Procesa botón ☆ CSAT: guarda voto y edita el mensaje a ★★★☆☆."""
    from app.services.encuesta_satisfaccion import (
        capturar_voto_telegram,
        parse_puntuacion,
        texto_encuesta_confirmacion,
    )

    cq_id = str(cq.get("id") or "")
    data = str(cq.get("data") or "").strip()
    msg = cq.get("message") if isinstance(cq.get("message"), dict) else {}
    chat = msg.get("chat") if isinstance(msg.get("chat"), dict) else {}
    if not chat:
        from_user = cq.get("from") if isinstance(cq.get("from"), dict) else {}
        # fallback raro: sin message.chat
        chat = {"id": from_user.get("id")} if from_user.get("id") is not None else {}
    chat_id = chat.get("id")
    message_id = msg.get("message_id")
    puntuacion = parse_puntuacion(data)

    # Siempre ACK para quitar el spinner del cliente
    if puntuacion:
        answer_callback_query(cq_id, text=f"{'★' * puntuacion}")
    else:
        answer_callback_query(cq_id, text="OK")
        logger.info("Telegram callback no-CSAT data=%r", data[:80])
        return

    if chat_id is None:
        logger.warning("CSAT callback sin chat_id")
        return

    try:
        result = capturar_voto_telegram(
            db,
            org_id,
            chat_id=str(chat_id),
            puntuacion=int(puntuacion),
            meta_message_id=f"cq:{cq_id}"[:80],
        )
        logger.info(
            "CSAT Telegram chat=%s score=%s ok=%s reason=%s",
            chat_id,
            puntuacion,
            result.get("ok"),
            result.get("reason"),
        )
    except Exception:
        logger.exception("CSAT Telegram falló al guardar voto chat=%s", chat_id)
        result = {"ok": False}

    # Feedback visual SIEMPRE: iluminar 1…N y sacar botones
    if message_id is not None:
        edited = edit_message_text(
            str(chat_id),
            message_id,
            texto_encuesta_confirmacion(int(puntuacion)),
        )
        if not edited.get("ok") and not edited.get("simulated"):
            logger.warning(
                "CSAT editMessage falló chat=%s mid=%s detail=%s",
                chat_id,
                message_id,
                (edited.get("detail") or edited.get("reason") or "")[:200],
            )


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
        # Log del tipo de update (ayuda a diagnosticar webhooks sin callback_query)
        if payload.get("callback_query"):
            logger.info("Telegram update=callback_query")
        elif payload.get("message"):
            logger.info(
                "Telegram update=message text=%r",
                str((payload.get("message") or {}).get("text") or "")[:40],
            )

        cq = payload.get("callback_query")
        if isinstance(cq, dict):
            _handle_csat_callback(db, org.id, cq)
            return {"status": "ok"}

        message = payload.get("message") or payload.get("edited_message")
        if not isinstance(message, dict):
            return {"status": "ok"}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            return {"status": "ok"}
        mid = str(message.get("message_id") or "")

        from app.services.prompt_safety import clamp_message
        from app.services.telegram_client import enviar_texto as enviar_texto_tg
        from app.services.transcription import (
            MSG_AUDIO_FALLBACK,
            texto_desde_audio_telegram,
        )

        transcribed = texto_desde_audio_telegram(message)
        if transcribed is not None:
            text = (transcribed or "").strip()
            if not text:
                logger.warning("Telegram audio sin transcripción usable chat=%s", chat_id)
                enviar_texto_tg(str(chat_id), MSG_AUDIO_FALLBACK)
                return {"status": "ok"}
            logger.info("Telegram audio transcrito chat=%s chars=%s", chat_id, len(text))
        else:
            text = (message.get("text") or "").strip()
            if not text:
                return {"status": "ok"}

        text = clamp_message(text, max_chars=4000)
        result = procesar_mensaje_entrante(
            db,
            org.id,
            telefono=str(chat_id),
            texto=text,
            canal="telegram",
            wa_id=str(chat_id),
            meta_message_id=mid,
            usar_llama=True,
        )
        if isinstance(result, dict) and result.get("modo") == "encuesta":
            logger.info(
                "CSAT Telegram (texto) chat=%s score=%s ok=%s",
                chat_id,
                result.get("puntuacion"),
                result.get("ok"),
            )
    except Exception:
        logger.exception("Error procesando webhook Telegram")
    return {"status": "ok"}
