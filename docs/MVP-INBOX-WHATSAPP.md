# MVP Inbox WhatsApp — guía rápida

## Qué incluye

- Abonados en Postgres (`abonados`) con seed Batán/Ecolan
- Bot N1 (internet + móvil + corte/deuda) con playbooks
- Escalamiento a ticket **N2** si no resuelve o piden agente
- **Inbox** en `/inbox` (tomar, responder, cerrar)
- Simulador sin Meta + webhook Cloud API listo

## Probar local

1. API: `uvicorn main:app --reload --port 8000`
2. Frontend: `cd frontend && npm run dev`
3. Login `batan` / `batan` (o `admin` y tenant Batán)
4. Ir a **Inbox WhatsApp** → Simular WA con `5492235551234` / `Hola`

### Abonados demo

| Teléfono | DNI | Caso |
|----------|-----|------|
| 5492235551234 | 30111222 | María — activo ambos |
| 5492235559012 | 32123456 | Ana — corte / deuda |
| 5492235560001 | 27333444 | Jorge — suspendido |
| 5492235560099 | 26444555 | Pedro — internet OK |

## WhatsApp Meta

Variables (ver `.env.example`):

```env
WHATSAPP_TOKEN=...
WHATSAPP_PHONE_NUMBER_ID=...
WHATSAPP_VERIFY_TOKEN=ops-hub-wa-verify
WHATSAPP_DEFAULT_ORG_SLUG=coop-batan
```

Webhook: `GET/POST https://TU_API/api/v1/whatsapp/webhook`

## Llama

Variables `AI_*` o desde **Admin → Configuración plataforma → API IA**.

## Configuración de plataforma (admin)

Login `admin` / `admin` → **Admin Hub** → pestaña **Configuración plataforma**:

| Sección | Qué configura |
|---------|----------------|
| API IA | `base_url`, modelo Llama, API key |
| WhatsApp | token Meta, phone number id, verify token, org slug |
| Base de datos | URL (documentación / prep on-prem; reinicio para aplicar) |
| Conocimiento | umbrales RAG (score, top_k, tamaño fragmento) |
| Playbooks | JSON de pasos N1 internet/móvil/corte |

API: `GET/PUT /api/v1/admin/settings` (solo admin). Secretos se devuelven enmascarados; reenviar valor con `***` no los pisa.

Runtime: IA, WhatsApp y playbooks leen la DB con fallback a `.env`.

El simulador de inbox puede ir con `usar_llama: false` (reglas puras).
