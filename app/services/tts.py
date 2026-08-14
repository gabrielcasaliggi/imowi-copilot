"""Cliente HTTP hacia Piper TTS local (Docker en :9100)."""

from __future__ import annotations

import logging
import re

import httpx

from app.config import TTS_ENABLED, TTS_TIMEOUT_S, TTS_URL

logger = logging.getLogger("operations_hub")

# Textos con links o muy largos: mejor texto (QR, URLs, plantillas de pago)
_URL_RE = re.compile(r"https?://|www\.", re.I)
_DOMAIN_RE = re.compile(
    r"\b[\w-]+\.(?:com|coop|ar|net|org|io)\b",
    re.IGNORECASE,
)


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


def texto_para_habla(texto: str) -> str:
    """Normaliza copy para TTS: menos robótico, sin dominios, siglas pronunciables."""
    t = (texto or "").strip()
    if not t:
        return ""

    # Quitar markdown / bullets
    t = t.replace("*", "").replace("_", " ").replace("#", " ")
    t = re.sub(r"https?://\S+", " ", t)
    t = _DOMAIN_RE.sub(" ", t)

    # Marca / producto → forma hablada (evita “batan punto com”)
    reemplazos = [
        (r"\bSoporte\s+Bat[aá]n\b", "Soporte Batán"),
        (r"\bCooperativa\s+Bat[aá]n\s*/\s*Ecolan\b", "Cooperativa Batán"),
        (r"\bBat[aá]n\s*/\s*Ecolan\b", "Batán"),
        (r"\bN\.?\s*º\b", "número"),
        (r"\bN°\b", "número"),
        (r"\bDNI\b", "de ene i"),
        (r"\bIMOWI\b", "Imowi"),
        (r"\bFTTH\b", "fibra"),
        (r"\bWi-?Fi\b", "wifi"),
        (r"\bQR\b", "código QR"),
        (r"\bOV\b", "oficina virtual"),
    ]
    for pat, rep in reemplazos:
        t = re.sub(pat, rep, t, flags=re.IGNORECASE)

    # “soy Eco/Eko, de Soporte Batán …” → asistente de la cooperativa
    t = re.sub(
        r"\bsoy\s+(Eco|Eko)\s*,\s*de\s+Soporte\s+Bat[aá]n\b",
        r"soy \1, el asistente de la Cooperativa Batán",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(
        r"\bsoy\s+(Eco|Eko)\s*,\s*de\s+Cooperativa\s+Bat[aá]n\b",
        r"soy \1, el asistente de la Cooperativa Batán",
        t,
        flags=re.IGNORECASE,
    )
    # Sobra “(Cooperativa Batán)” repetido tras el reemplazo
    t = re.sub(
        r"(asistente de la Cooperativa Batán)\s*\(\s*Cooperativa\s+Bat[aá]n\s*\)",
        r"\1",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(r"\(\s*Cooperativa\s+Bat[aá]n\s*\)", "", t, flags=re.IGNORECASE)

    # Pausas naturales
    t = t.replace(" / ", ", ")
    t = t.replace("/", ", ")
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\s+,", ",", t)
    # Evitar mensajes eternamente largos en audio
    if len(t) > 420:
        t = t[:417].rsplit(" ", 1)[0].rstrip(",.;:") + "."
    return t


def sintetizar_audio(texto: str) -> bytes:
    """Texto → OGG Opus. Vacío si TTS off, texto no apto, o falla."""
    if not tts_disponible():
        return b""
    if not texto_apto_para_audio(texto):
        logger.info("TTS omitido (texto no apto para audio) chars=%s", len(texto or ""))
        return b""

    hablado = texto_para_habla(texto)
    if not hablado:
        return b""

    url = TTS_URL.rstrip("/") + "/synthesize"
    try:
        with httpx.Client(timeout=TTS_TIMEOUT_S) as client:
            r = client.post(url, json={"text": hablado[:800]})
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
