# EKO 2.6R — Update Ticket Discovery

**Date:** 2026-09-23  
**Mode:** READ ONLY — discovery/audit only  
**Scope:** capability `update_ticket` (Action Runtime + Legacy writers)  
**Not done:** code/config/DB/prod changes; no tickets created/modified; Runtime not activated  

---

## Status

```text
PARTIAL
```

---

## Executive Summary

`update_ticket` **exists** as a registered ActionSpec with a real Runtime executor (`_exec_update_ticket`) that appends **internal evidence** (`evidencia` / `descripcion_falla`) under ownership checks. It is **intentionally not** the customer-visible / push path (that is `ticket_customer_note`, 2.6E/2.6I).

It is **excluded** from default `ACTION_RUNTIME_ACTIONS`, so `covers(update_ticket)=False` unless explicitly listed in env CSV **and** `ACTION_RUNTIME_ENABLED=true`. Coverage status: **RUNTIME_EXECUTOR_ONLY**.

N1 **does not** call `dispatch_runtime("update_ticket")`. Hot path uses Legacy `_append_evidencia_ticket` directly. There is **no XOR helper** binding Legacy append vs Runtime for this action.

Therefore the agentic chain:

```text
N1 → Proposal → Policy → Confirmation → Runtime → update_ticket → TicketEvent → proactive
```

is **not** complete for `update_ticket`: Confirmation is NOT_REQUIRED; TicketEvent/proactive are **by design absent** on this action; N1 Runtime dispatch is **absent**.

---

## Capability

| Question | Evidence |
|---|---|
| Formal action? | **YES** — `ActionSpec("update_ticket", _exec_update_ticket, …)` in `eko_action_runtime.bootstrap_registry` |
| ActionSpec? | **YES** — `idempotency="PROTECTED"`; `confirmation_required` default **False** |
| Capability contract? | **YES** — `eko_capability_contract` entry `update_ticket` (MUTATION, HIGH, auth required) |
| Capability discovery? | **YES** — listed in 2.6H / 2.6J / coverage matrix |
| In default `ACTION_RUNTIME_ACTIONS`? | **NO** — `app/config.py` comments + frozenset omit it; tests assert absence |
| `covers()`? | Only if ENABLED ∧ name ∈ ACTIONS; default → **False** |
| Parameters (code) | `ticket_id` (params or `conv.ticket_id`); `nota` / `note` |
| Mutable ticket fields (Runtime executor) | Appends to `Ticket.evidencia`; may append snippet to `descripcion_falla` via `_append_evidencia_ticket` — **not** estado/prioridad/asignación/categoría |

Primary files:

* `app/services/eko_action_runtime.py` — `_exec_update_ticket`, registry  
* `app/services/eko_action_coverage.py` — RUNTIME_EXECUTOR_ONLY  
* `app/services/eko_capability_contract.py` — contract  
* `app/services/canal_abonado.py` — `_append_evidencia_ticket`  
* `app/estate/repository.py` — `update_ticket` (helpdesk; **different** writer)  
* `app/api/v1/tickets.py` — PUT/close/reassign → `repo.update_ticket`  
* `app/services/eko_decision_catalog.py` — `update_ticket_evidence`  

---

## Runtime

| Flag | Value |
|---|---|
| RUNTIME_EXECUTOR | **YES** — `_exec_update_ticket` |
| RUNTIME_DISPATCH | **YES** for generic `dispatch_runtime` / `execute_action` **if** covers; **NO** N1 call site found |
| RUNTIME_COVERAGE | **PARTIAL** / **RUNTIME_EXECUTOR_ONLY** (gate off by default; no N1 wire) |
| LEGACY_PATH | **YES** — `_append_evidencia_ticket` from canal N1; helpdesk `repo.update_ticket` |

Reconstructed Runtime path (**if** ENABLED + ACTIONS includes `update_ticket` + someone calls `execute_action`/`dispatch_runtime`):

```text
ActionRequest(update_ticket, {ticket_id?, nota})
→ sanitize_parameters
→ evaluate_policy (ALLOW if abonado/org; confirmation NOT required)
→ _exec_update_ticket
→ ticket_pertenece_abonado
→ _append_evidencia_ticket
→ ActionResult success {ticket_id}
```

No TicketEvent. No proactive emit in this executor.

---

## Authority / CASI

