# EKO 2.6J — Ticket Agentic Lifecycle Discovery

**Date:** 2026-09-23  
**Mode:** READ ONLY — code changes: **NONE** (este archivo es el único entregable)  
**Primary evidence:** live code (`eko_action_runtime`, `eko_action_coverage`, `eko_capability_contract`, `config.ACTION_RUNTIME_ACTIONS`, `canal_abonado`, `eko_journeys`, `eko_ticket_proactive`, `estate/repository`, `api/v1/tickets`, portal) + existing tests  

---

## 1. Executive Summary

Hoy el **Ticket Agentic Lifecycle** de Eko **no** es un ciclo completo bajo CASI→Policy→Runtime→Effect. Es un **mosaico**:

| Capacidad | Realidad operativa |
|---|---|
| `show_ticket` | Runtime READ cableado N1; ownership vía `ticket_pertenece_abonado` |
| `ticket_customer_note` | Runtime EFFECT + N1 wire (2.6I); Event `nota` Sí; push vía 2.3G-B (self-note suppress) |
| `create_ticket` | Executor + N1 XOR helper existen; **fuera del default ACTIONS**; Legacy `_crear_ticket_n2` sigue siendo el hot path típico |
| `update_ticket` (Runtime) | Executor = evidencia interna (`_append_evidencia`); **N1 no despacha** |
| Admin/helpdesk update/close/reassign | Legacy API `PUT /tickets` + `repo.update_ticket` — **no** Action Runtime |
| `escalate_human` | Executor muda `conv.estado→espera_agente`; N1 **compone** `create_ticket`, no despacha `escalate_human` |
| `close_conversation` | Cierra **hilo N1**, no el Ticket estate; executor only; N1 Legacy CSAT |
| `close_ticket` / `resolved` | **No** hay ActionSpec `close_ticket`. Estados ticket = `Abierto` / `En Revisión` / `Cerrado`. **No** existe estado `Resuelto` |
| SLA breach push | 2.6A Event `sla_breach` Sí → `ticket.sla_breached` (sistema) |

**Pregunta de la fase:** *¿Hasta dónde llega realmente el lifecycle agentic?*

**Respuesta con evidencia:** desde la intención del abonado, hoy llegan de punta a punta bajo Runtime gobernado:

1. **consultar ticket** (`show_ticket`), y  
2. **dejar nota customer-visible** (`ticket_customer_note`),

cuando `ACTION_RUNTIME_ENABLED` + membership en ACTIONS.

Crear ticket, evidencia interna, escalar humano y cerrar ticket/conversación siguen **parcialmente** o **fuera** de ese tubo (Legacy/helpdesk/composición).

```text
EKO 2.6J — DISCOVERY COMPLETE
```

---

## 2. Current Ticket Lifecycle

```text
                    ┌─────────────────────────────────────────────┐
                    │              Abonado (N1 / portal / app)     │
                    └─────────────────────────────────────────────┘
                         │                    │
            phrase/journey/LLM          Portal JWT POST
                         │                    │
         ┌───────────────▼────────┐   ┌───────▼────────┐
         │ Policy/Motor/Journey   │   │ portal create   │
         │ + Action Runtime gate  │   │ (estate write)  │
         └───────────────┬────────┘   └───────┬────────┘
                         │                    │
         show_ticket / note / (create if on)  │
                         │                    │
                         ▼                    ▼
              ┌──────────────────────────────────────┐
              │           Estate Ticket                 │
              │  + TicketEvent (creacion/nota/…)        │
              └──────────────────┬───────────────────┘
                                 │
                    add_ticket_event post-commit
                                 │
                                 ▼
                    2.3G-B detector → policy → claim → Expo
                                 │
                    ┌────────────┴────────────┐
                    │ Helpdesk agente/admin     │
                    │ PUT/events/reassign/close │
                    │ (RBAC; no Runtime N1)     │
                    └──────────────────────────┘
```

