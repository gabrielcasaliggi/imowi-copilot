# Roles y portal abonado — Cooperativa Batán

## Personas

| Rol | Cómo entra | Qué hace |
|-----|------------|----------|
| **Admin** | `admin` / `admin` | Todo: config, stats, reasignar hilos, ver colas |
| **Agente** | `batan` / `batan` | Bandeja + tickets N2 + KB |
| **Abonado** | `/portal` (sin usuario de consola) | Chat con bot; si escala, agente toma el hilo |

WhatsApp Meta queda para una fase posterior (número de producción).

## Portal web

URL: `/portal`

1. Identificación por teléfono y/o DNI  
2. Chat con bot N1 (`canal=web`)  
3. Escalamiento → cola de **Bandeja** para agentes  
4. Polling mientras espera / habla con agente  

API:

- `POST /api/v1/portal/session`
- `POST /api/v1/portal/messages` (Bearer portal_token)
- `GET /api/v1/portal/conversations/{id}`

## Consola

- Login: link “¿Sos abonado? Ir al portal”
- Nav agente: **Bandeja** (Web + futuros WA), tickets, conocimiento
- Admin: reasignar conversación desde la bandeja

## Demo abonado

| Teléfono | DNI | Nombre |
|----------|-----|--------|
| 5492235551234 | 30111222 | María González |
