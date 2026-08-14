FROM python:3.11-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt \
 && python -c "import edge_tts; print('edge-tts ok')"

COPY app.py .

# Voz femenina argentina (rioplatense). Sin PyTorch / sin Coqui.
ENV TTS_VOICE=es-AR-ElenaNeural
ENV TTS_FORCE_FEMALE=true
ENV TTS_RATE=+0%
ENV TTS_PITCH=+0Hz
ENV TTS_MAX_CHARS=800
ENV TTS_OPUS_BITRATE=64k

EXPOSE 9100

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -fsS http://127.0.0.1:9100/health | grep -q es-AR-ElenaNeural || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9100"]