**Gates globales (no negociados en esta fase):**

- `ACTION_RUNTIME_ENABLED` default **false**
- Default `ACTION_RUNTIME_ACTIONS` incluye `show_ticket` + `ticket_customer_note`; **excluye** `create_ticket`, `update_ticket`, `escalate_human`, `close_conversation`
- `EKO_JOURNEYS_ENABLED` default **false** (journeys orquestan; canal tiene wire paralelo para note/show)

---

## 3. Action Inventory

Fuentes: `bootstrap_registry()` ActionSpecs; `eko_action_coverage._base_rows()`; `eko_capability_contract`; `config.ACTION_RUNTIME_ACTIONS`.

| Action | Existe | Capability | Coverage | Runtime | Legacy | Effect | Estado |
|---|---|---|---|---|---|---|---|
| `show_ticket` | YES | YES | EXECUTED_BY_RUNTIME | YES (default ACTIONS) | journey fallback read if gate off | READ Ticket facts | **RUNTIME_READY** |
| `ticket_customer_note` | YES | YES | EXECUTED_BY_RUNTIME | YES (default ACTIONS + N1 2.6I) | none customer-visible | TicketEvent `nota` Sí | **RUNTIME_READY** |
| `create_ticket` | YES | YES | EXECUTED_BY_RUNTIME (wired) | executor YES; **not** default ACTIONS | `_crear_ticket_n2` when gate off | Ticket + Event `creacion` Sí + espera_agente | **RUNTIME_PARTIAL** |
| `update_ticket` | YES | YES | RUNTIME_EXECUTOR_ONLY | executor YES; N1 **no** dispatch | `_append_evidencia_ticket` | Ticket fields evidencia (no Event) | **RUNTIME_PARTIAL** |
| `escalate_human` | YES | YES | RUNTIME_EXECUTOR_ONLY | executor YES; N1 **no** dispatch as ActionRequest | escape → create_ticket / espera_agente | `conv.estado` (+ notify) | **RUNTIME_PARTIAL** / composition |
| `close_conversation` | YES | YES | RUNTIME_EXECUTOR_ONLY | executor YES; N1 **no** dispatch | `_cerrar_consulta_resuelta` + CSAT | `conv.estado=cerrado` | **LEGACY_ONLY** (hot path) |
| `close_ticket` | **NO** ActionSpec | N/A | N/A | N/A | `PUT /tickets` → `repo.update_ticket` | Ticket `Cerrado` + Event `actualizacion` Sí | **LEGACY_ONLY** (helpdesk) |
| `resolved` | **NO** estado en estate | N/A | N/A | N/A | N/A | N/A | **UNAVAILABLE** |
| Portal create ticket | API | N/A | N/A | no Runtime | portal JWT | Ticket + creacion | **LEGACY_ONLY** (portal authority) |
| Reassign / derivar | API | N/A | N/A | no Runtime | `POST …/reassign` | Event `reasignacion` No | **LEGACY_ONLY** |
| Bulk close | API admin | N/A | N/A | no Runtime | `cerrar_tickets_abiertos` | Event `cierre_masivo` No | **LEGACY_ONLY** |
| SLA breach emit | helper 2.6A | proactive | N/A | sistema | refresh_tickets_sla hook | Event `sla_breach` Sí | **RUNTIME_READY** (event path; not N1 Action) |

Clasificación de columna **Estado** = readiness Agentic Ops N1 (no “calidad de producto”).

---

## 4. Per-action End-to-End Trace

### 4.1 `show_ticket` — RUNTIME_READY

