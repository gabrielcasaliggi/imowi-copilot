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

1. Este archivo, `CLAUDE.md` (qué es Eko + mapa de lectura) y `README.md`.
2. Si el entorno no está: `bash scripts/setup-dev.sh`.
3. Estado del trabajo: git (`git status`, `git log -5`) y el brief de la sesión. Lo que no esté en el repo no existe para el agente.
4. Confirmar una sola tarea y sus criterios de aceptación **antes** de editar.
5. Abrir solo los docs del dominio en `CLAUDE.md` §5 — no todo `docs/EKO-*.md`.

## Alcance de cada sesión

- **WIP = 1**: una tarea verificada por sesión. No encadenar “ya que estamos”.
- **Done** no es una autoevaluación: es sensores en verde + evidencia.
- Criterios en **default-FAIL**: no marcar cerrado sin prueba (comando, captura de flujo, o criterio de aceptación citado).
- No ampliar alcance, no refactors colaterales, no archivos que el brief no pida.

## Modelo de trabajo profesional (herramientas)

Proceso de equipo, **un solo copiloto**, calidad por sensores y git — no por cantidad de agentes.

| Pieza | Rol |
|---|---|
| **Cursor** | Espacio de trabajo (editor, git, terminal). Sin suscripción Pro; IA en Cursor solo si hay API y con disciplina |
| **Claude API + Claude Code** | Ejecución asistida por defecto (implementar, diffs, explicación) |
| **Claude app** (opcional) | Briefs, ADRs, copy — fuera del loop de archivos |
| **Git + CI / sensores** | Verdad de “listo”; sin pass no hay cierre |

### Un hilo, fases en serie

Las fases Architect → Dev → QA → Security siguen siendo el rigor del oficio, pero **en el mismo hilo** (mismo chat / misma sesión Claude Code), no como flota de agentes:

1. Decidir (brief / ADR corto)  
2. Implementar  
3. Verificar sensores  
4. Revisar seguridad/datos solo si el cambio lo exige  

Roles `@architect`, `@developer`, `@qa`, `@reviewer-security`: guía de **estilo en este hilo** si se invocan; no spawnear otro agente.

### Prohibido por defecto

- `Task` / multi-agente / ciclo EKO orquestado / best-of-n / Max Mode  
- Solo con pedido explícito **y** presupuesto dedicado (API con tope o plan alto)

Detalle operativo corto: `.cursor/rules/token-budget-pro.mdc`.

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
| Orientación Eko (Claude Code) | `CLAUDE.md` |
| API | `app/` · entrada `main.py` |
| Consola + portal | `frontend/` |
| App abonado | `mobile/` |
| Deploy | `DEPLOY.md`, `docs/FRONTEND-DEPLOY.md`, `deploy/` |
| RBAC | `docs/RBAC-ROLES-PERMISOS.md` |
| RAG / KB | `docs/rag-botmaker-2026-08-14/` |
| QA N1 | `qa_bot/` |
| Baseline / siguiente bloque Eko | `docs/EKO-2.5-…`, `docs/EKO-2.6T-…`, `docs/EKO-NEXT-BLOCK-ARCHITECTURE.md` |

`frontend/AGENTS.md` es la guía de Next.js de este tree; no sustituye este archivo.

## Bitácora del harness

| Fecha | Cambio | Por qué |
|---|---|---|
| 2026-09-01 | Harness mínimo: este `AGENTS.md` + regla Cursor | Adoptar guía Scrum Manager (jun 2026): instrucciones, estado en git, sensores, WIP=1, bootstrap |
| 2026-09-01 | Schema: `aplicar_schema` en boot | Production postgres con estate no usa `create_all`; Alembic stamp/upgrade; `migrate_schema` sigue aditivo |
| 2026-09-01 | FE contrato + mobile CI | `npm test` del api-client (4 endpoints) y `tsc --noEmit` de `mobile/` en GitHub Actions |
| 2026-09-01 | Dump KB fuera de git | Un dump opcional en `data/`; N1 usa estate. No versionar 52k duplicados |
| 2026-09-08 | Auth WA por MSISDN (F1) | `lookup_abonados_por_telefono` + desambiguación N cuentas; brief `docs/INTEGRACION-OV-FACTURAS-WA.md` |
| 2026-09-10 | Rama de planta manda el turno N1 | BCM/UISP `enlace_ok` ya no cae al LLM; Sensa cuelga del acceso; ADSL/IMOWI no usan BCM; sensor `tests/test_guardrails_planta.py` |
| 2026-09-10 | Eval masivo `--planta` | Replay Botmaker mockea BCM/Radius (`enlace_ok` / `onu_offline`); sensor `tests/test_eval_planta.py` |
| 2026-09-28 | Reglas de fase en `.cursor/rules/` | `@architect`, `@developer`, `@qa`, `@reviewer-security`, `@design-system`. `alwaysApply: false`. El harness de este archivo sigue siempre activo |
| 2026-09-29 | Austeridad tokens Pro ~USD 20 | Cupo debe alcanzar el mes; sin Task/EKO espontáneos; modelos caros prohibidos; migración Claude prevista |
| 2026-10-01 | Solo chat principal | Multi-agente quemó el cupo; volver a un solo agente; roles @* = estilo en el mismo chat; Claude API como IA principal |
| 2026-10-01 | Modelo profesional herramientas | Cursor=IDE; Claude Code=copiloto; un hilo fases en serie; multi-agente solo con presupuesto dedicado |
| 2026-10-01 | `CLAUDE.md` orientación Eko | Índice profesional: qué es Eko, baseline, invariantes, mapa de lectura por dominio; evita dump exhaustivo |
| 2026-10-02 | EKO 2.8A: login nombrado por texto → `selected_service_ref` | El canal por texto dejaba `login_seleccionado` sin ref y el diagnóstico volvía a pedir selección; `_sincronizar_login_desde_mensaje` ahora canonicaliza vía `_enrich_login_to_ref`; sensor `tests/test_eko_28a_login_sync_ref.py` |
| 2026-10-02 | EKO CTX-1: servicio en foco en CONTEXTO_ABONADO | El prompt N1 no sabía qué servicio estaba en foco ni distinguía datos técnicos de otro login; sección `SERVICE IN FOCUS`, guarda por grupo pppoe/uisp/bcm y fecha de ticket; sensor `tests/test_eko_ctx_1_servicio_en_foco.py` |
