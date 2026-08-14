FROM python:3.11-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        espeak-ng \
        libsndfile1 \
        git \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# PyTorch CPU primero (coqui-tts lo exige; pip genérico a veces no lo trae)
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir \
      torch==2.4.1 \
      torchaudio==2.4.1 \
      --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && python -c "import torch, torchaudio, TTS; print('torch', torch.__version__, 'ok')"

COPY app.py .

ENV TTS_MODEL=tts_models/es/css10/vits
ENV TTS_MODEL_DIR=/models
ENV TTS_MAX_CHARS=800
ENV TTS_OPUS_BITRATE=64k
ENV TTS_HOME=/models
ENV COQUI_TOS_AGREED=1
ENV NUMBA_CACHE_DIR=/tmp/numba

EXPOSE 9100

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9100"]
