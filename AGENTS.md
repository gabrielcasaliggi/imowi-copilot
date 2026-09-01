# AGENTS.md — Operations Hub (Copilot-Tickets)

Harness externo de este repo. Un agente nuevo debe orientarse leyendo solo archivos del proyecto.

## Qué es

Consola de soporte para Cooperativa Batán: portal del abonado (bot N1 → agente), bandeja, tickets N2, KB e IA.

- Abonados: `/portal` y app `mobile/`
- Agentes/admin: consola web
- APIs legacy de telemetría/JSC **no** forman parte de la UI operativa

## Topología (no ampliar el stack)

```
Nginx → Next.js :3000 (frontend/) → FastAPI :8000 (app/) → PostgreSQL
                              ↘ Expo (mobile/)
```

Python 3.12+, Next.js en `frontend/`, Expo en `mobile/`. No introducir frameworks, ORMs ni servicios nuevos sin criterio explícito en el brief.

## Cold start (bootstrap)

1. Este archivo y `README.md`.
2. Si el entorno no está: `bash scripts/setup-dev.sh`.
3. Estado del trabajo: git (`git status`, `git log -5`) y el brief de la sesión. Lo que no esté en el repo no existe para el agente.
4. Confirmar una sola tarea y sus criterios de aceptación **antes** de editar.

## Alcance de cada sesión

- **WIP = 1**: una tarea verificada por sesión. No encadenar “ya que estamos”.
- **Done** no es una autoevaluación: es sensores en verde + evidencia.
- Criterios en **default-FAIL**: no marcar cerrado sin prueba (comando, captura de flujo, o criterio de aceptación citado).
- No ampliar alcance, no refactors colaterales, no archivos que el brief no pida.

## Sensores (computacionales primero)

| Superficie | Cierre mínimo |
|---|---|
| Backend (`app/`, `tests/`) | `.venv/bin/python -m pytest` y `.venv/bin/ruff check .` sobre lo tocado |
| Frontend (`frontend/`) | `npm run lint` y `npm test` en `frontend/`; si cambió UI, flujo real en el navegador |
| Mobile (`mobile/`) | typecheck/lint del paquete tocado |
| Cualquier claim cuantitativo o de fuente | dato con origen en el repo o en el brief; no inventar |

Un linter o test opaco no basta: si falla, el mensaje al corregir debe decir qué falló, qué se esperaba y dónde.

Los jueces inferenciales (otro modelo, “¿está bien?”) van **después** de los sensores de arriba, nunca en su lugar. No aceptar como prueba los checks que el mismo agente acaba de inventar.

## Confidencialidad

- Nunca pegar secretos, keys ni `.env` en el chat.
- No commitear `.env`, credenciales ni datos de abonados reales.
- Credenciales de demo local: solo las de `README.md`; en prod no se tocan desde el agente.

## Si algo falla (steering)

No reñir al modelo. Clasificar y dejar el arreglo **en el repo**:

1. ¿Faltaba una guía (convención no escrita)?
2. ¿Faltaba un sensor (el error no se detectó solo)?
3. ¿El alcance era demasiado amplio?
4. ¿El entorno no era legible?

Anotar el cambio en la bitácora de abajo. Pregunta útil: *qué capacidad le faltaba al entorno, no al modelo*.

## Dónde está qué

| Pieza | Dónde |
|---|---|
| API | `app/` · entrada `main.py` |
| Consola + portal | `frontend/` |
| App abonado | `mobile/` |
| Deploy | `DEPLOY.md`, `docs/FRONTEND-DEPLOY.md`, `deploy/` |
| RBAC | `docs/RBAC-ROLES-PERMISOS.md` |
| RAG / KB | `docs/rag-botmaker-2026-08-14/` |
| QA N1 | `qa_bot/` |

`frontend/AGENTS.md` es la guía de Next.js de este tree; no sustituye este archivo.

## Bitácora del harness

| Fecha | Cambio | Por qué |
|---|---|---|
| 2026-09-01 | Harness mínimo: este `AGENTS.md` + regla Cursor | Adoptar guía Scrum Manager (jun 2026): instrucciones, estado en git, sensores, WIP=1, bootstrap |
| 2026-09-01 | Schema: `aplicar_schema` en boot | Production postgres con estate no usa `create_all`; Alembic stamp/upgrade; `migrate_schema` sigue aditivo |
| 2026-09-01 | FE contrato + mobile CI | `npm test` del api-client (4 endpoints) y `tsc --noEmit` de `mobile/` en GitHub Actions |
