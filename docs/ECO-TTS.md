# Eco TTS — respuesta en audio por WhatsApp (voz femenina argentina)

Cuando el abonado manda una **nota de voz** por WhatsApp, Eco responde en **audio**.

## Voz (default)

| | |
|---|---|
| Motor | **Microsoft Edge TTS** (`edge-tts`) |
| Voz | **`es-AR-ElenaNeural`** — femenina, español argentino |
| Alternativa masculina | `es-AR-TomasNeural` |
| Offline | `TTS_ENGINE=coqui` (VITS `es/css10`, acento España; más RAM) |

Por qué no Coqui CSS10 para esto: ese modelo es español peninsular, no rioplatense.  
XTTS fine-tune AR existe, pero pide ~4–8 GB RAM / speaker reference — el server actual no lo bancá cómodo.

Edge TTS es liviano, rápido (menos riesgo de reintentos Meta) y suena natural en es-AR.

## Flujo

1. WA audio → Whisper (STT) → texto  
2. Motor N1 genera respuesta  
3. `texto_para_habla()` (marca, DNI, sin .com)  
4. Edge Elena → MP3 → ffmpeg (fade + limiter + loudnorm) → OGG Opus 64k  
5. WhatsApp `type=audio`

## Levantar en el server

```bash
cd /opt/operations-hub
git pull origin main

sudo docker compose -f docker-compose.tts.yml build --no-cache
sudo docker compose -f docker-compose.tts.yml up -d

curl -s http://127.0.0.1:9100/health
# {"engine":"edge","voice":"es-AR-ElenaNeural","ready":true,...}
```

El contenedor necesita **salida a Internet** (HTTPS a los endpoints de Edge).

En `/opt/operations-hub/.env`:

```env
TTS_ENABLED=true
TTS_URL=http://127.0.0.1:9100
TTS_TIMEOUT_S=45
```

Opcional (compose / env del contenedor):

```env
TTS_ENGINE=edge
TTS_VOICE=es-AR-ElenaNeural
# TTS_RATE=+5%
# TTS_PITCH=-2Hz
```

```bash
sudo systemctl restart operations-hub-api
```

**RAM:** Edge ~poco (compose `mem_limit: 1g`). Con 6 GB en el host sobra margen para API + Whisper + Next.  
XTTS fine-tune AR local queda viable más adelante si preferís offline 100 %.

## Notas

- Solo WhatsApp; Inbox de agentes sigue en texto.  
- Mensajes con link / QR → texto.  
- Avisos operativos (CSAT gracias, «ya derivado») **siempre en texto**; no TTS.  
- El webhook WA ACK’ea a Meta en background (evita reintentos mientras sintetiza).  
- Coqui / XTTS AR quedan como upgrade si más adelante hay GPU o más RAM.