```text
Usuario
 ↓ phrase ("estado del ticket" / journey ticket_consulta)
 ↓ Intent (NO ActionProposal domain escalate/resolved)
 ↓ Policy (evaluate_policy — ALLOW if registered + abonado)
 ↓ Journey _advance_ticket OR canal_abonado consulta_ticket
 ↓ dispatch_runtime("show_ticket")   [si covers]
 ↓ _exec_show_ticket
 ↓ ticket_pertenece_abonado + load_ticket_facts
 ↓ Ticket READ (no TicketEvent write)
 ↓ (no proactive)
 ↓ user_message estado
```

| Paso | Existe |
|---|---|
| Phrase / journey | YES |
| ActionProposal (domain escalate/resolved) | NO (no requerido) |
| Policy Runtime | YES |
| dispatch N1 | YES |
| Executor | YES |
| Ownership | YES |
| Event / push | NO (READ) |
| Legacy fallback | YES (journey: reader directo si `ar is None`) |

**Foreign ticket:** DENY `foreign_ticket` — proven en 4B/4C/4D/journeys.  
**Ambiguity:** missing `ticket_id` → NEEDS_INPUT (journey pide número; executor `missing_ticket_id`). Multi-ticket auto-select: **NOT PROVEN** for show (journey exige tid explícito o `conv.ticket_id`).

**Expuesto al abonado:** id, state, category, origin, timestamps (`ticket_fact_item`) — sin eventos internos ni notas en el READ Runtime.

---

### 4.2 `ticket_customer_note` — RUNTIME_READY (2.6I PASS)

```text
Usuario
 ↓ phrase (_TICKET_NOTE_PHRASES) / LLM parse_llm_action_proposal
 ↓ parameters sanitized (no visibility/notify/ownership)
 ↓ Policy ALLOW | NEEDS_INPUT | DENY
 ↓ Journey _advance_ticket_customer_note OR canal phrase gate
 ↓ dispatch_runtime("ticket_customer_note")
 ↓ _exec_ticket_customer_note (ownership + ambiguous resolve)
 ↓ emit_ticket_customer_note
 ↓ TicketEvent(tipo=nota, visible_cliente=Sí)
 ↓ maybe_deliver_ticket_event_push (2.3G-B)
 ↓ SELF_NOTE_NO_PUSH si actor abonado* ; else policy→claim→Expo
```

| Check | Result |
|---|---|
| Ownership | PASS |
| Actor N1 | `abonado:{id}` |
| Visibility | hardcoded Sí |
| Notify | detector authority (not LLM) |
| Event type | `nota` → `ticket.updated` |
| Self-note | PASS suppress push |
| Foreign | DENY |
| Ambiguous | NEEDS_INPUT |
| CASI sanitize | PASS |
| XOR | PASS (gate off → unavailable, no Legacy Sí) |

**Verdict 2.6I audit (no code change):** **PASS**

---

### 4.3 `create_ticket` — RUNTIME_PARTIAL

```text
Usuario / playbook escape
 ↓ Motor authorize_escalate OR decision create_ticket_n2
 ↓ _ticket_via_runtime_o_legacy
    ├─ covers? → dispatch_runtime("create_ticket")
    │     → Policy NEEDS_CONFIRMATION (confirmation_required=True)
    │     → trusted sí → _exec_create_ticket → _crear_ticket_n2
    └─ covers? False → Legacy _crear_ticket_n2 directo
 ↓ ticket_bridge.crear_ticket / repo.create
 ↓ TicketEvent tipo=creacion visible=Sí  → proactive ticket.created
 ↓ conv.ticket_id + conv.estado=espera_agente + handoff notify
```

| Aspecto | Evidencia |
|---|---|
| ActionSpec | YES, `confirmation_required=True`, PROTECTED |
| Default ACTIONS | **NO** — must list in env CSV |
| N1 wire | YES (`_ticket_via_runtime_o_legacy`) |
| Effect real | YES — Ticket estate + Event creacion |
| Ownership | vía abonado/línea en `_crear_ticket_n2` |
| XOR when covers | YES — tests 4D: deny/unavailable/confirm → no Legacy writer |
| Hot path prod típico | Legacy (ENABLED false o action no listada) |
| ActionProposal domain | escalate/resolved ≠ Runtime ActionRequest (capas distintas) |

