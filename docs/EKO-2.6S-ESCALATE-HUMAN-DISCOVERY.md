# EKO 2.6S — Escalate Human Discovery

**Date:** 2026-09-23  
**Mode:** READ ONLY — discovery/audit only  
**Context:** `create_ticket` Runtime proved in production (2.6P); `update_ticket` left PARTIAL (2.6R)  

---

## Status

```text
PARTIAL
```

*(Customer-facing “hablar con agente + ticket” is already delivered via **composition** with `create_ticket` Runtime — not via ActionRequest `escalate_human`.)*

---

## Executive Summary

`escalate_human` **exists** as ActionSpec + Runtime executor + confirmation plumbing, but N1 **does not** dispatch `ActionRequest("escalate_human")`.

Documented composition (`ESCALATE_COMPOSITION`):

```text
escalate_human → create_ticket (N1 escape/handoff)
```

What N1 actually does on `agente` / human-request escape:

```text
N1 escape → _ticket_via_runtime_o_legacy → create_ticket Runtime
         → confirmation → Ticket + TicketEvent(creacion) → espera_agente
```

That path **reuses the 2.6P-proven** `create_ticket` Runtime (XOR helper, CASI, Event).

The Action `escalate_human` executor **only** sets `conv.estado=espera_agente` + notify + handoff stamp — **no ticket**, **no TicketEvent**. It is **not** in default `ACTION_RUNTIME_ACTIONS`. Confirmation-resume in canal lists `escalate_human` but **only implements** the post-confirm branch for `create_ticket` (escalate confirm → falls through / no effect).

Therefore: product escalate-with-ticket = **READY via create_ticket**; named Action `escalate_human` = **PARTIAL / unwired**.

---

## Current Capability

| Component | Status |
|---|---|
| Formal action `escalate_human` | **YES** — registry ActionSpec |
| ActionSpec | **YES** — `confirmation_required=True`, `idempotency=PROTECTED` |
| Capability contract | **YES** — type ESCALATION, HIGH, notes composition |
| Capability discovery | **YES** — 2.6H/J/coverage |
| Runtime executor | **YES** — `_exec_escalate_human` |
| Runtime dispatch (generic) | **YES** if covers + someone calls `dispatch_runtime` |
| N1 dispatch of Action | **NO** — no `dispatch_runtime("escalate_human")` found |
| Legacy / handoff | **YES** — escape → create_ticket; Motor `authorize_escalate`; diag IA ACT_ESCALATE |
| In default ACTIONS | **NO** |
| What it does today (executor) | `conv.estado → espera_agente`; `notify_espera_agente`; `stamp_handoff_out`; **no Ticket** |

Primary files:

* `app/services/eko_action_runtime.py` — `_exec_escalate_human`, registry  
* `app/services/eko_action_coverage.py` — `ESCALATE_COMPOSITION`, RUNTIME_EXECUTOR_ONLY  
* `app/services/eko_capability_contract.py` — contract  
* `app/services/canal_abonado.py` — escape → `_ticket_via_runtime_o_legacy`; `_talvez_runtime_confirmation_pending`  
* `app/domain/conversation_motor.py` — `authorize_escalate` (no ticket write)  
* `app/domain/action_proposal.py` — `evaluate_escalate`  
* `app/services/eko_action_bridge.py` — confirmation prompts; resolve confirm for create/escalate  
* `app/services/eko_handoff_continuity.py` — stamp on escalate  

---

## N1 Dispatch

| Stage | Status |
|---|---|
| N1 “quiero agente” / `agente` | **YES** — `es_escape_agente` / human request → `_ticket_via_runtime_o_legacy` |
| Proposal as `escalate_human` Action | **NO** |
| Proposal as `create_ticket` (composition) | **YES** |
| Policy | Via create_ticket Runtime when covers |
| Confirmation | Via create_ticket (2.6P: generic NEEDS_CONFIRMATION message observed) |
| Runtime `escalate_human` | **NO** on hot path |
| Legacy create / XOR create | **YES** — create helper |

Motor path: `authorize_escalate` may ALLOW `ACT_ESCALATE`; canal then effects ticket/espera — **Motor does not create tickets** (documented).

