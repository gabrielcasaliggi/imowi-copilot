# EKO 2.7C — Incident & Customer Experience Scope

**Status:** SCOPE DEFINITION ONLY  
**Date:** 2026-09-23  
**Product decision:** C — INCIDENT / CUSTOMER EXPERIENCE (2.7B)  
**Mode:** READ ONLY — no code, config, ACTIONS, or production changes  

---

## Baseline

```text
2.6 Agentic Ops: CLOSED
2.7 Discovery: COMPLETE
2.7A: COMPLETE
2.7B: COMPLETE → axis C selected
2.5 Continuity: FROZEN
```

Hard exclusions (unchanged): payment WRITE, BSS EFFECTS, install EFFECT, admin ticket mutate, `update_ticket` customer Action, `escalate_human` in ACTIONS, Sensa/VoIP WRITE, reopen 2.5/2.6, proactive without SoT, Legacy debt cleanup general.

---

## 1. Current flow audit (code evidence)

Primary journey: `internet_sin_conectividad` in `app/services/eko_journeys.py` (`_advance_connectivity`).  
Gates: identity → fixed-internet login count → selection → diagnostic Runtime → explain → optional create_ticket via `_ticket_via_runtime_o_legacy`.  
Selection SoT: `eko_journey.selected_service_ref` (2.5D-1); shadow `login_seleccionado` write-only projection.  
Ticket follow-up: `_advance_ticket` / `_advance_ticket_customer_note`; phrases `_TICKET_NOTE_PHRASES`; resolve via `conv.ticket_id` → UUID in text → unique visible ticket → else ambiguous/missing.

### Caso A — Un solo servicio fijo

| Step | Behavior today |
|---|---|
| Identify service | `_login_count` / BillTrack connectivity logins; if 1, can proceed without menu |
| Active service | `get_selected_ref` or capture/enrich login → `apply_service_ref` |
| Diagnostic | `run_diagnostic_pppoe` (portal connectivity if `service_id`) under covers |
| State kept | journey fields + selected_service_ref + TSS stamps in ctx |
| Customer result | Mapped from connectivity status/reason (canonical portal result) |
| Ticket | Confirmation then XOR create (`journey_connectivity_create_ticket`) |
| Association | `conv.ticket_id`; motivo journey string; abonado trust |
| Continue | Journey may leave connectivity step; ticket queries need ticket intent/phrases |

**Gap (UX):** after ticket, chat may feel “menu reset” if next utterance doesn’t match ticket/note/connectivity resume patterns.

### Caso B — Múltiples servicios / logins

| Step | Behavior today |
|---|---|
| Ambiguity | `n_logins > 1` without selection → `service_selection` / `needs_input` |
| Linguistic selection | `resolve_service_selection` / `looks_like_selection_utterance` (fijo/otro/…) |
| Preserve selection | `selected_service_ref` canonical; cleared only by explicit apply rules |
| Diagnostic uses selection | PPPoE executor reads `get_selected_ref` (not first login invent) |
| Ticket service | Writer uses abonado + context; login projected when selection applied |
| Risk “first service” | Mitigated when journey/Runtime path used; **residual** Legacy phrase paths / non-journey canal may still differ (document, don’t wholesale rewrite) |

**IMO WI / Sensa / no fixed Internet:** `n_logins <= 0` → honest unavailable for fixed Internet diag; redirect to móvil/Sensa/factura — **must preserve**.

### Caso C — Incidente + ticket existente

| Behavior | Evidence |
|---|---|
| Identify ticket | `conv.ticket_id` or UUID in text; else ask |
| Ownership | `ticket_pertenece_abonado` / visible list |
| Context | Conversation + journey state; not full NOC timeline |
| Show | `show_ticket` Runtime when covered |
| Continue | Ticket journey / note phrases |

**Gap:** natural language “¿qué pasó con mi reclamo de internet?” may not always enter `_advance_ticket` without keyword coverage — **INCLUDE** intent/phrase hardening in scope (not new ActionSpec).

### Caso D — Seguimiento / nota

| Behavior | Evidence |
|---|---|
| Ticket id | Same resolve as note helper |
| `ticket_customer_note` | Wired N1 when `covers(note)` |
| Visible + Event | `emit_ticket_customer_note` → `nota` Sí |
| Proactive | ticket.updated path (2.3G) |
| Dedup | detalle hash on emit |
| Prod | **ACTIONS=`create_ticket` only** → `covers(note)=False` → note path unavailable in prod today |