**Conclusión:** es un Effect real; Runtime path **existe y está testeado**, pero **no** es el camino default de producción. No es “solo HANDOFF vacío”: crea Ticket N2 y Event customer-visible `creacion`.

---

### 4.4 `update_ticket` — RUNTIME_PARTIAL (evidence-only vs helpdesk)

**A) Runtime Action `update_ticket` (N1 capability):**

```text
(ActionRequest)
 ↓ Policy
 ↓ _exec_update_ticket
 ↓ ticket_pertenece_abonado
 ↓ _append_evidencia_ticket  → muta Ticket.evidencia / descripcion_falla
 ↓ NO TicketEvent, NO push
```

- Coverage: **RUNTIME_EXECUTOR_ONLY** — N1 **no** llama `dispatch_runtime("update_ticket")`.
- Confirmación: NOT_REQUIRED.
- No en default ACTIONS.

**B) Helpdesk `PUT /tickets/{id}` (`repo.update_ticket`):**

```text
Agente/admin RBAC
 ↓ repo.update_ticket (estado, resolución, nivel, destino, asignado_a, SLA, …)
 ↓ on cambios → TicketEvent actualizacion|reasignacion
      closing → visible Sí (ticket.closed via map)
      else actualizacion → visible No
      reassign → reasignacion visible No
 ↓ proactive solo si visible + mapping
```

**Separación crítica (proven 2.6E/G/I):**

| | Runtime `update_ticket` | `ticket_customer_note` | Admin PUT close |
|---|---|---|---|
| Customer Event | NO | YES `nota` | YES on Cerrado (`actualizacion` Sí) |
| Push | NO | YES (non-self) | YES on close path |
| Campos estado/asignación | NO | NO | YES |

---

### 4.5 `escalate` — RUNTIME_PARTIAL / composition HANDOFF

Implementaciones reales:

1. **ActionSpec `escalate_human`:** set `conv.estado=espera_agente` + `notify_espera_agente` + stamp handoff continuity. **No** crea TicketEvent. **No** muta Ticket estate por sí solo.
2. **N1 composition (documented):** `escalate_human → create_ticket` (escape/handoff) — coverage notes + `ESCALATE_COMPOSITION`.
3. **Domain Motor `authorize_escalate`:** ActionProposal escalate/resolved — autoriza ACT_ESCALATE; canal ejecuta efectos (ticket/espera).
4. **Helpdesk reassign:** `POST` reasignación → Event `reasignacion` No.

```text
LLM proposal escalate
 ↓ Motor authorize_escalate (CASI)
 ↓ canal → often create_ticket / espera_agente
 ↓ (optional) Runtime escalate_human IF listed in ACTIONS — N1 typically does NOT dispatch it
```

**No** inferir “derivar supervisor” = Runtime escalate.

---

### 4.6 `close` — split: conversation vs ticket

| Operación | ActionSpec | Quién | Effect | Event | Push |
|---|---|---|---|---|---|
| `close_conversation` | YES | Runtime executor / Legacy N1 | `ConversacionCanal.estado=cerrado` (+ CSAT Legacy) | NO TicketEvent | NO ticket push |
| Ticket → `Cerrado` | NO | Agente/admin `PUT /tickets` | `Ticket.estado=Cerrado` | `actualizacion` Sí → `ticket.closed` | YES (2.3G-B) |
| Bulk close | NO | admin/supervisor | muchos Cerrado | `cierre_masivo` No | NO (internal tipo) |
| `resolved` | — | — | **UNSUPPORTED** | — | — |

Estados válidos (`ESTADOS_TICKET_VALIDOS`): `Abierto`, `En Revisión`, `Cerrado`.

N1 “cerrar consulta” ≠ cerrar Ticket N2.

