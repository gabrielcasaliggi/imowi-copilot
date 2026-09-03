# Roles y portal abonado — Cooperativa Batán

## Personas

| Rol | Cómo entra | Qué hace |
|-----|------------|----------|
| **Admin** | `admin` / `admin` | Todo: config, stats, reasignar hilos, ver colas |
| **Agente** | `batan` / `batan` | Bandeja + tickets N2 + KB |
| **Abonado** | `https://soporte.ecolan.com` o app nativa (`mobile/`) | Chat con Eko; si escala, agente toma el hilo |

WhatsApp Meta queda como canal de aviso; el soporte turno a turno vive en portal/app (sin costo por mensaje).

## Portal web

URL: `https://soporte.ecolan.com` (`/` = portal; `ibot.ecolan.com/portal` redirige acá)

1. Identificación por DNI + OTP / PIN  
2. Chat con bot N1 (`canal=web`)  
3. Escalamiento → cola de **Bandeja** para agentes  
4. Polling mientras espera / habla con agente  

API:

- `POST /api/v1/portal/auth/start` · `verify` · `login-pin`
- `POST /api/v1/portal/messages` (Bearer portal_token)
- `GET /api/v1/portal/conversations/{id}`

## App nativa

Cliente Expo en [`mobile/`](../mobile/README.md). Mismos endpoints, header `X-Canal: app`.

- Auth DNI + OTP (primera vez) y PIN después  
- Chat, voz (`POST /api/v1/portal/audio`) y push (`POST /api/v1/portal/devices`)  
- La bandeja muestra el hilo como **App**

## Consola

- Login: link “¿Sos abonado? Ir al portal”
- Nav agente: **Bandeja** (Web + futuros WA), tickets, conocimiento
- Admin: reasignar conversación desde la bandeja

## Demo abonado

| Teléfono | DNI | Nombre |
|----------|-----|--------|
| 5492235551234 | 30111222 | María González |
