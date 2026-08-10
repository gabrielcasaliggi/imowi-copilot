"""Cliente HTTP hacia el servicio Whisper local (Docker en :9000)."""

from __future__ import annotations

import logging

import httpx

from app.config import WHISPER_ENABLED, WHISPER_TIMEOUT_S, WHISPER_URL

logger = logging.getLogger("operations_hub")

MSG_AUDIO_FALLBACK = (
    "No pude escuchar bien el audio. ¿Me lo escribís en un mensajito de texto?"
)


def whisper_disponible() -> bool:
    return bool(WHISPER_ENABLED and (WHISPER_URL or "").strip())


def transcribir_audio(
    audio_bytes: bytes,
    *,
    filename: str = "audio.ogg",
    mime: str = "audio/ogg",
) -> str:
    """Envía audio al servicio Whisper. Vacío si está deshabilitado o falla."""
    if not whisper_disponible():
        logger.info("Whisper deshabilitado — omito transcripción")
        return ""
    if not audio_bytes:
        return ""

    url = WHISPER_URL.rstrip("/") + "/transcribe"
    try:
        with httpx.Client(timeout=WHISPER_TIMEOUT_S) as client:
            r = client.post(
                url,
                files={"file": (filename, audio_bytes, mime)},
            )
        if r.status_code >= 400:
            logger.warning("Whisper HTTP %s: %s", r.status_code, r.text[:300])
            return ""
        data = r.json() if r.content else {}
        text = str(data.get("text") or "").strip()
        return text[:4000]
    except Exception:
        logger.exception("Whisper transcribe falló url=%s", url)
        return ""


def texto_desde_audio_whatsapp(msg: dict) -> str | None:
    """Transcribe audio WA. None = no era audio; '' = falló / vacío."""
    tipo = (msg.get("type") or "").strip().lower()
    if tipo != "audio":
        return None
    if not whisper_disponible():
        return ""
    media = msg.get("audio") or {}
    media_id = str(media.get("id") or "").strip()
    if not media_id:
        return ""
    from app.services.whatsapp_client import descargar_media

    raw = descargar_media(media_id)
    if not raw:
        return ""
    mime = str(media.get("mime_type") or "audio/ogg").strip() or "audio/ogg"
    return transcribir_audio(raw, filename="voice.ogg", mime=mime)


def texto_desde_audio_telegram(message: dict) -> str | None:
    """Transcribe voice/audio TG. None = no era audio; '' = falló / vacío."""
    voice = message.get("voice") if isinstance(message.get("voice"), dict) else None
    audio = message.get("audio") if isinstance(message.get("audio"), dict) else None
    media = voice or audio
    if not media:
        return None
    if not whisper_disponible():
        return ""
    file_id = str(media.get("file_id") or "").strip()
    if not file_id:
        return ""
    from app.services.telegram_client import descargar_archivo

    raw = descargar_archivo(file_id)
    if not raw:
        return ""
    mime = "audio/ogg"
    filename = "voice.ogg"
    if audio and not voice:
        mime = str(audio.get("mime_type") or "audio/mpeg").strip() or "audio/mpeg"
        filename = str(audio.get("file_name") or "audio.mp3")
    return transcribir_audio(raw, filename=filename, mime=mime)
