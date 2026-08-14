# Eco TTS — voz femenina argentina (rioplatense)

Cuando el abonado manda una **nota de voz** por WhatsApp, Eco responde en **audio** con:

| | |
|---|---|
| Motor | Microsoft Edge TTS (`edge-tts`) |
| Voz | **`es-AR-ElenaNeural`** — femenina, **es-AR** |
| Acento | Argentino / rioplatense |

**No** se usa Coqui `css10` (español de España, tono masculino). Si escuchás esa voz, el contenedor viejo sigue vivo: hay que **recrear** (abajo).

## Deploy (obligatorio recreate)

```bash
cd /opt/operations-hub
git pull origin main

# Tirar el Coqui viejo (nombre anterior) y el nuevo
sudo docker compose -f docker-compose.tts.yml down
sudo docker rm -f operations-hub-tts-elena-ar 2>/dev/null || true
# por si quedó el servicio viejo sin container_name:
sudo docker ps -a | grep -i tts || true

sudo docker compose -f docker-compose.tts.yml build --no-cache
sudo docker compose -f docker-compose.tts.yml up -d --force-recreate

curl -s http://127.0.0.1:9100/health
# Debe decir:
#   "voice":"es-AR-ElenaNeural"
#   "gender":"Female"
#   "locale":"es-AR"
#   "ready":true

# Probar audio (Elena diciendo una frase argentina):
curl -s -X POST http://127.0.0.1:9100/synthesize \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hola, soy Eco, la asistente de la Cooperativa Batán. ¿Cómo andás?"}' \
  -o /tmp/elena.ogg
# Escuchá /tmp/elena.ogg — tiene que sonar mujer argentina, no hombre de España.

sudo systemctl restart operations-hub-api
```

El contenedor necesita **salida HTTPS** a Microsoft. Si `ready:false`, mirá:
`sudo docker compose -f docker-compose.tts.yml logs --tail=80`

## .env del API

```env
TTS_ENABLED=true
TTS_URL=http://127.0.0.1:9100
TTS_TIMEOUT_S=45
```

No hace falta `TTS_ENGINE` / `TTS_MODEL` (Coqui quedó fuera).

## Flujo

1. WA audio → Whisper → texto  
2. N1 genera respuesta  
3. `texto_para_habla()`  
4. Edge Elena → MP3 → ffmpeg → OGG Opus  
5. WhatsApp `type=audio`

## Notas

- Solo WhatsApp; inbox agentes en texto.  
- Avisos operativos (CSAT / «ya derivado») en texto, sin TTS.  
- Webhook ACK en background.  
- Con 6 GB RAM en el host, Edge deja margen de sobra; XTTS AR local queda como upgrade offline futuro.
