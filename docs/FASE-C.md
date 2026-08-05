# Fase C rápida — Canales reales (MVP)

Objetivo: operación observable + humo E2E + WhatsApp listo en prod.  
Fuera de esta tanda: JSC live profundo, delivery receipts WA, OTel/Prometheus.

## Entregado

### 1. Métricas LLM
- Wrapper en `app/llm.py` registra ok/error, latencia, model, tokens (`usage` si el provider lo trae).
- Snapshot: `GET /api/v1/metrics/llm` (JWT consola).
- Contadores in-process (se reinician con el API).

```bash
TOKEN=...  # login
curl -fsS -H "Authorization: Bearer $TOKEN" https://ibot.ecolan.com/api/v1/metrics/llm | python3 -m json.tool
```

También en UI: **Admin → IA / LLM** (KPIs + últimas llamadas, auto-refresh).

### 2. Smoke Playwright
```bash
.venv/bin/pip install playwright httpx
.venv/bin/playwright install chromium

# Local o prod (ajustar URL)
export QA_BASE_URL=https://ibot.ecolan.com
export VERIFY_USER=tu@email
export VERIFY_PASSWORD='...'
.venv/bin/python -m qa_bot.smoke_fase_c

# Matriz API + smoke UI portales (guest)
.venv/bin/python -m qa_bot.run_qa --mode both --scenarios E01,E08 --base-url https://ibot.ecolan.com
```

Notas:
- Guest UI busca “No soy abonado / consulta general” (y el texto viejo por compat).
- Si `PORTAL_ALLOW_GUEST=false`, el smoke de portal guest se saltea o falla a propósito.

### 3. Checklist WhatsApp prod

- [ ] `WHATSAPP_TOKEN` y `WHATSAPP_PHONE_NUMBER_ID` seteados
- [ ] `WHATSAPP_APP_SECRET` = App Secret de Meta (firma HMAC)
- [ ] `WHATSAPP_VERIFY_TOKEN` coincide con el webhook en Meta
- [ ] `WHATSAPP_DEFAULT_ORG_SLUG` = cooperativa correcta (ej. `coop-batan`)
- [ ] GET verify:  
  `curl -s "https://ibot.ecolan.com/api/v1/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=TOKEN&hub.challenge=123"`
- [ ] POST sin firma → **403** (con secret cargado)
- [ ] Admin → Settings → test WhatsApp (token+phone configurados)
- [ ] Mensaje real de prueba desde un número autorizado en Meta

Ver también: `./scripts/verify-production.sh https://ibot.ecolan.com`

## Siguiente (resto Fase C)
1. JSC live (diagnóstico red)
2. WhatsApp: status callbacks / reintentos
3. Playwright autenticado DNI+OTP
4. Export métricas LLM a Sentry/Prometheus
