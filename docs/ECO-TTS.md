# Eco TTS — voz femenina argentina (rioplatense)

## Cómo funciona (prod)

La API sintetiza **en proceso** con Microsoft Edge TTS:

| | |
|---|---|
| Backend | `TTS_BACKEND=edge` (default) |
| Voz | **`es-AR-ElenaNeural`** — femenina, es-AR |
| Formato | MP3 → WhatsApp `audio/mpeg` |

**Ya no depende del contenedor Docker en :9100.** Ese puerto a menudo seguía sirviendo Coqui CSS10 (voz masculina de España) aunque hubieras levantado Elena.

El contenedor `docker-compose.tts.yml` queda **opcional** (`TTS_BACKEND=http`).

## Deploy

```bash
cd /opt/operations-hub
git fetch origin main && git checkout -- . && git pull origin main

# Instalar edge-tts en el venv de la API
sudo -u soporte .venv/bin/pip install -r requirements.txt

# .env — obligatorio:
#   TTS_ENABLED=true
#   TTS_BACKEND=edge
#   TTS_VOICE=es-AR-ElenaNeural
# (podés borrar o ignorar TTS_URL)

# Opcional: apagar el TTS Docker viejo para que no confunda
sudo docker compose -f docker-compose.tts.yml down

sudo systemctl restart operations-hub-api

# Probar desde el host (misma voz que WA):
sudo -u soporte .venv/bin/python - <<'PY'
from app.services.tts import sintetizar_audio, mime_y_filename_tts
b = sintetizar_audio("Hola, soy Eco, la asistente de la Cooperativa Batán. ¿Cómo andás?")
open("/tmp/elena-api.mp3","wb").write(b)
print("bytes", len(b), "mime", mime_y_filename_tts())
PY
# Escuchá /tmp/elena-api.mp3 — mujer argentina
```

Logs esperados al mandar audio por WA:
`TTS edge synthesize voice=es-AR-ElenaNeural chars=...`

## Notas

- El servidor necesita **salida HTTPS** (Edge).  
- Avisos CSAT / «ya derivado» siguen en texto.  
- Webhook WA ACK en background.  
- Contenedor Elena (`operations-hub-tts-elena-ar`) solo si preferís `TTS_BACKEND=http`.
