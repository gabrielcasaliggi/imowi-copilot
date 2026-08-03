# QA Bot N1 — Portal Ecolan (Invitado)

Harness de auditoría conversacional contra producción:

- Portal UI: https://ibot.ecolan.com/portal (Playwright, modo Invitado)
- API: `POST /api/v1/portal/session` + `POST /api/v1/portal/messages` (org `coop-batan`)

## Uso

```bash
.venv/bin/pip install playwright httpx
.venv/bin/playwright install chromium
.venv/bin/python -m qa_bot.run_qa --mode both
```

Reporte: `../reporte_qa_bot.md`