---

## Runtime

| Flag | Value |
|---|---|
| RUNTIME_EXECUTOR | **YES** |
| RUNTIME_DISPATCH | **PARTIAL** — infrastructure yes; N1 wire **no** |
| RUNTIME_COVERAGE | **PARTIAL** — RUNTIME_EXECUTOR_ONLY; not in default ACTIONS |
| CREATE_TICKET_REUSE | **YES** on N1 composition (escape → create_ticket Runtime when ENABLED+ACTIONS) |

Two distinct Runtime shapes:

1. **Composition (live N1):** create_ticket Runtime (2.6P).  
2. **Named Action (dormant):** escalate_human → espera_agente only.

---

## Create Ticket Reuse

```text
CREATE_TICKET_REUSE = YES
```

N1 escape already calls `_ticket_via_runtime_o_legacy` → same Runtime executor / XOR / Event path proven in 2.6P (`escape_agente` → confirm → `create_ticket_confirmed` → TicketEvent creacion).

`_exec_escalate_human` does **not** call `create_ticket` or `_crear_ticket_n2`.

---

## Authority / CASI

| Concern | Finding |
|---|---|
| Who decides user wants human? | Phrase gates (`es_escape_agente`, `pide_humano*`) + Motor `evaluate_escalate` / `authorize_escalate` |
| Who authorizes escalation? | Motor for ACT_ESCALATE; create_ticket Policy+Trusted confirmation for ticket path |
| Motivo | Deterministic strings (e.g. “Cliente solicitó agente/técnico”) + conversation context — not free LLM authority |
| LLM params | Escalation ActionRequest unused on N1; create_ticket sanitizes untrusted keys |
| LLM executes directly? | **NO** for ticket write |
| ticket_id from LLM? | create_ticket path uses writer / conv — not escalate_human params |
| Policy + Motor | **YES** on create path; Motor alone on escalate authorization |

```text
CASI = PASS (for create_ticket composition path used by N1 escalate)
CASI for unused escalate_human Action path = PASS-shaped (TrustedContext + confirmation_required) but unwired
```

---

## Ownership

Escalation-with-ticket uses **create_ticket** ownership (abonado TrustedContext; writer links ticket to conv).

| Case | Behavior (N1 create composition) |
|---|---|
| A) Identified abonado | ALLOW after confirm → ticket |
| B) Ambiguous / multi-account | Prior service-selection / multi_cuenta gates may NEEDS_INPUT before diagnose; escape can still ticket with available abonado |
| C) Multiple accounts | Same as create_ticket / selection gates — not escalate_human-specific |
| D) Insufficient context | Still can create with motivo + padón if abonado bound |
| E) Existing `conv.ticket_id` | create_ticket **already_done** / writer early-return |
| F) No ticket yet | create after confirmation |

`_exec_escalate_human` alone: needs conv+db; **already_done** if already `espera_agente`/`con_agente`; does not check ticket ownership (no ticket).

---

## Confirmation

| Path | Confirmation |
|---|---|
| ActionSpec `escalate_human` | **YES** (`confirmation_required=True`); prompt: «¿Confirmás que querés hablar con un agente?» |
| N1 escape → create_ticket | **YES** (create_ticket REQUIRED) — 2.6P production |
| `_talvez_runtime_confirmation_pending` | Accepts pending action ∈ {create_ticket, escalate_human, close_conversation} **if** `covers(action)` |
| Post-confirm body | **Only `create_ticket` implemented**; escalate_human confirm → **returns None** (gap if ACTIONS ever includes escalate_human alone) |

---

## Ticket Creation

Via **composition only** (`_crear_ticket_n2` / Runtime `_exec_create_ticket`):

* Motivo / descripción from deterministic canal strings + handoff resumen + evidence snippet  
* Categoría / destino / nivel from `destino_n2_canal` / intent tags  
* Canal / origen from conversation  
* Actor style `bot:{telefono}` on writer  
* **Not** from escalate_human executor  

LLM does not authoritatively set ticket fields on this path (same CASI as create_ticket).

