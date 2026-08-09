# Canal Telegram — guía operativa

## Producto

Bot N1 (Eko) + bandeja de agentes, mismo motor que WhatsApp/portal, vía **Telegram Bot API**.

## Configuración

Variables de entorno (o Admin → Settings → Telegram):

| Variable | Uso |
|----------|-----|
| `TELEGRAM_BOT_TOKEN` | Token de [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_WEBHOOK_SECRET` | Secret token del webhook (header `X-Telegram-Bot-Api-Secret-Token`) |
| `TELEGRAM_DEFAULT_ORG_SLUG` | Cooperativa que recibe los mensajes (ej. `coop-batan`) |

En producción el webhook **exige** `TELEGRAM_WEBHOOK_SECRET`.

## Webhook

1. Exponer HTTPS: `https://<host>/api/v1/telegram/webhook`
2. Registrar con Bot API:

```bash
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{
    \"url\": \"https://ibot.ecolan.com/api/v1/telegram/webhook\",
    \"secret_token\": \"${TELEGRAM_WEBHOOK_SECRET}\",
    \"allowed_updates\": [\"message\", \"edited_message\", \"callback_query\"]
  }"
```

> **Importante:** si `allowed_updates` solo tiene `"message"`, Telegram **nunca** entrega los toques de botones inline (encuesta CSAT). Hay que incluir `callback_query`.

También desde Admin: **Registrar webhook CSAT** (`POST /api/v1/admin/settings/telegram-webhook`).

Verificar:

```bash
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo" | jq .
# allowed_updates debe incluir callback_query (o estar vacío = todos)
```

3. Validar en Admin → Telegram → **Validar bot (getMe)**  
   o `POST /api/v1/admin/settings/test-telegram`

## Flujo

```
Telegram update (texto | callback_query)
  → POST /api/v1/telegram/webhook
  → texto: procesar_mensaje_entrante(canal=telegram, chat_id)
  → callback csat:N: guardar voto + editar mensaje ★★★☆☆
  → Eko N1 / handoff → Inbox
  → Reply agente → sendMessage(chat_id)
```

- Identidad: `chat_id` en `telefono` / `wa_id`, `session_id` = `tg:{org}:{chat_id}`
- MVP texto: stickers/fotos se ignoran
- Encuesta CSAT: **ReplyKeyboard** `☆ 1`…`☆ 5` (mensaje de texto; no depende de `callback_query`)
- Simular sin bot: `POST /api/v1/inbox/simulate` con `"canal": "telegram"`

## Checklist prod

- [ ] Bot creado en BotFather y token cargado
- [ ] `TELEGRAM_WEBHOOK_SECRET` seteado y pasado a `setWebhook`
- [ ] `allowed_updates` incluye `callback_query` (encuesta)
- [ ] Org slug correcta
- [ ] Mensaje real → respuesta Eko en Telegram
- [ ] Handoff visible en bandeja con label **Telegram**
- [ ] Reply del agente llega al chat de Telegram
- [ ] Encuesta ☆ → mensaje se edita a ★ y queda en estadísticas