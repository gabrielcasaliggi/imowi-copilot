"""Cliente HTTP hacia el servicio Whisper local (Docker en :9000)."""

from __future__ import annotations

import logging
import re

import httpx

from app.config import WHISPER_ENABLED, WHISPER_TIMEOUT_S, WHISPER_URL

logger = logging.getLogger("operations_hub")

MSG_AUDIO_FALLBACK = (
    "No pude escuchar bien el audio. ¿Me lo escribís en un mensajito de texto?"
)

# Sesgo STT cuando el bot acaba de pedir DNI (WhatsApp audio).
WHISPER_PROMPT_DNI = (
    "Documento nacional de identidad DNI argentino de siete u ocho dígitos. "
    "Números: cero, uno, dos, tres, cuatro, cinco, seis, siete, ocho, nueve. "
    "Separador de miles con punto o coma."
)

# Sesgo STT genérico: pagos, deuda y corte (audios fuera del pedido de DNI).
WHISPER_PROMPT_FACTURACION = (
    "Consulta de facturación, pago, deuda, saldo, aviso de pago, corte por mora. "
    "Todavía no pagué, no pagué, me cortaron el servicio, falta de pago."
)


def normalizar_texto_audio_stt(texto: str) -> str:
    """Corrige errores frecuentes de Whisper en audios de abonados (sin LLM)."""
    t = (texto or "").strip()
    if not t:
        return t
    low = t.lower()
    # «todo bien nos pague» ≈ «todavía no pagué»
    if "todo bien" in low and re.search(r"\b(nos\s+)?pague?\b", low):
        t = re.sub(
            r"todo\s+bien.*?pague?\b",
            "todavía no pagué",
            t,
            count=1,
            flags=re.IGNORECASE,
        )
    elif re.search(r"\bnos\s+pague?\b", low) and any(
        k in low
        for k in (
            "cort",
            "servicio",
            "internet",
            "pasa",
            "sé",
            "se ",
            "si ",
            "sí ",
            "deuda",
            "factura",
        )
    ):
        t = re.sub(r"\bnos\s+pague?\b", "no pagué", t, count=1, flags=re.IGNORECASE)
    return t.strip()


def whisper_disponible() -> bool:
    return bool(WHISPER_ENABLED and (WHISPER_URL or "").strip())


def transcribir_audio(
    audio_bytes: bytes,
    *,
    filename: str = "audio.ogg",
    mime: str = "audio/ogg",
    prompt: str = "",
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
            data = {}
            hint = (prompt or "").strip()
            if hint:
                data["prompt"] = hint[:500]
            r = client.post(
                url,
                files={"file": (filename, audio_bytes, mime)},
                data=data,
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


def texto_desde_audio_whatsapp(msg: dict, *, prompt: str = "") -> str | None:
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
    return transcribir_audio(raw, filename="voice.ogg", mime=mime, prompt=prompt)


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