---

## 5. Ownership / Authorization Matrix

| Operation | Identity | Ticket ownership | Who may EFFECT |
|---|---|---|---|
| `show_ticket` | TrustedContext abonado | `ticket_pertenece_abonado` | abonado (own) |
| `ticket_customer_note` N1 | TrustedContext | same + emit defensive | abonado (own); agent API `agent_authorized` |
| `create_ticket` | TrustedContext + confirm | línea/conv abonado | abonado (escalamiento N2) |
| `update_ticket` Runtime | TrustedContext | `ticket_pertenece_abonado` | abonado (evidence only) — **if** dispatched |
| Admin PUT / events | JWT RBAC | org ticket + role/assignment | agente/admin |
| Reassign | `tickets` supervisor perms | org | supervisor/admin |
| Bulk close | admin/supervisor | org | admin/supervisor |
| SLA breach | sistema | ticket owner for push | sistema |

**Autenticado ≠ autorizado:** proven (foreign DENY; agent assignment checks on PUT).

---

## 6. TicketEvent Matrix

Inventario desde código (`eko_ticket_proactive`, `repository`, `tickets.py`, learning_loop):

| Event `tipo` | Visible default | Push (si Sí + map) | Detector map | Actor típico | Uso |
|---|---|---|---|---|---|
| `creacion` | Sí | `ticket.created` | YES | `bot:…` / portal / sistema | create ticket |
| `nota` | Sí (emit only) | `ticket.updated` | YES | agente email / `abonado:*` | customer note ACT |
| `actualizacion` | No (admin); **Sí si Cerrado** | updated / **closed** | YES | operador | admin update/close |
| `reasignacion` | No | NO (internal) | no map / gated | operador | reassign |
| `nota_interna` | No | NO | internal set | agente | helpdesk interno |
| `sla_breach` | Sí | `ticket.sla_breached` | YES | sistema | 2.6A |
| `cierre_masivo` | No | NO | internal | admin | bulk close |
| `aprendizaje` / KB\* | No | NO | internal | sistema | learning_loop |
| otros ops (`paso_operativo`, …) | typically No | NO | `_INTERNAL_TIPOS` | — | ops |

**Accidental customer exposure risk (GAP awareness, not new bug):**

- Admin non-close `actualizacion` default **No** (2.6E/G harden) — PASS vs accidental.
- Close → **Sí** intentional.
- Default `add_ticket_event(visible_cliente="No")` — PASS.
- Path that still forces Sí: `creacion`, `emit_ticket_customer_note`, `sla_breach`, close branch.

Portal projection allowlist (`is_portal_customer_event`): `creacion`, `nota`, `sla_breach`, + `actualizacion` only if estado Cerrado.

---

## 7. Proactive Chain Matrix

```text
Effect → TicketEvent → Detector → Policy → Dedup(claim) → Ownership → Delivery
```

| Lifecycle signal | Event | Chain | Support |
|---|---|---|---|
| created | `creacion` Sí | full | 2.3G-B YES |
| updated (note) | `nota` Sí | full (+ self-note suppress) | 2.6E/I YES |
| updated (admin fields) | `actualizacion` No | suppressed at gate | intentional |
| closed | `actualizacion` Sí + estado Cerrado | `ticket.closed` | YES |
| sla_breach | `sla_breach` Sí | `ticket.sla_breached` | 2.6A YES |
| resolved | — | — | **UNSUPPORTED** |
| escalate_human alone | no TicketEvent | no ticket push | N/A |
| update_ticket evidence | no Event | no push | intentional |

**Deferred (unchanged):** Event committed → push failed (no outbox tx) — 2.6F.

---

## 8. CASI Audit

