# Eco TTS — respuesta en audio por WhatsApp

Cuando el abonado manda una **nota de voz** por WhatsApp, Eco responde en **audio** (Piper local). Si TTS falla o el texto no es apto (URLs, mensajes muy largos), cae a texto.

## Flujo

1. WA audio → Whisper (STT) → texto  
2. Motor N1 genera respuesta  
3. Si el turno entró como audio → normalización hablada → Piper (TTS) → OGG Opus → WhatsApp `type=audio`  
4. Fallback: texto

## Calidad de voz

- Piper con `length_scale` un poco más lento (menos “robot apurado”).
- Antes de sintetizar, `texto_para_habla()`:
  - “soy Eco, de Soporte Batán…” → “soy Eco, el asistente de la Cooperativa Batán”
  - `DNI` → “de ene i”; sin dominios `.com`/`.coop`
  - Mensajes de audio acotados (~420 caracteres)

## DNI por audio

El STT a menudo manda `24,914,867`, `24 914 867` o “dos cuatro nueve…”. El extractor acepta formato AR, dígitos sueltos y palabras numéricas.

## Levantar Piper

```bash
docker compose -f docker-compose.tts.yml up -d --build
curl -s http://localhost:9100/health
```

## Config API (`.env` del hub)

```env
TTS_ENABLED=true
TTS_URL=http://localhost:9100
TTS_TIMEOUT_S=45
```

Reiniciar `operations-hub-api` tras editar `.env`. Si cambió `tts/app.py`, rebuild del contenedor.

## Notas

- Solo WhatsApp; Telegram sigue en texto.
- Mensajes con link o muy largos → texto (p. ej. QR de pago).
- Agentes en Inbox siguen respondiendo en texto.
