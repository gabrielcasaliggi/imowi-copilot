# Canal Telegram — guía operativa

## Producto

Bot N1 (Eco) + bandeja de agentes, mismo motor que WhatsApp/portal, vía **Telegram Bot API**.

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
  -d "url=https://ibot.ecolan.com/api/v1/telegram/webhook" \
  -d "secret_token=${TELEGRAM_WEBHOOK_SECRET}" \
  -d "allowed_updates=[\"message\"]"
```

3. Validar en Admin → Telegram → **Validar bot (getMe)**  
   o `POST /api/v1/admin/settings/test-telegram`

## Flujo

```
Telegram update (texto)
  → POST /api/v1/telegram/webhook
  → procesar_mensaje_entrante(canal=telegram, chat_id)
  → Eco N1 / handoff → Inbox
  → Reply agente → sendMessage(chat_id)
```

- Identidad: `chat_id` en `telefono` / `wa_id`, `session_id` = `tg:{org}:{chat_id}`
- MVP: solo mensajes de **texto** (stickers/fotos se ignoran)
- Simular sin bot: `POST /api/v1/inbox/simulate` con `"canal": "telegram"`

## Checklist prod

- [ ] Bot creado en BotFather y token cargado
- [ ] `TELEGRAM_WEBHOOK_SECRET` seteado y pasado a `setWebhook`
- [ ] Org slug correcta
- [ ] Mensaje real → respuesta Eco en Telegram
- [ ] Handoff visible en bandeja con label **Telegram**
- [ ] Reply del agente llega al chat de Telegram
