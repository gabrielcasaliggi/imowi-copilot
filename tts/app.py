"""Servicio HTTP: texto → audio OGG Opus.

Motor por defecto: Microsoft Edge TTS — voz femenina argentina
`es-AR-ElenaNeural` (latam / rioplatense). Ligero, sin PyTorch.

Opcional offline: TTS_ENGINE=coqui + modelo Coqui (español CSS10, no AR).
API: POST /synthesize {"text":"..."} → audio/ogg
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import tempfile
import wave
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

logger = logging.getLogger("tts")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

MODEL_DIR = Path(os.getenv("TTS_MODEL_DIR", "/models")).resolve()
# edge = Elena AR (default) | coqui = VITS local (es-ES)
TTS_ENGINE = (os.getenv("TTS_ENGINE", "edge").strip().lower() or "edge")
# Voz Neural argentina femenina (Edge). Otras: es-AR-TomasNeural, es-MX-DaliaNeural, …
TTS_VOICE = (
    os.getenv("TTS_VOICE", "es-AR-ElenaNeural").strip() or "es-AR-ElenaNeural"
)
TTS_RATE = (os.getenv("TTS_RATE", "+0%").strip() or "+0%")
TTS_PITCH = (os.getenv("TTS_PITCH", "+0Hz").strip() or "+0Hz")
TTS_MODEL = (
    os.getenv("TTS_MODEL", "tts_models/es/css10/vits").strip()
    or "tts_models/es/css10/vits"
)
MAX_CHARS = int(os.getenv("TTS_MAX_CHARS", "800") or "800")
OPUS_BITRATE = os.getenv("TTS_OPUS_BITRATE", "64k").strip() or "64k"

_tts = None  # solo Coqui
_sample_rate = 24000
_ready = False


def _load_coqui():
    global _sample_rate
    os.environ.setdefault("COQUI_TOS_AGREED", "1")
    os.environ.setdefault("TTS_HOME", str(MODEL_DIR))
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    import numpy as np  # noqa: F401
    import torch  # noqa: F401
    import torchaudio  # noqa: F401
    from TTS.api import TTS

    logger.info("Cargando Coqui model=%s", TTS_MODEL)
    engine = TTS(model_name=TTS_MODEL, progress_bar=False)
    try:
        _sample_rate = int(engine.synthesizer.output_sample_rate)
    except Exception:
        _sample_rate = int(getattr(engine, "output_sample_rate", None) or 22050)
    logger.info("Coqui listo sr=%s", _sample_rate)
    return engine


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _tts, _ready, _sample_rate
    _ready = False
    _tts = None
    try:
        if TTS_ENGINE == "coqui":
            _tts = _load_coqui()
            _ready = _tts is not None
        else:
            # Probar edge-tts (import + lista de voces) sin sintetizar aún
            import edge_tts  # noqa: F401

            _sample_rate = 24000
            _ready = True
            logger.info(
                "Edge TTS listo voice=%s rate=%s pitch=%s (es-AR femenina)",
                TTS_VOICE,
                TTS_RATE,
                TTS_PITCH,
            )
    except Exception:
        logger.exception(
            "TTS no pudo iniciar engine=%s. ready=false (sin restart loop).",
            TTS_ENGINE,
        )
        _ready = False
        _tts = None
    yield
    _tts = None
    _ready = False


app = FastAPI(title="Eco TTS (es-AR)", lifespan=lifespan)


class SynthIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


@app.get("/health")
def health():
    return {
        "ok": True,
        "engine": TTS_ENGINE,
        "voice": TTS_VOICE if TTS_ENGINE == "edge" else None,
        "model": TTS_MODEL if TTS_ENGINE == "coqui" else None,
        "ready": _ready,
        "sample_rate": _sample_rate,
        "locale": "es-AR" if TTS_ENGINE == "edge" else "es",
    }


def _wav_to_ogg_opus(wav_or_media: Path, ogg_path: Path) -> None:
    """Anti-clip + fade + loudnorm + Opus (calidad audio, no voip)."""
    dur = 0.0
    try:
        if wav_or_media.suffix.lower() == ".wav":
            with wave.open(str(wav_or_media), "rb") as wf:
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
    af_parts.append("alimiter=limit=0.95:level=false")
    af_parts.append("loudnorm=I=-16:TP=-1.5:LRA=11")
    af = ",".join(af_parts)

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(wav_or_media),
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
    """Edge TTS → MP3 (Elena AR). Sync: /synthesize corre en threadpool."""
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


def _synthesize_coqui_wav(text: str, wav_path: Path) -> None:
    import numpy as np

    assert _tts is not None
    try:
        _tts.tts_to_file(text=text, file_path=str(wav_path))
        if wav_path.exists() and wav_path.stat().st_size > 1000:
            return
    except TypeError:
        pass

    wav = _tts.tts(text=text)
    arr = np.asarray(wav, dtype=np.float32)
    if arr.ndim > 1:
        arr = arr.reshape(-1)
    peak = float(np.max(np.abs(arr))) if arr.size else 0.0
    if peak > 0.99:
        arr = arr * (0.90 / peak)
    elif peak > 0.90:
        arr = arr * (0.90 / peak)
    pcm = np.clip(arr * 32767.0, -32768, 32767).astype(np.int16)
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(_sample_rate)
        wf.writeframes(pcm.tobytes())


@app.post("/synthesize")
def synthesize(body: SynthIn):
    if not _ready:
        raise HTTPException(503, "TTS no listo")
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(400, "texto vacío")
    if len(text) > MAX_CHARS:
        text = text[: MAX_CHARS - 1].rstrip() + "…"

    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            ogg_path = tmp_path / "out.ogg"
            if TTS_ENGINE == "coqui":
                wav_path = tmp_path / "out.wav"
                _synthesize_coqui_wav(text, wav_path)
                _wav_to_ogg_opus(wav_path, ogg_path)
            else:
                mp3_path = tmp_path / "out.mp3"
                _synthesize_edge_sync(text, mp3_path)
                if not mp3_path.exists() or mp3_path.stat().st_size < 64:
                    raise RuntimeError("edge-tts no generó audio")
                _wav_to_ogg_opus(mp3_path, ogg_path)
            data = ogg_path.read_bytes()
    except Exception as e:
        logger.exception("synthesize falló engine=%s", TTS_ENGINE)
        raise HTTPException(500, f"synthesize error: {e}") from e

    if not data:
        raise HTTPException(500, "audio vacío")
    return Response(content=data, media_type="audio/ogg")
