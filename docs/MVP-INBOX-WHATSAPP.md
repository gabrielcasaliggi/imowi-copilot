# Inbox / Bandeja — guía operativa (Batán)

## Producto

Consola de **Cooperativa Batán**: bandeja de conversaciones (portal web, WhatsApp, Telegram), bot N1, tickets N2 y conocimiento.

## Roles

- **Agente** (`batan`/`batan`): bandeja + tickets  
- **Admin** (`admin`/`admin`): todo + reasignar  
- **Abonado**: solo [`/portal`](./PORTAL-ABONADO.md)

## Flujo

1. Abonado entra a `/portal` → bot N1  
2. Si no resuelve / pide agente → hilo en **Bandeja** (`espera_agente`)  
3. Agente toma, responde, cierra; ticket N2 en consola de tickets  

WhatsApp Cloud API y Telegram Bot API: ver config de plataforma / `docs/TELEGRAM-CANAL.md`. El portal web sigue siendo el canal prioritario de UX.
