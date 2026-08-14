"""Servicio HTTP: texto → audio (Piper TTS) en OGG Opus para WhatsApp."""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

logger = logging.getLogger("tts")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

MODEL_DIR = Path(os.getenv("TTS_MODEL_DIR", "/models")).resolve()
# Voz española (MX) — buena calidad en CPU. Override con TTS_VOICE.
TTS_VOICE = os.getenv("TTS_VOICE", "es_MX-claude-high").strip() or "es_MX-claude-high"
MAX_CHARS = int(os.getenv("TTS_MAX_CHARS", "800") or "800")

# Rel paths bajo rhasspy/piper-voices
_VOICE_HF: dict[str, tuple[str, str]] = {
    "es_MX-claude-high": (
        "es/es_MX/claude/high/es_MX-claude-high.onnx",
        "es/es_MX/claude/high/es_MX-claude-high.onnx.json",
    ),
    "es_MX-claude-medium": (
        "es/es_MX/claude/medium/es_MX-claude-medium.onnx",
        "es/es_MX/claude/medium/es_MX-claude-medium.onnx.json",
    ),
    "es_ES-mls_10246-low": (
        "es/es_ES/mls_10246/low/es_ES-mls_10246-low.onnx",
        "es/es_ES/mls_10246/low/es_ES-mls_10246-low.onnx.json",
    ),
}

_voice = None


def _hf_url(rel: str) -> str:
    return f"https://huggingface.co/rhasspy/piper-voices/resolve/main/{rel}"


def _ensure_voice_files(name: str) -> tuple[Path, Path]:
    if name not in _VOICE_HF:
        raise RuntimeError(f"Voz TTS desconocida: {name}. Opciones: {sorted(_VOICE_HF)}")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    onnx_rel, json_rel = _VOICE_HF[name]
    onnx_path = MODEL_DIR / Path(onnx_rel).name
    json_path = MODEL_DIR / Path(json_rel).name
    for path, rel in ((onnx_path, onnx_rel), (json_path, json_rel)):
        if path.exists() and path.stat().st_size > 1000:
            continue
        url = _hf_url(rel)
        logger.info("Descargando voz Piper %s → %s", name, path.name)
        urllib.request.urlretrieve(url, path)  # noqa: S310 — URL fija HF
    return onnx_path, json_path


def _load_voice():
    from piper import PiperVoice

    onnx_path, _json_path = _ensure_voice_files(TTS_VOICE)
    logger.info("Cargando Piper voice=%s path=%s", TTS_VOICE, onnx_path)
    return PiperVoice.load(str(onnx_path))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _voice
    _voice = _load_voice()
    logger.info("TTS Piper listo voice=%s", TTS_VOICE)
    yield
    _voice = None


app = FastAPI(title="Piper TTS", lifespan=lifespan)


class SynthIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


@app.get("/health")
def health():
    return {"ok": True, "voice": TTS_VOICE, "ready": _voice is not None}


def _wav_to_ogg_opus(wav_path: Path, ogg_path: Path) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(wav_path),
        "-c:a",
        "libopus",
        "-b:a",
        "24k",
        "-vbr",
        "on",
        "-application",
        "voip",
        str(ogg_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg falló: {(proc.stderr or '')[-400:]}")


def _synthesize_wav(text: str, wav_path: Path) -> None:
    import wave

    with wave.open(str(wav_path), "wb") as wav_file:
        # API nueva: synthesize_wav; legacy: synthesize(text, wav_file)
        if hasattr(_voice, "synthesize_wav"):
            _voice.synthesize_wav(text, wav_file)
        else:
            _voice.synthesize(text, wav_file)


@app.post("/synthesize")
def synthesize(body: SynthIn):
    if _voice is None:
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
            _synthesize_wav(text, wav_path)
            _wav_to_ogg_opus(wav_path, ogg_path)
            data = ogg_path.read_bytes()
    except Exception as e:
        logger.exception("synthesize falló")
        raise HTTPException(500, f"synthesize error: {e}") from e

    if not data:
        raise HTTPException(500, "audio vacío")
    return Response(content=data, media_type="audio/ogg")