---

## 2. UX / conversational design (target — not implemented)

Must avoid:

* re-asking selected service  
* re-running diagnostic without need  
* losing `ticket_id` after create  
* dumping to general menu after ticket without handoff copy  
* inventing fault / SLA / resolution times  
* LLM turning incomplete diag into “encontramos una falla”  

**Current break points (candidates for 2.7C):**

1. Post-ticket continuity messaging / journey step stickiness  
2. Follow-up phrases incomplete vs customer language (“sigue sin funcionar”)  
3. Prod note gate off → follow-up mutates nothing customer-visible via Runtime note  
4. Possible dual entry (journey vs Legacy canal) confusing UX — document; touch Legacy **only if** required for safety of this journey  

---

## 3. Target journey (design)

```text
START
→ INTENT (internet_sin_conectividad / resume)
→ SERVICE RESOLUTION (identity + fixed-internet eligibility)
→ SERVICE SELECTION (if n>1 or ambiguous ref)
→ DIAGNOSTIC (Runtime PPPoE/portal; selected_service_ref authority)
→ RESULT (status/reason from adapter — not LLM invent)
→ CUSTOMER-FACING EXPLANATION (renderer from trusted result)
→ ACTION (continue checks / confirm ticket / escalate composition)
→ TICKET IF NEEDED (create_ticket XOR Runtime)
→ FOLLOW-UP (show_ticket / ticket_customer_note when covers)
```

| Stage | State | Trusted data | Authority | Action | Next | Fallback |
|---|---|---|---|---|---|---|
| Intent | journey name | texto | phrase/journey detect | set journey | identity/selection | other domains |
| Identity | abonado | TrustedContext | auth | ask DNI | selection | stop |
| Selection | selected_service_ref | catalog BillTrack | resolve_service_selection | ask options | diagnostic | unavailable |
| Diagnostic | TSS/result | portal/Radius | Runtime executor | run_diagnostic_* | explain | needs_input/unavailable |
| Explain | last_diagnostic_result | result codes | mapping tables | send_message | action | honest incomplete |
| Ticket | confirmation / ticket_id | Policy+XOR | create_ticket | confirm→create | follow-up | reject |
| Follow-up | ticket_id | ownership | show/note | note/show | end/wait | NEEDS_INPUT/DENY |

---

## 4. Continuity (2.5 frozen)

Reuse existing:

* `selected_service_ref`  
* `conv.ticket_id`  
* journey fields (`last_diagnostic_result`, `pending_confirmation`, options, correlation_id)  
* TSS ctx stamps  
* handoff continuity stamps (2.5D-4)  

**No new SoT fields** unless a blocker proves absence. Prefer journey step / messaging fixes over schema.

---

## 5. Ticket continuity chain

```text
diagnostic → create_ticket (XOR) → ticket_id on conv
→ show_ticket / ticket_customer_note → TicketEvent → proactive
```

Guarantees already: ownership on note/show; create idempotent via `conv.ticket_id`; XOR helper for create.  
**2.7C must not** introduce dual create; must not bypass Policy.

---

## 6. `ticket_customer_note` production gate

| Item | Status |
|---|---|
| Executor / ActionSpec / Policy / ownership / sanitize | YES |
| Runtime + Event + proactive + idempotency | YES (2.6I) |
| N1 wire | YES |
| Default ACTIONS (code) | includes note |
| Production effective ACTIONS | **create_ticket only** |

Adding `ticket_customer_note` to prod CSV:

* Requires restart; boot log must show both actions (or CSV list)  
* Enables N1 note Runtime + customer Events + push path  
* Does **not** enable update_ticket/escalate  
* Needs controlled smoke (authorized identity)  

```text
ticket_customer_note gate classification = READY_WITH_GUARDRAILS
```

READY in product/code; prod enable = **ops decision** + smoke; not BLOCKED on missing implementation.

**Future smoke (not now):** after CSV+restart, abonado authorized → phrase note on owned ticket → one Event `nota` → `eko_action` path=runtime → no foreign ticket.

---

## 7. Multi-service rules

Preserve:

* only fixed-internet diagnosticable types for PPPoE path  
* IMOWI/Sensa/VoIP not treated as fixed Internet login diag  
* selection required when ambiguous  
* `ownership_matches_ref`  

2.7C work: ensure journey UX never skips selection when `n>1`; regression tests for “otro/fijo” refs.

