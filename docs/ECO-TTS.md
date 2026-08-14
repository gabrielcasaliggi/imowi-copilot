# Eco TTS — respuesta en audio por WhatsApp (Coqui VITS)

Cuando el abonado manda una **nota de voz** por WhatsApp, Eco responde en **audio**.  
Motor actual: **Coqui TTS** modelo `tts_models/es/css10/vits` (español, natural en CPU).  
Si TTS falla o el texto no es apto (URLs, muy largo), cae a texto.

## Por qué Coqui (y no Piper)

Piper era liviano pero sonaba robótico y, con Opus 24k “voip”, **pegaba el techo de volumen (0 dB)** → voz “cortada”.  
Coqui VITS español + Opus 64k + loudnorm/limiter suaviza picos y mejora naturalidad.

## Flujo

1. WA audio → Whisper (STT) → texto  
2. Motor N1 genera respuesta  
3. `texto_para_habla()` (marca, DNI, sin .com)  
4. Coqui → WAV → ffmpeg (fade + limiter + loudnorm) → OGG Opus 64k  
5. WhatsApp `type=audio`

## Levantar en el server

```bash
cd /opt/operations-hub
git pull origin main

# Parar el loop si está reiniciando
sudo docker compose -f docker-compose.tts.yml stop

# Rebuild CON cache limpia (instala torch CPU)
sudo docker compose -f docker-compose.tts.yml build --no-cache
sudo docker compose -f docker-compose.tts.yml up -d

sudo docker compose -f docker-compose.tts.yml logs -f --tail=80
# Esperar: "Coqui listo" / health ready=true

curl -s http://127.0.0.1:9100/health
```

Si ves `PyTorch was not found`, el build viejo quedó cacheado: repetí `build --no-cache`.

En `/opt/operations-hub/.env`:

```env
TTS_ENABLED=true
TTS_URL=http://127.0.0.1:9100
TTS_TIMEOUT_S=90
```

```bash
sudo systemctl restart operations-hub-api
```

**RAM:** reservar ~2–4 GB para el contenedor (`mem_limit: 4g` en el compose).

## Calidad / encode

| Antes (Piper) | Ahora (Coqui) |
|---------------|---------------|
| Opus 24k voip | Opus **64k** audio |
| Picos a 0 dB | limiter + loudnorm −1.5 dB TP |
| Voz robótica | VITS español CSS10 |

## DNI por audio

Sigue valiendo formato `24,914,867`, dígitos sueltos y palabras (“dos cuatro…”).

## Notas

- Solo WhatsApp; Inbox de agentes sigue en texto.  
- Mensajes con link / QR → texto.  
- XTTS (clon de voz) queda como upgrade futuro: mismo puerto, otro `TTS_MODEL`.
