"""Servicio HTTP: texto → audio OGG Opus.

Voz fija: Microsoft Edge TTS **es-AR-ElenaNeural** (femenina, argentino / rioplatense).
No usa Coqui CSS10 (español de España, tono masculino).
API: POST /synthesize {"text":"..."} → audio/ogg
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

logger = logging.getLogger("tts")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Única voz soportada en prod: femenina argentina
DEFAULT_VOICE = "es-AR-ElenaNeural"
ALLOWED_VOICES = frozenset(
    {
        "es-AR-ElenaNeural",  # femenina AR (default)
        "es-AR-TomasNeural",  # masculina AR (solo si se pide explícito)
    }
)

TTS_VOICE = (os.getenv("TTS_VOICE", DEFAULT_VOICE).strip() or DEFAULT_VOICE)
if TTS_VOICE not in ALLOWED_VOICES:
    logger.warning(
        "TTS_VOICE=%s no es es-AR; forzando %s",
        TTS_VOICE,
        DEFAULT_VOICE,
    )
    TTS_VOICE = DEFAULT_VOICE

# Preferir siempre femenina salvo override explícito a Tomas
_force_female = (os.getenv("TTS_FORCE_FEMALE", "true").strip().lower() or "true") in (
    "1",
    "true",
    "yes",
    "on",
)
if _force_female and TTS_VOICE != DEFAULT_VOICE:
    logger.warning("TTS_FORCE_FEMALE: %s → %s", TTS_VOICE, DEFAULT_VOICE)
    TTS_VOICE = DEFAULT_VOICE

TTS_RATE = (os.getenv("TTS_RATE", "+0%").strip() or "+0%")
TTS_PITCH = (os.getenv("TTS_PITCH", "+0Hz").strip() or "+0Hz")
MAX_CHARS = int(os.getenv("TTS_MAX_CHARS", "800") or "800")
OPUS_BITRATE = os.getenv("TTS_OPUS_BITRATE", "64k").strip() or "64k"

_sample_rate = 24000
_ready = False
_voice_meta: dict = {}


def _resolve_voice_meta(voices: list) -> dict:
    for v in voices:
        if (v.get("ShortName") or "") == TTS_VOICE:
            return {
                "short_name": v.get("ShortName"),
                "gender": v.get("Gender"),
                "locale": v.get("Locale"),
                "friendly_name": v.get("FriendlyName"),
            }
    return {}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _ready, _sample_rate, _voice_meta
    _ready = False
    _voice_meta = {}
    try:
        import edge_tts

        voices = await edge_tts.list_voices()
        meta = _resolve_voice_meta(voices)
        if not meta:
            raise RuntimeError(
                f"Voz {TTS_VOICE} no disponible en Edge TTS (¿sin red saliente?)"
            )
        locale = (meta.get("locale") or "").upper()
        gender = (meta.get("gender") or "").lower()
        if not locale.startswith("ES-AR"):
            raise RuntimeError(f"Voz no es es-AR: {meta}")
        if _force_female and gender != "female":
            raise RuntimeError(f"Se exige voz femenina; got {meta}")

        _voice_meta = meta
        _sample_rate = 24000
        _ready = True
        logger.info(
            "TTS listo engine=edge voice=%s gender=%s locale=%s (rioplatense)",
            TTS_VOICE,
            meta.get("gender"),
            meta.get("locale"),
        )
    except Exception:
        logger.exception("TTS no pudo iniciar. ready=false")
        _ready = False
    yield
    _ready = False


app = FastAPI(title="Eco TTS es-AR Elena", lifespan=lifespan)


class SynthIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


@app.get("/health")
def health():
    return {
        "ok": True,
        "engine": "edge",
        "voice": TTS_VOICE,
        "gender": _voice_meta.get("gender"),
        "locale": _voice_meta.get("locale") or "es-AR",
        "ready": _ready,
        "sample_rate": _sample_rate,
        "accent": "rioplatense-ar",
    }


def _media_to_ogg_opus(media_path: Path, ogg_path: Path) -> None:
    """Fade + loudnorm + Opus calidad."""
    af = ",".join(
        [
            "apad=pad_dur=0.18",
            "afade=t=in:st=0:d=0.06",
            "alimiter=limit=0.95:level=false",
            "loudnorm=I=-16:TP=-1.5:LRA=11",
        ]
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(media_path),
        "-af",
        af,
        "-c:a",
        "libopus",
        "-b:a",
        OPUS_BITRATE,
        "-vbr",
        "on",
        "-application",
        "audio",
        "-ar",
        "48000",
        "-ac",
        "1",
        str(ogg_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg falló: {(proc.stderr or '')[-500:]}")


def _synthesize_edge_sync(text: str, media_path: Path) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(
        text,
        TTS_VOICE,
        rate=TTS_RATE,
        pitch=TTS_PITCH,
    )
    if hasattr(communicate, "save_sync"):
        communicate.save_sync(str(media_path))
    else:
        asyncio.run(communicate.save(str(media_path)))


@app.post("/synthesize")
def synthesize(body: SynthIn):
    if not _ready:
        raise HTTPException(503, "TTS no listo (voz es-AR Elena)")
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(400, "texto vacío")
    if len(text) > MAX_CHARS:
        text = text[: MAX_CHARS - 1].rstrip() + "…"

    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            mp3_path = tmp_path / "out.mp3"
            ogg_path = tmp_path / "out.ogg"
            _synthesize_edge_sync(text, mp3_path)
            if not mp3_path.exists() or mp3_path.stat().st_size < 64:
                raise RuntimeError("edge-tts no generó audio")
            _media_to_ogg_opus(mp3_path, ogg_path)
            data = ogg_path.read_bytes()
    except Exception as e:
        logger.exception("synthesize falló voice=%s", TTS_VOICE)
        raise HTTPException(500, f"synthesize error: {e}") from e

    if not data:
        raise HTTPException(500, "audio vacío")
    return Response(
        content=data,
        media_type="audio/ogg",
        headers={
            "X-TTS-Voice": TTS_VOICE,
            "X-TTS-Locale": "es-AR",
        },
    )