| EFFECT | LLM may propose | LLM cannot | Verdict |
|---|---|---|---|
| `ticket_customer_note` | YES | visibility/notify/ownership/tipo/push/direct write | **CASI PASS** |
| `show_ticket` | params ticket_id | foreign access | **CASI PASS** |
| `create_ticket` | motivo/intent content | auto-confirm; confirmation trusted only | **CASI PASS** (when Runtime path) |
| `update_ticket` Runtime | nota text | Event/push | **CASI PASS** (executor) — N1 dispatch **NOT PROVEN** in prod path |
| Helpdesk PUT | N/A (human JWT) | — | N/A agent authority |
| Domain escalate proposal | YES | Motor deny without heuristics/plant | **CASI PASS** (escalate suites) |

**Overall ticket Agentic CASI:** **CASI PASS** for Runtime-governed actions; **CASI PARTIAL** for lifecycle completeness (many EFFECTS still helpdesk/Legacy without LLM surface).

No path found where LLM alone sets `visible_cliente` or calls `add_ticket_event` — **NOT PROVEN** violation in current Runtime sanitize + emit.

---

## 9. Runtime XOR Legacy Audit

| Action | Runtime path | Legacy path | Fallback | XOR proven? |
|---|---|---|---|---|
| `show_ticket` | dispatch | journey direct reader if gate off | XOR by gate | YES (mutual exclusion by covers) |
| `ticket_customer_note` | dispatch | **none** customer-visible | unavailable if off | **YES** (2.6I tests) |
| `create_ticket` | `_ticket_via_runtime_o_legacy` | `_crear_ticket_n2` | if covers: never Legacy on deny/fail | **YES** (4D) |
| `update_ticket` | executor only | `_append_evidencia` N1 | parallel writers **possible** if both used | **GAP** — N1 Legacy evidence vs Runtime not XOR-wired |
| `escalate_human` | executor | compose create_ticket | composition ≠ dual same ActionRequest | **PARTIAL** |
| `close_conversation` | executor | `_cerrar_consulta_resuelta` | N1 Legacy primary | **NOT XOR-wired** |
| Ticket close | none | helpdesk PUT | — | N/A |

---

## 10. Confirmation Audit

| Action | Required? | Implemented? | Enforced? | Bypass? | Destructive? |
|---|---|---|---|---|---|
| `create_ticket` | YES | trusted user confirm / pending state | Policy NEEDS_CONFIRMATION | LLM cannot confirm | YES (Ticket+handoff) |
| `escalate_human` | YES | same pattern if Runtime | Policy | N1 usually bypasses via composition | MEDIUM (espera_agente) |
| `close_conversation` | YES (spec) | if Runtime | Policy | N1 Legacy may close without Runtime confirm | MEDIUM |
| `ticket_customer_note` | NO | — | — | — | MEDIUM (visible note) |
| `show_ticket` | NO | — | — | — | NO |
| `update_ticket` | NO | — | — | — | LOW (evidence) |
| Ticket close helpdesk | tramite bloqueo + RBAC | helpdesk UX | API checks | — | HIGH |

No new UX introduced in this discovery.

---

## 11. Idempotency Audit

| Write | Effect idempotency | Notification dedup |
|---|---|---|
| `create_ticket` | `conv.ticket_id` → `already_done` | Event creacion once per create; push claim by Event.id |
| `ticket_customer_note` | same `(ticket, detalle)` → same Event | claim `push_claimed_at`; self-note no push |
| `update_ticket` evidence | substring dedup in evidencia text | N/A (no Event) |
| Admin update | new Event per change set | claim per Event |
| escalate_human | already in espera_agente → already_done | handoff notify separate |
| close_conversation | already cerrado → already_done | CSAT separate |
| Ticket close | estado Cerrado + learning once | Event + claim |

**Do not conflate:** `push_claimed_at` ≠ write idempotency.

---

## 12. Test Evidence

