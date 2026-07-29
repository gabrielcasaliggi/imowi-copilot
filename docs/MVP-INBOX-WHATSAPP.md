# Inbox / Bandeja — guía operativa (Batán)

## Producto

Consola de **Cooperativa Batán**: bandeja de conversaciones (portal web hoy; WhatsApp después), bot N1, tickets N2 y conocimiento.

## Roles

- **Agente** (`batan`/`batan`): bandeja + tickets  
- **Admin** (`admin`/`admin`): todo + reasignar  
- **Abonado**: solo [`/portal`](./PORTAL-ABONADO.md)

## Flujo

1. Abonado entra a `/portal` → bot N1  
2. Si no resuelve / pide agente → hilo en **Bandeja** (`espera_agente`)  
3. Agente toma, responde, cierra; ticket N2 en consola de tickets  

WhatsApp Cloud API: fase 2 (ver config plataforma). No es el canal prioritario de la UX actual.