| Concern | Finding |
|---|---|
| Who decides “user wants update”? | N1 Legacy call sites decide to append evidence; Runtime would need Proposal/decision — **no N1 proposal wire** for `update_ticket` found |
| Who authorizes? | Policy + executor ownership (`ticket_pertenece_abonado`); TrustedContext abonado/org |
| Who sets `ticket_id`? | `req.parameters["ticket_id"]` **or** `conv.ticket_id` |
| LLM free `ticket_id`? | **`ticket_id` is not in `_UNTRUSTED_PARAM_KEYS`** — LLM proposal **may** carry `ticket_id`; foreign tickets still **DENY** via ownership |
| LLM mutable fields? | Only `nota`/`note` used; no estado/priority from params |
| LLM direct executor? | No — must pass `execute_action` / registry; still **no confirmation gate** |
| Sanitize | Strips identity/visibility/notify/actor keys; **does not** strip `ticket_id` or `nota` |
| LLM ≠ authority | **PASS with caveat**: ownership blocks foreign tickets; sibling ticket_id of same abonado could be proposed by LLM without confirmation |

```text
CASI for executor ownership = PASS (foreign DENY)
CASI for “ticket_id only from trusted context” = PARTIAL (params allowed; contract text says trusted_context)
```

---

## Ownership

| Case | Behavior (executor code) |
|---|---|
| A) Own ticket + nota | **ALLOW** → success |
| B) Other abonado’s ticket | **DENY** `foreign_ticket` |
| C) Nonexistent ticket_id | **DENY** `foreign_ticket` (same branch as foreign; `t is None`) |
| D) Multiple tickets same abonado | No auto-resolve; needs `ticket_id` or `conv.ticket_id` — else **NEEDS_INPUT** `missing_ticket_or_note` |
| E) Ambiguous | No dedicated `ambiguous_ticket` (unlike `ticket_customer_note`) |
| F) Conv without ticket + no param | **NEEDS_INPUT** |
| G) Other context/account | **DENY** if ownership fails |

Missing abonado → **DENY** `missing_abonado`.

---

## Confirmation

| Item | Value |
|---|---|
| Required on ActionSpec? | **NO** (`confirmation_required` unset → False) |
| Coverage / 4E | NOT_REQUIRED; 4E asserts update_ticket exception to “requires_confirmation” |
| Pending / `pending.act` | N/A for this action’s happy path |
| After confirm | N/A |

```text
Confirmation: NOT_REQUIRED
```

There is **no** enforced `Proposal → Policy → Confirmation → Runtime` for updates; Policy can ALLOW immediately.

---

## Mutable Fields

### Runtime `update_ticket` / `_append_evidencia_ticket`

| Field | Class |
|---|---|
| `evidencia` (append, dedup substring, ≤800 chars block) | **SAFE_FOR_N1** (internal) |
| `descripcion_falla` (append snippet ≤2000) | **SAFE_FOR_N1** (internal) |
| estado, nivel, destino, asignado_a, SLA, resolución, … | **UNSUPPORTED** by this executor |

### Helpdesk `repo.update_ticket` / API

| Field | Class |
|---|---|
| estado, resolución, descripción, nivel, destino, proveedor, motivo_escalamiento, estado_sla, ticket_externo_id, asignado_a | **ADMIN_ONLY** / helpdesk API |
| Auto TicketEvent `actualizacion`/`reasignacion` | Admin path (visible_cliente mostly No; cierre Sí) |

**Gap:** backend helpdesk can mutate far more than N1 Runtime `update_ticket`; N1 must not be given that surface via this ActionSpec (currently it is not).

Customer-visible notes are **`ticket_customer_note`**, not `update_ticket`.

---

## Ticket Events

| Path | Event? |
|---|---|
| Runtime `_exec_update_ticket` | **NO** — documented intentional (2.6E tests) |
| Legacy `_append_evidencia_ticket` | **NO** |
| Helpdesk `repo.update_ticket` | **YES** — `actualizacion` / `reasignacion` (not this Action) |
| `ticket_customer_note` | **YES** — separate ACT |

```text
TicketEvent for Runtime update_ticket = NO (by design)
exactly one event per Runtime mutation = N/A (zero events)
```

---

## Proactive / Push

Runtime `update_ticket`: **no** push / no proactive detector trigger (no Event).

Helpdesk close → Event visible Sí → existing 2.3G pipeline may push — **not** via Action `update_ticket`.

Customer push updates: **`ticket_customer_note`** / admin Event paths.

