"""TTS para WhatsApp: voz femenina argentina (Edge es-AR-ElenaNeural).

Por defecto sintetiza **en el proceso de la API** (no depende del contenedor :9100,
que a menudo seguía sirviendo Coqui CSS10 masculino de España).

Backend:
  TTS_BACKEND=edge  → edge-tts in-process (default, recomendado)
  TTS_BACKEND=http  → POST a TTS_URL/synthesize (contenedor opcional)
"""

from __future__ import annotations

import asyncio
import logging
import re
import tempfile
from pathlib import Path

import httpx

from app.config import (
    TTS_BACKEND,
    TTS_ENABLED,
    TTS_TIMEOUT_S,
    TTS_URL,
    TTS_VOICE,
)

logger = logging.getLogger("operations_hub")

_URL_RE = re.compile(r"https?://|www\.", re.I)
_DOMAIN_RE = re.compile(
    r"\b[\w-]+\.(?:com|coop|ar|net|org|io)\b",
    re.IGNORECASE,
)

# Solo voces es-AR; default femenina
_DEFAULT_VOICE = "es-AR-ElenaNeural"
_ALLOWED = frozenset({"es-AR-ElenaNeural", "es-AR-TomasNeural"})


def _voice() -> str:
    v = (TTS_VOICE or "").strip() or _DEFAULT_VOICE
    if v not in _ALLOWED:
        logger.warning("TTS_VOICE=%s inválida; usando %s", v, _DEFAULT_VOICE)
        return _DEFAULT_VOICE
    return v