---

## TicketEvent

| Path | Event |
|---|---|
| create_ticket Runtime (N1 escape) | **YES** — `creacion` (2.6P) |
| `_exec_escalate_human` alone | **NO** |

---

## Proactive / Push

Inherits **create_ticket** / `ticket.created` pipeline when a ticket is created (same as 2.6P).

`_exec_escalate_human`: handoff notify to agents (`notify_espera_agente`) — not customer TicketEvent push.

---

## XOR Runtime/Legacy

| Path | XOR |
|---|---|
| create_ticket via `_ticket_via_runtime_o_legacy` | **PASS** (2.6K/2.6P) |
| Direct Legacy `_crear_ticket_n2` sites (2.6M) | Still **Legacy-only** residual |
| escalate_human executor vs create | **Different side effects**; no XOR between them — if both fired: espera_agente + ticket possible |

```text
RUNTIME_XOR_LEGACY (create composition) = PASS
RUNTIME_XOR_LEGACY (escalate_human Action vs create) = PARTIAL / N/A until unified product decision
```

---

## Idempotency / Duplicate Protection

| Scenario | Protection |
|---|---|
| Double escape after ticket | `conv.ticket_id` → already_done / early return |
| Double confirm create | Same |
| Double escalate_human executor | already_done if already espera_agente |
| Duplicate Event creacion | Writer creates once; Event with ticket create |
| Retry Runtime create | PROTECTED via conv.ticket_id |

```text
Idempotency (create composition) = PASS
Idempotency (escalate_human alone) = PASS for estado; no ticket concerns
```

---

## Existing Tests

| Suite | Covers |
|---|---|
| 4D coverage / ESCALATE_COMPOSITION | composition string; RUNTIME_EXECUTOR_ONLY |
| 4E capability | escalate in mutators; confirmation required |
| 2.5D-4 | `_exec_escalate_human` stamps continuity |
| 2.6K / 2.6N-C | escalate_human **not** in default ACTIONS |
| 4A decision catalog | escalate_human id present |
| QA anti-ticket / escape | `es_escape_agente` + ticket creation behavior |
| 2.6P smoke (prod) | escape → create_ticket Runtime (not escalate Action) |

**Missing:** N1 test that `dispatch_runtime("escalate_human")` is never called on escape; confirmation-resume for escalate_human when covers; XOR if both Actions enabled.

---

## Relation to 2.6P

```text
Can escalate_human safely reuse create_ticket Runtime proven in 2.6P?
→ YES (already does, via N1 composition)
```

**PARTIAL** only if the goal is “N1 must dispatch ActionSpec escalate_human”: that would need an explicit product decision (compose vs replace vs dual) and wire — **not done**; enabling ACTIONS=`escalate_human` alone is **unsafe/incomplete** (confirm resume gap; no ticket).

Recommended product stance for 2.6 close-out: treat **customer escalate = create_ticket Runtime** (already production); keep Action `escalate_human` documented as executor-only / composition note; **do not** add to ACTIONS without a dedicated implementation phase.

---

## Gaps

1. No N1 `dispatch_runtime("escalate_human")`.  
2. Not in default ACTIONS (intentional).  
3. Executor does not create ticket / Event.  
4. Confirmation pending accepts escalate_human but post-confirm handler **missing**.  
5. Residual Legacy direct creates still bypass Runtime (2.6M) — same as create audit.  
6. Product ambiguity: escalate ≠ create until decided (capability contract `migration_precondition`).  
7. No automated test that escape never calls escalate ActionRequest.

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

---

## Classification rationale

| Label | Fit |
|---|---|
| AGENTIC_READY | For **create_ticket composition** yes; for Action `escalate_human` **no** |
| AGENTIC_READY_SMALL_GAP | Would imply only activate ACTIONS — **false** (confirm resume incomplete; no ticket in executor) |
| PARTIAL | **YES** — Action pieces exist; N1 uses create composition instead |
| LEGACY_HANDOFF | Incomplete — create path is Runtime in prod |
| UNAVAILABLE | No — usable composition + executor exist |

```text
FINAL = PARTIAL
```