| Action | Tests (existing) | Coverage real | Missing critical case |
|---|---|---|---|
| `show_ticket` | 4B/4C/4D foreign; journeys missing id | strong ownership | multi-ticket ambiguity auto-select |
| `ticket_customer_note` | 2.6E/G + **2.6I** (happy/foreign/ambig/CASI/XOR/self) | strong | prod smoke (deferred) |
| `create_ticket` | 4B confirm; 4C/4D XOR; 4E already_done; portal create | strong Runtime+XOR; Legacy path implicit | default ACTIONS still off |
| `update_ticket` | 4B foreign; 2.6E/I no Event/push | executor proven | **N1 dispatch wire** absent |
| `escalate_human` | escalate_authority; 2.5D-4 stamp; 4D composition | Motor CASI strong | Runtime N1 dispatch of escalate_human |
| `close_conversation` | catalog/coverage docs | thin Runtime E2E | N1 Runtime wire + CSAT parity |
| Ticket close / events | 2.6E close visible; portal; helpdesk | helpdesk path | no Agentic `close_ticket` Action |
| Proactive | 2.3G-B; 2.3D/E; 2.6A | strong | Event/push tx window |

**RO test run (this phase):**

```text
pytest: 2.6I, 2.6E, 2.3G-B, 2.6A, 4D, 4E, portal_tickets, escalate_authority
→ 1 FAIL: test_4d_explicit_pppoe_one_reader (diagnostic PPPoE — known unrelated; not fixed)
→ remaining PASS
ruff (ticket-related modules spot): PASS
```

---

## 13. Final Classification

| Capability | Authority | Runtime | Effect | Event | Push | Ownership | CASI | XOR | Classification |
|---|---|---|---|---|---|---|---|---|---|
| `show_ticket` | Trusted + pertenece | YES default | READ | — | — | YES | PASS | YES | **AGENTIC_READY** |
| `ticket_customer_note` | Trusted + emit | YES default + N1 | WRITE Event | nota Sí | updated\* | YES | PASS | YES | **AGENTIC_READY** |
| `create_ticket` | Trusted + confirm | wired; **not default on** | WRITE Ticket | creacion Sí | created | línea/conv | PASS | YES when on | **AGENTIC_READY_SMALL_GAP** |
| `update_ticket` (evidence) | Trusted | executor only | evidencia fields | no | no | YES | PASS | GAP N1 | **PARTIAL** |
| Admin ticket update/close | RBAC JWT | no | Ticket fields | varies | on close | assignment/RBAC | N/A | N/A | **LEGACY/HANDOFF** |
| `escalate_human` | Motor/confirm | executor; N1 compose | conv state | no | no ticket push | conv | PASS Motor | PARTIAL | **PARTIAL** |
| `close_conversation` | Legacy/Runtime | executor only | conv cerrado | no | no | conv | PARTIAL | no | **LEGACY/HANDOFF** |
| `close_ticket` | helpdesk | **no Action** | Cerrado | actualizacion Sí | closed | RBAC | N/A | N/A | **LEGACY/HANDOFF** |
| `resolved` | — | — | — | — | — | — | — | — | **UNAVAILABLE** |
| SLA breach | sistema | event helper | Event | sla_breach Sí | sla_breached | owner | N/A | N/A | **AGENTIC_READY** (proactive) |

\*N1 self-note: Event yes, push suppressed.

---

## 14. Gaps

1. **`create_ticket` not in default `ACTION_RUNTIME_ACTIONS`** — Runtime path dormant until env CSV (same pattern as other mutators).  
2. **`update_ticket` N1 dispatch missing** — evidence remains Legacy `_append_evidencia`; Runtime XOR not call-site enforced.  
3. **No ActionSpec `close_ticket`** — customer ticket close is helpdesk-only.  
4. **`escalate_human` N1 does not dispatch ActionRequest** — composition with create_ticket.  
5. **`close_conversation` CSAT/Legacy** — Runtime executor incomplete vs N1 Legacy path.  
6. **`ticket.resolved` unsupported** — product uses `Cerrado` only.  
7. **Event→push transaction window** — deferred (2.6F).  
8. **Production smoke** for note/create — NOT VERIFIED.  
9. **Known unrelated FAIL** — PPPoE diagnostic 4B/4D tests.  
10. **show_ticket multi-ticket ambiguity** — weaker than note path (NEEDS_INPUT only on missing id).

