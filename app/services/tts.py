"""Cliente HTTP hacia Piper TTS local (Docker en :9100)."""

from __future__ import annotations

import logging
import re

import httpx

from app.config import TTS_ENABLED, TTS_TIMEOUT_S, TTS_URL

logger = logging.getLogger("operations_hub")

# Textos con links o muy largos: mejor texto (QR, URLs, plantillas de pago)
_URL_RE = re.compile(r"https?://|www\.", re.I)


def tts_disponible() -> bool:
    return bool(TTS_ENABLED and (TTS_URL or "").strip())


def texto_apto_para_audio(texto: str) -> bool:
    t = (texto or "").strip()
    if not t or len(t) < 2:
        return False
    if _URL_RE.search(t):
        return False
    if len(t) > 800:
        return False
    return True


def sintetizar_audio(texto: str) -> bytes:
    """Texto → OGG Opus. Vacío si TTS off, texto no apto, o falla."""
    if not tts_disponible():
        return b""
    if not texto_apto_para_audio(texto):
        logger.info("TTS omitido (texto no apto para audio) chars=%s", len(texto or ""))
        return b""

    url = TTS_URL.rstrip("/") + "/synthesize"
    try:
        with httpx.Client(timeout=TTS_TIMEOUT_S) as client:
            r = client.post(url, json={"text": texto.strip()[:800]})
        if r.status_code >= 400:
            logger.warning("TTS HTTP %s: %s", r.status_code, (r.text or "")[:300])
            return b""
        data = bytes(r.content or b"")
        if len(data) < 64:
            logger.warning("TTS audio demasiado corto (%s bytes)", len(data))
            return b""
        return data
    except Exception:
        logger.exception("TTS synthesize falló url=%s", url)
        return b""
