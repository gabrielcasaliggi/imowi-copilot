"""Servicio HTTP: texto → audio con Coqui TTS (español VITS) → OGG Opus.

Calidad superior a Piper. Misma API: POST /synthesize → audio/ogg
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import wave
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

logger = logging.getLogger("tts")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

MODEL_DIR = Path(os.getenv("TTS_MODEL_DIR", "/models")).resolve()
# Español VITS (CSS10) — natural en CPU. Alt: tts_models/multilingual/multi-dataset/xtts_v2 (más pesado)
TTS_MODEL = (
    os.getenv("TTS_MODEL", "tts_models/es/css10/vits").strip()
    or "tts_models/es/css10/vits"
)
MAX_CHARS = int(os.getenv("TTS_MAX_CHARS", "800") or "800")
OPUS_BITRATE = os.getenv("TTS_OPUS_BITRATE", "64k").strip() or "64k"

_tts = None
_sample_rate = 22050


def _load_tts():
    global _sample_rate
    os.environ.setdefault("COQUI_TOS_AGREED", "1")
    os.environ.setdefault("TTS_HOME", str(MODEL_DIR))
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    from TTS.api import TTS

    logger.info("Cargando Coqui model=%s (puede demorar la 1ª vez)", TTS_MODEL)
    engine = TTS(model_name=TTS_MODEL, progress_bar=False)
    # sample rate del modelo
    try:
        _sample_rate = int(engine.synthesizer.output_sample_rate)
    except Exception:
        try:
            _sample_rate = int(getattr(engine, "output_sample_rate", None) or 22050)
        except Exception:
            _sample_rate = 22050
    logger.info("Coqui listo sr=%s", _sample_rate)
    return engine


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _tts
    _tts = _load_tts()
    yield
    _tts = None


app = FastAPI(title="Coqui TTS (es)", lifespan=lifespan)


class SynthIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


@app.get("/health")
def health():
    return {
        "ok": True,
        "engine": "coqui",
        "model": TTS_MODEL,
        "ready": _tts is not None,
        "sample_rate": _sample_rate,
    }


def _synthesize_wav_file(text: str, wav_path: Path) -> None:
    assert _tts is not None
    # API: lista de floats o escribe a archivo
    try:
        _tts.tts_to_file(text=text, file_path=str(wav_path))
        if wav_path.exists() and wav_path.stat().st_size > 1000:
            return
    except TypeError:
        # algunas versiones no aceptan file_path igual
        pass

    wav = _tts.tts(text=text)
    arr = np.asarray(wav, dtype=np.float32)
    if arr.ndim > 1:
        arr = arr.reshape(-1)
    # clip suave antes de int16
    peak = float(np.max(np.abs(arr))) if arr.size else 0.0
    if peak > 0.99:
        arr = arr * (0.90 / peak)
    elif peak > 0:
        arr = arr * min(1.0, 0.90 / peak) if peak > 0.90 else arr
    pcm = np.clip(arr * 32767.0, -32768, 32767).astype(np.int16)
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(_sample_rate)
        wf.writeframes(pcm.tobytes())


def _wav_to_ogg_opus(wav_path: Path, ogg_path: Path) -> None:
    """Anti-clip + fade + loudnorm + Opus de calidad (no voip 24k)."""
    # Duración para fade-out
    dur = 0.0
    try:
        with wave.open(str(wav_path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate() or 1
            dur = frames / float(rate)
    except Exception:
        dur = 0.0
    fade_out_st = max(0.0, dur - 0.12) if dur > 0.25 else 0.0

    af_parts = [
        "apad=pad_dur=0.18",
        "afade=t=in:st=0:d=0.06",
    ]
    if fade_out_st > 0:
        af_parts.append(f"afade=t=out:st={fade_out_st:.3f}:d=0.10")
    # Limitar picos (el Piper viejo llegaba a 0 dB y “cortaba”)
    af_parts.append("alimiter=limit=0.95:level=false")
    af_parts.append("loudnorm=I=-16:TP=-1.5:LRA=11")
    af = ",".join(af_parts)

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(wav_path),
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


@app.post("/synthesize")
def synthesize(body: SynthIn):
    if _tts is None:
        raise HTTPException(503, "TTS no listo")
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(400, "texto vacío")
    if len(text) > MAX_CHARS:
        text = text[: MAX_CHARS - 1].rstrip() + "…"

    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            wav_path = tmp_path / "out.wav"
            ogg_path = tmp_path / "out.ogg"
            _synthesize_wav_file(text, wav_path)
            _wav_to_ogg_opus(wav_path, ogg_path)
            data = ogg_path.read_bytes()
    except Exception as e:
        logger.exception("synthesize falló")
        raise HTTPException(500, f"synthesize error: {e}") from e

    if not data:
        raise HTTPException(500, "audio vacío")
    return Response(content=data, media_type="audio/ogg")
