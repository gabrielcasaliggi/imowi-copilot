"""Servicio HTTP mínimo: audio → texto con faster-whisper (CPU)."""

from __future__ import annotations

import logging
import os
import tempfile
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

logger = logging.getLogger("whisper")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base").strip() or "base"
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu").strip() or "cpu"
WHISPER_COMPUTE = os.getenv("WHISPER_COMPUTE_TYPE", "int8").strip() or "int8"
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "es").strip() or "es"
MAX_BYTES = int(os.getenv("WHISPER_MAX_BYTES", str(5 * 1024 * 1024)) or str(5 * 1024 * 1024))

_model = None


def _load_model():
    from faster_whisper import WhisperModel

    logger.info(
        "Cargando faster-whisper model=%s device=%s compute=%s",
        WHISPER_MODEL,
        WHISPER_DEVICE,
        WHISPER_COMPUTE,
    )
    return WhisperModel(WHISPER_MODEL, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _model
    _model = _load_model()
    logger.info("Whisper listo")
    yield
    _model = None


app = FastAPI(title="Whisper STT", lifespan=lifespan)


@app.get("/health")
def health():
    return {"ok": True, "model": WHISPER_MODEL, "ready": _model is not None}


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    if _model is None:
        raise HTTPException(503, "Modelo no cargado")

    data = await file.read()
    if not data:
        raise HTTPException(400, "Archivo vacío")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"Audio supera {MAX_BYTES} bytes")

    suffix = ".ogg"
    name = (file.filename or "").lower()
    if name.endswith(".opus"):
        suffix = ".opus"
    elif name.endswith(".mp3"):
        suffix = ".mp3"
    elif name.endswith(".wav"):
        suffix = ".wav"
    elif name.endswith(".m4a"):
        suffix = ".m4a"
    elif name.endswith(".webm"):
        suffix = ".webm"

    path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(data)
            path = tmp.name
        segments, info = _model.transcribe(
            path,
            language=WHISPER_LANGUAGE,
            vad_filter=True,
            beam_size=1,
        )
        text = " ".join((s.text or "").strip() for s in segments).strip()
        logger.info(
            "transcribe ok lang=%s duration=%.1fs chars=%s",
            getattr(info, "language", "?"),
            float(getattr(info, "duration", 0) or 0),
            len(text),
        )
        return JSONResponse({"text": text, "language": getattr(info, "language", WHISPER_LANGUAGE)})
    except Exception as exc:
        logger.exception("transcribe falló")
        raise HTTPException(500, f"Transcripción falló: {exc}") from exc
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass
