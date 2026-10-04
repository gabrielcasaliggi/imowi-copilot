---
# CLAUDE.md — Orientación profesional (Operations Hub / Eko)

Contrato corto para Claude Code (y cualquier copiloto). **No** es un dump del proyecto.
Fuente de verdad del harness: `AGENTS.md`. Este archivo define **qué es Eko** y **qué leer por tarea**.

## 1. Qué es Eko

**Eko** es el asistente virtual N1 del abonado en Cooperativa Batán (producto Soporte Batán / Ecolan + móvil IMOWI).

| | |
|---|---|
| Canales | Portal web (`soporte.ecolan.com`), app Expo (`mobile/`), futuros WA; voz cuando el build lo permite |
| Rol | Diagnosticar, informar, crear/seguir tickets, facturación de lectura + handoff a OV, proactivo (corte/ticket/SLA) |
| Tono | Español argentino (*vos*), corto, una pregunta por mensaje — ver `docs/EKO-VOICE.md` |
| **No es** | Copilot NOC / consola de operadores (`ibot.ecolan.com`), ni el producto “Operations Hub” completo |

**Operations Hub** = consola agentes/admin + portal + API + estate.  
**Eko** = capa conversacional y de acciones **customer-facing** sobre esa plataforma.

## 2. Stack (no ampliar)

```
Nginx → Next.js :3000 (frontend/) → FastAPI :8000 (app/) → PostgreSQL
                         ↘ Expo (mobile/)
```

| Superficie | Path |
|---|---|
| API / Runtime / journeys | `app/` · entrada `main.py` |
| Consola + portal web | `frontend/` |
| App abonado | `mobile/` |
| Harness | `AGENTS.md`, `.cursor/rules/` |

## 3. Baseline de producto (no reabrir sin propuesta explícita)

| Bloque | Estado | Documento ancla |
|---|---|---|
| 2.5 Capa conversacional | FROZEN | `docs/EKO-2.5-CONVERSATIONAL-LAYER-FREEZE.md` |
| 2.6 Agentic Ops | CLOSED | `docs/EKO-2.6T-FINAL-AGENTIC-OPS-COVERAGE.md` |
| 2.7 Incident CX | 2.7D CLOSED (deploy+smoke) | `docs/EKO-2.7D-INCIDENT-CX-IMPLEMENTATION.md` |
| Siguiente milestone | Contrato Architect | `docs/EKO-NEXT-BLOCK-ARCHITECTURE.md` |

Operativo hoy (resumen; detalle en NEXT-BLOCK §1): identidad JWT + multi-cuenta; incidente Internet fijo → diagnóstico → `create_ticket` Runtime; tickets en Activity; saldo/cabecera FC en chat + OV; Home con saldo/OV; proactivo outage + ticket + SLA; app Home/chat/Activity/push/voz según build.

Mutación customer-facing en prod: **`create_ticket`**. `ticket_customer_note` existe en código y puede estar **apagada** por CSV de producción — no inventar el flag.

## 4. Invariantes (romper = FAIL)

1. **WIP = 1** — una tarea verificada por sesión (`AGENTS.md`).
2. **CASI** — `LLM content ≠ authority`; Proposal ≠ transición de estado. Mutaciones vía Policy/Runtime/ownership.
3. **SoT de servicio** — `selected_service_ref` (2.5); no diagnosticar ambiguo.
4. **Planta manda el turno** — BCM/UISP `enlace_ok` no cae al LLM; ver `tests/test_guardrails_planta.py`.
5. **No ampliar stack** — sin frameworks/ORMs/servicios nuevos sin brief.
6. **Un hilo / un copiloto** — sin flota de agentes; multi-agente solo con presupuesto dedicado.
7. **Secretos** — nunca pegar `.env` / keys / datos reales de abonados.

## 5. Mapa de lectura (abrir solo lo del dominio)

Antes de editar: `AGENTS.md` + brief de la tarea + **una** fila de esta tabla.

| Si la tarea toca… | Leer primero (máx. 2–3 docs) | Código típico |
|---|---|---|
| Identidad Eko / copy | `docs/EKO-VOICE.md`, `docs/PORTAL-ABONADO.md` | portal auth, canal |
| Continuidad / servicio elegido | `docs/EKO-2.5-CONVERSATIONAL-LAYER-FREEZE.md`, `docs/EKO-2.5B-CONTEXT-CONTINUITY-CONTRACT.md` | `app/services/eko_*.py`, journeys |
| Tickets / Runtime / note | `docs/EKO-2.6T-FINAL-AGENTIC-OPS-COVERAGE.md`, contrato del sub-bloque (`2.6E`/`2.6K`/`2.6I`…) | `eko_action_runtime`, tickets portal |
| Proactivo / push / SLA | `docs/EKO-2.3C-PROACTIVE-NOTIFICATION-POLICY.md`, `docs/EKO-2.6A-TICKET-SLA-BREACH-PROACTIVE-PUSH.md` | `eko_proactive_*`, `app_push` |
| Facturación / OV | `docs/EKO-NEXT-BLOCK-ARCHITECTURE.md` §B, docs Billing 2.1 / OV del brief | invoice reader, `ov-links` |
| Incidente CX / “sin internet” | `docs/EKO-2.7D-INCIDENT-CX-IMPLEMENTATION.md`, `docs/EKO-2.7C-INCIDENT-CX-SCOPE.md` | connectivity, journeys |
| Comercial / autoridad | `docs/EKO-2.2G-COMMERCIAL-AUTHORITY-INTEGRATION-CONTRACT.md`, `docs/EKO-2.2H-COMMERCIAL-ADAPTER-BOUNDARY.md` | adapters comerciales |
| App móvil | `mobile/README.md` + doc EKO del feature | `mobile/src/` |
| RBAC consola | `docs/RBAC-ROLES-PERMISOS.md` | `app/rbac.py` |
| Deploy / prod | `DEPLOY.md`, `docs/FRONTEND-DEPLOY.md` | `deploy/` |
| Planta / N1 guardrails | brief + `tests/test_guardrails_planta.py` | BCM/UISP/Radius paths |
| Qué sigue / huecos | `docs/EKO-NEXT-BLOCK-ARCHITECTURE.md` | — |

Discovery (`*DISCOVERY*`), auditorías largas y matrices: **solo** si el brief lo cita. No leer “por las dudas”.

## 6. No hacer (ahorro de tokens y de riesgo)

- No leer todo `docs/` ni todo `docs/EKO-*.md` al inicio.
- No regenerar un “informe completo del sistema”; la doc de bloque ya es la SoT.
- No reabrir 2.5 / 2.6 / cierres 2.7 sin marcarlo como propuesta.
- No inventar SoT (vencimientos, PDF, pagos WRITE, eventos proactivos sin detector).
- No spawnear subagentes / orquestadores EKO por defecto.
- No dar por cerrado sin sensores del área tocada (`AGENTS.md` § Sensores).

## 7. Cierre de una tarea

1. Criterios de aceptación citados del brief o del doc de bloque.  
2. Sensores en verde (comando + pass/fail).  
3. Diff acotado; sin “ya que estamos”.  
4. Commit solo si el humano lo pide.

## 8. Arranque de sesión (checklist)

```text
[ ] Leí AGENTS.md (harness) y este CLAUDE.md (Eko)
[ ] Tengo brief / criterio de aceptación de UNA tarea
[ ] Abrí solo los 1–3 docs del mapa §5
[ ] Confirmé que no reabro un bloque FROZEN/CLOSED
[ ] Voy a verificar con el sensor de la superficie tocada
```