---

## 8. Customer-facing explanations

Must stay bound to connectivity reason codes / status (portal_connectivity / Radius), outage flags, and honest unavailable — **LLM CONTENT ≠ AUTHORITY**.

2.7C may tighten renderer mapping / copy; must not invent outage from incomplete probe.

---

## 9. CASI / Policy / Motor

MUST PRESERVE full chain. No effects from LLM handlers. No conversational bypass of Runtime for note/create.

---

## 10. Runtime / Legacy XOR

* create_ticket: XOR helper — PASS (2.6P) — preserve  
* ticket_customer_note: N1 Runtime when covers; no Legacy customer-visible note — preserve  
* Residual Legacy creates (2.6M): **document**; touch only if a specific path breaks 2.7C safety  

---

## 11. Proactive

INCLUDE reuse of existing ticket/outage events only.  
EXCLUDE new billing/connectivity-transition proactive.

---

## 12. Portal / Mobile

| Surface | 2.7C |
|---|---|
| Backend / journeys / copy | primary INCLUDE |
| Portal | EXCLUDE unless DTO gap blocks continuity (unlikely) |
| Mobile | EXCLUDE functional changes; Activity already shows ticket Events — optional EXCLUDE polish |

---

## 13. Test plan (minimum)

* Single service “sin internet” → diag uses that service  
* Multi-service → selection required; after select → that service only  
* Existing ticket query → correct id + ownership  
* Follow-up “sigue sin funcionar” → resolves ticket (phrase coverage)  
* Note → ownership; Event when covers  
* Foreign ticket → DENY  
* Ambiguous tickets → NEEDS_INPUT  
* No ticket → explicit ask  
* CASI: LLM proposal cannot force note visibility/ownership  
* XOR create: Runtime ON → Legacy 0; OFF → Runtime 0  
* Regression: 2.5D*, 2.6I, 2.6K, 2.6N-C, diagnostics, tickets, proactive ticket, billing smoke (no expand)  

---

## 14. Production

```text
This phase: NO prod change, NO ACTIONS change, NO note activation, NO tickets
```

If later activating note: edit ACTIONS CSV to include `ticket_customer_note` (keep create), restart, verify boot log, smoke as above, rollback = remove note from CSV + restart.

---

## 15. Scope final table

| Área | Estado |
| --- | --- |
| Sin internet journey | **INCLUDE** (UX/continuity on existing journey) |
| Multi-service selection | **INCLUDE** (harden + tests) |
| Diagnostic continuity | **INCLUDE** |
| Ticket continuity | **INCLUDE** |
| ticket_customer_note | **DECISION** (READY_WITH_GUARDRAILS; prod CSV separate) |
| Portal | **EXCLUDE** (default) |
| Mobile | **EXCLUDE** (default) |
| Proactive | **INCLUDE** reuse only / **EXCLUDE** new events |
| CASI | **MUST PRESERVE** |
| 2.5 | **FROZEN** |
| 2.6 | **CLOSED** |

---

## 16. Exit criteria (proposed)

1. “Sin internet” uses selected service for diag  
2. Multi-service never diags ambiguous selection  
3. Ticket continuity with conversation (`ticket_id`)  
4. Customer can follow incident without full journey reset  
5. Explicit prod gate for `ticket_customer_note` documented (enabled or deferred)  
6. Ownership enforced  
7. CASI PASS  
8. Runtime/Legacy XOR PASS for create (+ note if enabled)  
9. No new BSS effects  
10. No invented states/SLA/diag claims  
11. Relevant regression suites PASS  
12. 2.5/2.6 not reopened  

---

## Implementation files expected (for later 2.7C code phase — not now)

Likely touch (estimate from audit):

* `app/services/eko_journeys.py` — connectivity/ticket continuity, phrases, post-ticket step  
* `app/services/canal_abonado.py` — only if journey/canal handoff gap for this flow  
* `app/services/eko_service_selection.py` — only if selection edge-case blocker  
* Possibly copy/renderer helpers for connectivity results  
* `tests/test_eko_*` new 2.7C suite + extend 2.6I/selection  

Unlikely: `app/config.py` defaults (prod CSV is ops); mobile; portal DTOs; proactive detectors.

---

## Safety

```text
Production touched: NO
Configuration changed: NO
Runtime changed: NO
Tickets created: 0
Tickets modified: 0
Implementation performed: NO
```