---

## 15. External Dependencies

**Implementable now (in-repo authority):**

- Activar `create_ticket` en ACTIONS + ENABLED (rollout)  
- Wire N1 `update_ticket` evidence XOR (behavior-preserving)  
- Optional Runtime wire `close_conversation` with CSAT parity  
- Optional Action `close_ticket` **only if** product wants abonado-initiated close (needs policy/confirm design)

**Requires external / out-of-scope authority (do not invent):**

- BSS/CRM WRITE beyond estate Ticket  
- Payment/Fiserv SoT  
- Commercial catalog / eligibility / pricebook / campaigns  
- Installation work-order / technician agenda SoT  
- True “resolved” workflow if product adds new estado

---

## 16. Recommended Next Implementation

### A — siguiente implementación más pequeña (recomendado)

**Activación gobernada de `create_ticket` en Runtime (rollout):**

- Ya tiene: ActionSpec, confirmation, executor, N1 XOR helper, Event `creacion`, tests 4C/4D.  
- Gap: no está en default ACTIONS + `ACTION_RUNTIME_ENABLED` off.  
- Trabajo: config/rollout + sensores de activación; **sin** nuevo capability.  
- Clasificación post-A esperable: **AGENTIC_READY** (cuando ENABLED+ACTIONS en segmento).

### B — siguiente después de A

**N1 wire XOR para `update_ticket` (evidencia interna)** — preservar semántica no-visible / no-push; no fusionar con `ticket_customer_note`.

### C — dependencias / no ahora

- Abonado `close_ticket` Agentic (nuevo contrato producto + confirm)  
- Unificar escalate_human vs create_ticket composition  
- Outbox Event/push  
- Cualquier BSS/commercial/installation WRITE

---

## 17. Explicit Non-Goals

- No modificar código, tests, config, schemas ni contratos en 2.6J.  
- No tocar Billing 2.1 ni EKO 2.5 conversational freeze.  
- No corregir FAIL diagnóstico PPPoE.  
- No implementar create/update/escalate/close en esta fase.  
- No inventar `resolved` ni capabilities externas.  
- No cambiar `ticket_customer_note` (2.6I intacto).  
- No ampliar mobile / push payload.

---

## Appendix — Evidence anchors (paths)

| Concern | Path |
|---|---|
| Registry | `app/services/eko_action_runtime.py` `bootstrap_registry` |
| Coverage | `app/services/eko_action_coverage.py` |
| Default ACTIONS | `app/config.py` `ACTION_RUNTIME_ACTIONS` |
| N1 create XOR | `canal_abonado._ticket_via_runtime_o_legacy` |
| N1 note wire | `eko_journeys._advance_ticket_customer_note`, `canal_abonado` phrase |
| Events + detector | `estate/repository.add_ticket_event`, `eko_ticket_proactive` |
| Helpdesk | `app/api/v1/tickets.py` |
| States | `config.ESTADOS_TICKET_VALIDOS` |
| Docs prior | `docs/EKO-2.6H…`, `docs/EKO-2.6I…` |

---

## Final Gate

```text
EKO 2.6J — DISCOVERY COMPLETE
```

**Mapa de autoridad real:** el abonado, bajo Runtime on, puede **leer** su ticket y **escribir** una nota customer-visible gobernada; **crear** ticket está tecnicamente listo pero gated; **cerrar ticket**, **reasignar** y la mayoría de mutaciones de campos viven en **helpdesk Legacy**; **escalar** es composición/handoff más que un Effect ticket único; **resolved** no existe.
