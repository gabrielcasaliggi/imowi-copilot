FROM python:3.11-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt \
 && python -c "import edge_tts; print('edge-tts ok')"

COPY app.py .

# Por defecto: voz femenina argentina (Elena Neural). Sin PyTorch → ~poco RAM.
ENV TTS_ENGINE=edge
ENV TTS_VOICE=es-AR-ElenaNeural
ENV TTS_RATE=+0%
ENV TTS_PITCH=+0Hz
ENV TTS_MODEL_DIR=/models
ENV TTS_MAX_CHARS=800
ENV TTS_OPUS_BITRATE=64k

EXPOSE 9100

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9100"]