def tts_disponible() -> bool:
    if not TTS_ENABLED:
        return False
    backend = (TTS_BACKEND or "edge").strip().lower()
    if backend == "http":
        return bool((TTS_URL or "").strip())
    return True  # edge in-process


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

    t = t.replace("*", "").replace("_", " ").replace("#", " ")
    t = re.sub(r"https?://\S+", " ", t)
    t = _DOMAIN_RE.sub(" ", t)

    # Frases de identificación antes que la sigla suelta
    reemplazos = [
        (r"\bSoporte\s+Bat[aá]n\b", "Soporte Batán"),
        (r"\bCooperativa\s+Bat[aá]n\s*/\s*Ecolan\b", "Cooperativa Batán"),
        (r"\bBat[aá]n\s*/\s*Ecolan\b", "Batán"),
        (r"\bN\.?\s*º\b", "número"),
        (r"\bN°\b", "número"),
        # DNI: Edge AR lee "DNI o" como "DN O" — preferir "documento"
        (
            r"\btu\s+D\.?\s*N\.?\s*I\.?\s+o\s+n[uú]mero\s+de\s+socio\b",
            "tu documento, o tu número de socio",
        ),
        (
            r"\bD\.?\s*N\.?\s*I\.?\s+o\s+n[uú]mero\s+de\s+socio\b",
            "documento o número de socio",
        ),
        (
            r"\bD\.?\s*N\.?\s*I\.?\s*/\s*N\.?\s*º?\s*de\s*socio\b",
            "documento o número de socio",
        ),
        (
            r"\bpasame\s+(el\s+)?D\.?\s*N\.?\s*I\.?\b",
            "pasame el documento",
        ),
        (
            r"\benviame\s+tu\s+D\.?\s*N\.?\s*I\.?\b",
            "enviame tu documento",
        ),
        (
            r"\bel\s+D\.?\s*N\.?\s*I\.?\s+del\s+titular\b",
            "el documento del titular",
        ),
        (
            r"\botro\s+D\.?\s*N\.?\s*I\.?\b",
            "otro documento",
        ),
        (r"\bD\.?\s*N\.?\s*I\.?\b", "documento"),
        (r"\bCUIT\b", "cuit"),
        (r"\bCUIL\b", "cuil"),
        (r"\bIMOWI\b", "i mó ui"),
        (r"\bimovi\b", "i mó ui"),
        (r"\bFTTH\b", "fibra"),
        (r"\bPPPoE\b", "pe pe pe o e"),
        (r"\bWi-?Fi\b", "wifi"),
        (r"\bQR\b", "código QR"),
        (r"\bOV\b", "oficina virtual"),
        (r"\bN\.?\s*º\s*de\s*socio\b", "número de socio"),
        # Nombre del bot: "Eko"/"Eco" → acento en la E (Ée-co), no en la O
        (r"\bEko\b", "Ée-co"),
        (r"\bEco\b", "Ée-co"),
        (r"\bÉco\b", "Ée-co"),
    ]
    for pat, rep in reemplazos:
        t = re.sub(pat, rep, t, flags=re.IGNORECASE)

    # Voz femenina Elena: concordancia
    t = re.sub(r"\bel asistente\b", "la asistente", t, flags=re.IGNORECASE)
    t = re.sub(
        r"\bsoy\s+Ée-?co\s*,\s*de\s+Soporte\s+Bat[aá]n\b",
        "soy Ée-co, la asistente de la Cooperativa Batán",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(
        r"\bsoy\s+Ée-?co\s*,\s*de\s+Cooperativa\s+Bat[aá]n\b",
        "soy Ée-co, la asistente de la Cooperativa Batán",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(
        r"(asistente de la Cooperativa Batán)\s*\(\s*Cooperativa\s+Bat[aá]n\s*\)",
        r"\1",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(r"\(\s*Cooperativa\s+Bat[aá]n\s*\)", "", t, flags=re.IGNORECASE)

    t = t.replace(" / ", ", ")
    t = t.replace("/", ", ")

    # $1234,56 / $ 1.234,56 → «1.234,56 pesos» (evitar que TTS diga "dólares")
    def _pesos_ars(m: re.Match[str]) -> str:
        num = m.group(1).rstrip(".")
        return f"{num} pesos"

    t = re.sub(r"\$\s*([\d.,]+)", _pesos_ars, t)
    t = re.sub(r"\bUSD\b", "pesos", t, flags=re.IGNORECASE)
    t = re.sub(r"\bd[oó]lares?\b", "pesos", t, flags=re.IGNORECASE)
    t = re.sub(r"\bpesos\s+pesos\b", "pesos", t, flags=re.IGNORECASE)

    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\s+,", ",", t)
    if len(t) > 420:
        t = t[:417].rsplit(" ", 1)[0].rstrip(",.;:") + "."
    return t


def _edge_mp3(texto: str) -> bytes:
    """Sintetiza MP3 con Edge TTS (Elena AR)."""
    import edge_tts

    voice = _voice()
    logger.warning("TTS edge synthesize voice=%s chars=%s", voice, len(texto))

    async def _run(path: Path) -> None:
        communicate = edge_tts.Communicate(texto, voice)
        await communicate.save(str(path))

    with tempfile.TemporaryDirectory() as tmp:
        mp3 = Path(tmp) / "out.mp3"
        try:
            communicate = edge_tts.Communicate(texto, voice)
            if hasattr(communicate, "save_sync"):
                communicate.save_sync(str(mp3))
            else:
                asyncio.run(_run(mp3))
        except Exception:
            logger.exception("edge-tts falló voice=%s", voice)
            return b""
        if not mp3.exists() or mp3.stat().st_size < 64:
            logger.warning("edge-tts audio vacío voice=%s", voice)
            return b""
        return mp3.read_bytes()


def _http_audio(texto: str) -> bytes:
    url = TTS_URL.rstrip("/") + "/synthesize"
    try:
        with httpx.Client(timeout=TTS_TIMEOUT_S) as client:
            r = client.post(url, json={"text": texto[:800]})
        if r.status_code >= 400:
            logger.warning("TTS HTTP %s: %s", r.status_code, (r.text or "")[:300])
            return b""
        data = bytes(r.content or b"")
        if len(data) < 64:
            logger.warning("TTS audio demasiado corto (%s bytes)", len(data))
            return b""
        # Loguear voz del contenedor si manda header
        v = (r.headers.get("X-TTS-Voice") or "").strip()
        if v:
            logger.warning("TTS http voice_header=%s", v)
        return data
    except Exception:
        logger.exception("TTS synthesize falló url=%s", url)
        return b""


def sintetizar_audio(texto: str) -> bytes:
    """Texto → audio (MP3 Edge o OGG del contenedor). Vacío si off/falla."""
    if not tts_disponible():
        return b""
    if not texto_apto_para_audio(texto):
        logger.info("TTS omitido (texto no apto para audio) chars=%s", len(texto or ""))
        return b""

    hablado = texto_para_habla(texto)
    if not hablado:
        return b""

    backend = (TTS_BACKEND or "edge").strip().lower()
    if backend == "http":
        return _http_audio(hablado)
    return _edge_mp3(hablado)


def mime_y_filename_tts() -> tuple[str, str]:
    """MIME/filename según backend (Edge → mpeg; contenedor → ogg)."""
    backend = (TTS_BACKEND or "edge").strip().lower()
    if backend == "http":
        return "audio/ogg", "voice.ogg"
    return "audio/mpeg", "voice.mp3"
