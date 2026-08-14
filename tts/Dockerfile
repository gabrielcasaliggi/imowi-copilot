FROM python:3.11-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        espeak-ng \
        libsndfile1 \
        git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

ENV TTS_MODEL=tts_models/es/css10/vits
ENV TTS_MODEL_DIR=/models
ENV TTS_MAX_CHARS=800
ENV TTS_OPUS_BITRATE=64k
ENV TTS_HOME=/models
ENV COQUI_TOS_AGREED=1
ENV NUMBA_CACHE_DIR=/tmp/numba

EXPOSE 9100

# Primera carga descarga el modelo VITS (~100MB+)
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9100"]
