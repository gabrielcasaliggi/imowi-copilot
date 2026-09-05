# QA Bot N1 — Portal Ecolan

Harness de auditoría conversacional.

## Evaluación masiva (reemplaza capturas manuales)

Usa el dump Botmaker (`sessions-*.raw.json`, fuera de git). Anonimiza, filtra menús numéricos y reenvía los primeros turnos al endpoint local.

```bash
.venv/bin/python -m qa_bot.eval_masivo --solo-extraer
.venv/bin/python -m qa_bot.eval_masivo --limit 200 --categoria internet
```

Dump por defecto: `~/Descargas/sesiones-historicas-2025_2026-06`.
Corpus: `data/eval-botmaker/corpus.json` (gitignored).
Reporte: `qa_bot/artifacts/eval_botmaker.md` y `eval_botmaker.json`.

El replay aísla BillTrack (`.env` local suele tener credenciales inválidas) y reusa
un solo OTP: no martilla `/portal/auth/start`. Atajo: `bash scripts/run_eval_local.sh`.

Personas sintéticas (0 N2 evitables): `python -m qa_bot.entrenamiento_exhaustivo`.

## Matriz portal / producción (Invitado)

- Portal UI: https://ibot.ecolan.com/portal (Playwright, modo Invitado / visitante)
- API: `POST /api/v1/portal/session` + `POST /api/v1/portal/messages` (org `coop-batan`)
- Smoke Fase C: `python -m qa_bot.smoke_fase_c` — ver `docs/FASE-C.md`

```bash
.venv/bin/pip install playwright httpx
.venv/bin/playwright install chromium
.venv/bin/python -m qa_bot.run_qa --mode both
```

Reporte: `../reporte_qa_bot.md`
