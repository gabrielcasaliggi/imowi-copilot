# Inbox WhatsApp — guía operativa (Batán)

## Producto

Consola de **Cooperativa Batán**: bandeja WhatsApp, bot N1 (Ecolan / móvil / deuda), escalamiento a ticket N2 y conocimiento. Sin superficie JSC/NOC/red en la UI.

## Flujo agente

1. Login `batan` / `batan` → entra en **Bandeja WhatsApp**
2. Tomar hilo en cola → responder → cerrar
3. Tickets N2: **Consola de tickets**
4. KB: **Centro de conocimiento** (visible a agentes)

## Administración

`admin` / `admin` → Admin Hub (cooperativas + configuración IA/WhatsApp/playbooks).  
Inyectar entrada WhatsApp: solo admin, en **Herramientas de canal**.

## Seed

Si no hay conversaciones abiertas en `coop-batan`, al arrancar se crean 3 hilos realistas (`canal=whatsapp`).

## Meta Cloud API

Variables en `.env` / Configuración plataforma. Webhook: `/api/v1/whatsapp/webhook`.
