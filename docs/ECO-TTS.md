# Eco TTS — respuesta en audio por WhatsApp

Cuando el abonado manda una **nota de voz** por WhatsApp, Eco responde en **audio** (Piper local). Si TTS falla o el texto no es apto (URLs, mensajes muy largos), cae a texto.

## Flujo

1. WA audio → Whisper (STT) → texto  
2. Motor N1 genera respuesta  
3. Si el turno entró como audio → Piper (TTS) → OGG Opus → WhatsApp `type=audio`  
4. Fallback: texto

## Levantar Piper

```bash
docker compose -f docker-compose.tts.yml up -d --build
curl -s http://localhost:9100/health
```

La primera vez descarga la voz (~modelo ONNX) en el volumen `tts-models`.

## Config API (`.env` del hub)

```env
TTS_ENABLED=true
TTS_URL=http://localhost:9100
TTS_TIMEOUT_S=45
```

Reiniciar `operations-hub-api` después de cambiar env.

## Voces

Default: `es_MX-claude-high` (override con `TTS_VOICE` en el compose).

Opciones en `tts/app.py`: `es_MX-claude-medium`, `es_ES-mls_10246-low` (más liviana).

## Notas

- Solo WhatsApp; Telegram sigue en texto (se puede extender igual).
- Mensajes con `http://` o >800 caracteres → texto (p. ej. QR de pago).
- Agentes en Inbox siguen respondiendo en texto.
