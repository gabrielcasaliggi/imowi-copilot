"""Webhook WhatsApp Cloud API (Meta)."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.config import WHATSAPP_DEFAULT_ORG_SLUG, WHATSAPP_VERIFY_TOKEN, es_produccion
from app.estate import repository as repo
from app.estate.database import get_db, get_session_factory
from app.services.canal_abonado import procesar_mensaje_entrante
from app.services.platform_settings import resolve_whatsapp

logger = logging.getLogger("operations_hub")

router = APIRouter(tags=["WhatsApp"])


def _firma_valida(raw_body: bytes, signature_header: str | None, app_secret: str) -> bool:
    if not app_secret or not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    received = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)


def _extraer_texto_mensaje(msg: dict) -> str:
    """Extrae texto útil de distintos tipos de mensaje Cloud API."""
    tipo = (msg.get("type") or "").strip().lower()

    if tipo in ("text", "") or msg.get("text"):
        body = ((msg.get("text") or {}).get("body") or "").strip()
        if body:
            return body[:4000]

    if tipo == "button":
        body = ((msg.get("button") or {}).get("text") or "").strip()
        if body:
            return body[:4000]

    if tipo == "interactive":
        inter = msg.get("interactive") or {}
        sub = (inter.get("type") or "").strip().lower()
        if sub == "button_reply":
            body = ((inter.get("button_reply") or {}).get("title") or "").strip()
            if body:
                return body[:4000]
        if sub == "list_reply":
            lr = inter.get("list_reply") or {}
            # Preferir id (p.ej. CSAT "1"…"5"); fallback a título/descripción
            body = (lr.get("id") or lr.get("title") or lr.get("description") or "").strip()
            if body:
                return body[:4000]
        if sub == "nfm_reply":
            nfm = inter.get("nfm_reply") or {}
            body = (nfm.get("body") or nfm.get("response_json") or "").strip()
            if body:
                return body[:4000]

    # Captions de media
    for key in ("image", "video", "document", "audio"):
        if msg.get(key):
            cap = ((msg.get(key) or {}).get("caption") or "").strip()
            if cap:
                return cap[:4000]
            return f"[{key}]"

    return ""


def _procesar_payload_whatsapp(payload: dict, org_id: str, org_slug: str) -> None:
    """Procesa el payload fuera del request HTTP para devolver 200 a Meta al toque.

    Si Whisper/TTS tarda >~15–20s, Meta reintenta el mismo wamid y se dispara un loop
    de audios (p.ej. aviso «ya derivado» en espera_agente).
    """
    from app.estate import canal_repo as crepo
    from app.services.prompt_safety import clamp_message
    from app.services.transcription import (
        MSG_AUDIO_FALLBACK,
        texto_desde_audio_whatsapp,
    )
    from app.services.whatsapp_client import enviar_texto as enviar_texto_wa

    SessionLocal = get_session_factory()
    db = SessionLocal()
    procesados = 0
    omitidos = 0
    try:
        entries = payload.get("entry") or []
        for entry in entries:
            for change in entry.get("changes") or []:
                field = change.get("field") or ""
                value = change.get("value") or {}
                statuses = value.get("statuses") or []
                messages = value.get("messages") or []
                if statuses and not messages:
                    logger.warning(
                        "WhatsApp webhook solo statuses field=%s n=%s (ignorar; no es mensaje entrante)",
                        field,
                        len(statuses),
                    )
                    continue
                if not messages:
                    logger.warning(
                        "WhatsApp webhook sin messages field=%s keys=%s",
                        field,
                        sorted(value.keys()),
                    )
                    continue
                for msg in messages:
                    from_wa = msg.get("from") or ""
                    tipo = msg.get("type") or ""
                    mid = msg.get("id") or ""
                    if not from_wa:
                        omitidos += 1
                        logger.warning("WhatsApp msg sin from type=%s", tipo)
                        continue

                    if mid and crepo.inbound_meta_ya_procesado(db, org_id, mid):
                        omitidos += 1
                        logger.warning(
                            "WhatsApp msg duplicado omitido id=%s type=%s",
                            mid[:48],
                            tipo,
                        )
                        continue

                    if mid and not crepo.try_claim_inbound_meta(mid):
                        omitidos += 1
                        logger.warning(
                            "WhatsApp msg claim omitido (en vuelo) id=%s type=%s",
                            mid[:48],
                            tipo,
                        )
                        continue

                    stt_prompt = ""
                    if (tipo or "").strip().lower() == "audio":
                        try:
                            conv_hint = crepo.get_or_create_conversacion(
                                db,
                                org_id,
                                telefono=from_wa,
                                canal="whatsapp",
                                wa_id=from_wa,
                            )
                            ctx_hint = crepo.get_contexto(conv_hint)
                            if ctx_hint.get("pidio_dni"):
                                from app.services.transcription import WHISPER_PROMPT_DNI

                                stt_prompt = WHISPER_PROMPT_DNI
                        except Exception:
                            logger.exception(
                                "WhatsApp no pudo leer ctx para prompt DNI from=%s",
                                from_wa,
                            )

                    transcribed = texto_desde_audio_whatsapp(msg, prompt=stt_prompt)
                    if transcribed is not None:
                        text = (transcribed or "").strip()
                        if not text:
                            omitidos += 1
                            # Mantener claim: ya mandamos fallback; no reintentar el mismo wamid
                            logger.warning(
                                "WhatsApp audio sin transcripción usable id=%s",
                                mid[:48] if mid else "",
                            )
                            try:
                                enviar_texto_wa(from_wa, MSG_AUDIO_FALLBACK)
                            except Exception:
                                crepo.release_inbound_meta_claim(mid)
                                logger.exception(
                                    "WhatsApp fallback audio falló from=%s", from_wa
                                )
                            continue
                        logger.warning(
                            "WhatsApp audio transcrito from=%s chars=%s",
                            from_wa,
                            len(text),
                        )
                    else:
                        text = _extraer_texto_mensaje(msg)

                    if not text:
                        omitidos += 1
                        crepo.release_inbound_meta_claim(mid)
                        logger.warning(
                            "WhatsApp msg sin texto usable type=%s id=%s keys=%s",
                            tipo,
                            mid[:48] if mid else "",
                            sorted(msg.keys()),
                        )
                        continue
                    text = clamp_message(text, max_chars=4000)
                    if not text.strip():
                        omitidos += 1
                        crepo.release_inbound_meta_claim(mid)
                        continue
                    entrada_audio = transcribed is not None
                    try:
                        procesar_mensaje_entrante(
                            db,
                            org_id,
                            telefono=from_wa,
                            texto=text,
                            canal="whatsapp",
                            wa_id=from_wa,
                            meta_message_id=mid,
                            usar_llama=True,
                            entrada_audio=entrada_audio,
                        )
                        procesados += 1
                        logger.warning(
                            "WhatsApp msg procesado from=%s type=%s chars=%s org=%s",
                            from_wa,
                            tipo,
                            len(text),
                            org_slug,
                        )
                    except Exception:
                        omitidos += 1
                        crepo.release_inbound_meta_claim(mid)
                        logger.exception(
                            "WhatsApp fallo al procesar from=%s type=%s mid=%s",
                            from_wa,
                            tipo,
                            mid[:48] if mid else "",
                        )
    except Exception:
        logger.exception("Error procesando webhook WhatsApp")
    finally:
        db.close()
    logger.warning(
        "WhatsApp webhook done procesados=%s omitidos=%s org=%s",
        procesados,
        omitidos,
        org_slug,
    )


@router.get("/whatsapp/webhook")
def verify_webhook(
    hub_mode: str | None = Query(None, alias="hub.mode"),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(None, alias="hub.challenge"),
    db: Session = Depends(get_db),
):
    expected = resolve_whatsapp(db).get("verify_token") or WHATSAPP_VERIFY_TOKEN
    if hub_mode == "subscribe" and hub_verify_token == expected:
        return PlainTextResponse(content=hub_challenge or "")
    raise HTTPException(403, "Verify token inválido")


@router.post("/whatsapp/webhook")
async def receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    raw = await request.body()
    wa = resolve_whatsapp(db)
    secret = (wa.get("app_secret") or "").strip()

    if secret:
        sig = request.headers.get("x-hub-signature-256")
        if not _firma_valida(raw, sig, secret):
            raise HTTPException(403, "Firma inválida")
    elif es_produccion():
        logger.error("WhatsApp webhook sin WHATSAPP_APP_SECRET en production")
        raise HTTPException(503, "Webhook WhatsApp no configurado")

    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        raise HTTPException(400, "JSON inválido") from None

    org_slug = wa.get("default_org_slug") or WHATSAPP_DEFAULT_ORG_SLUG
    org = repo.get_org_by_slug(db, org_slug)
    if not org:
        logger.error("Org WhatsApp no encontrada: %s", org_slug)
        return {"status": "ok"}

    # 200 inmediato: Whisper + Coqui TTS no deben bloquear el ACK a Meta
    background_tasks.add_task(_procesar_payload_whatsapp, payload, org.id, org_slug)
    return {"status": "ok"}