---

## Legacy Paths

| Site | Function / caller | N1-facing? | XOR w/ Runtime? |
|---|---|---|---|
| `canal_abonado._append_evidencia_ticket` | Writer shared by Runtime executor | YES (multiple callers) | **NO** dedicated XOR |
| Callers (approx): cierre resuelto; identificación en cola; espera_agente anotaciones; otros flujos canal | Direct Legacy | YES | Parallel to Runtime if both enabled |
| `repo.update_ticket` | `api/v1/tickets.py` PUT/close/reassign; `agents/pipeline.py`; `seguimiento_ticket.py` | Agent/admin | Outside Action Runtime |
| Decision catalog | Documents `_append_evidencia_ticket` as implementation | — | — |

No `dispatch_runtime("update_ticket")` in N1 journeys/canal found.

---

## XOR

```text
RUNTIME_XOR_LEGACY: FAIL / NOT_APPLICABLE for dual-path safety
```

* Not PASS: no helper that forbids Legacy append when `covers(update_ticket)`.  
* Residual risk: if ACTIONS later includes `update_ticket` **and** N1 still calls `_append_evidencia_ticket` directly, dual writes of evidence are possible (substring dedup mitigates identical blocks only).

---

## N1 Dispatch

| Stage | Status |
|---|---|
| N1_PROPOSAL | **NO** dedicated journey/phrase → `update_ticket` ActionRequest found |
| POLICY | **YES** if execute_action invoked |
| CONFIRMATION | **NO** (not required) |
| RUNTIME_DISPATCH | **NO** on N1 hot path |
| LEGACY_DISPATCH | **YES** — `_append_evidencia_ticket` |

Customer-visible “update my ticket” N1 intent is wired to **`ticket_customer_note`** (2.6I), not `update_ticket`.

---

## Existing Tests

| Suite | Covers | Gaps |
|---|---|---|
| `test_4b_update_ticket_foreign_denied_*` | Foreign DENY; PROTECTED | No ambiguous; no Event assert |
| `test_26e_update_ticket_evidence_only_no_event_no_push` | Success append; **0** events; **0** push | N1 dispatch |
| `test_26i_update_ticket_remains_internal_*` | Separation from note | — |
| `test_26g` / F7 / 2.6K / 2.6N-C | Not in default ACTIONS; covers False | Activation wire |
| 4D / 4E coverage & capability | RUNTIME_EXECUTOR_ONLY; confirmation exception | XOR N1 |

**Not covered:** N1 phrase → Runtime update_ticket; XOR vs Legacy append; confirmation (N/A); TicketEvent from this action (intentionally none).

---

## Gaps

1. **N1 Runtime dispatch missing** — no canal/journey `dispatch_runtime("update_ticket")`.  
2. **Not in default ACTIONS** — even with ENABLED=true, default set does not cover it (must CSV — **not recommended without wire + XOR**).  
3. **No XOR** vs Legacy `_append_evidencia_ticket`.  
4. **No TicketEvent / proactive** on this action (by design) — product flow “update → Event → push” is **`ticket_customer_note`**, not `update_ticket`.  
5. **Confirmation not required** — differs from create/escalate/close.  
6. **`ticket_id` sanitization** — not stripped from LLM params; ownership is the backstop.  
7. **Ambiguous multi-ticket** — weaker than note (`needs_input` only if both id and nota missing).  
8. **Nonexistent ticket** reported as `foreign_ticket` (not `ticket_not_found`).  
9. Helpdesk `repo.update_ticket` is a **separate** mutator surface (ADMIN_ONLY) — do not conflate with Action Runtime.

---

## Production Safety

```text
production touched: NO
tickets created: 0
tickets modified: 0
configuration changed: NO
Runtime activated: NO
database changed: NO
```

No remote hosts contacted. Only deliverable: this document.

---

## Classification rationale

| Bar | Met? |
|---|---|
| AGENTIC_READY (full chain incl. Event+proactive) | **NO** |
| AGENTIC_READY_SMALL_GAP (only activate/config) | **NO** — missing N1 wire + XOR; Event path is a different ACT |
| PARTIAL | **YES** — executor + ownership + tests; no N1 Runtime path; no Event |
| LEGACY_HANDOFF | Partial flavor for N1 evidence — but executor exists → prefer PARTIAL |
| UNAVAILABLE | **NO** — usable executor exists in tests |

```text
FINAL = PARTIAL
```
