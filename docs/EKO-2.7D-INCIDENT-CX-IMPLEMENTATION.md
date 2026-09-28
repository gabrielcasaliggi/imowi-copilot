# EKO 2.7D — Incident & Customer Experience Implementation

**Status:** IMPLEMENTED (local / test harness)
**Date:** 2026-09-23
**Baseline:** 2.6 CLOSED · 2.7 Discovery/A/B COMPLETE · 2.7C SCOPE COMPLETE
**Axis:** C — INCIDENT / CUSTOMER EXPERIENCE

---

## Implementation performed

Minimum changes to make `internet_sin_conectividad` a coherent incident journey:

1. **Phrase coverage (2.7D)** for follow-up and note intents (`sigue sin funcionar`, `todavía no tengo internet`, `quiero agregar que…`, reclamo status variants).
2. **Incident continuity gate** in `_advance_connectivity`: when `conv.ticket_id` is set and the utterance is symptom follow-up / connectivity repeat (without explicit re-diagnose), do **not** re-probe or create another ticket; keep `selected_service_ref` and return `already_done` + `incident_continuity`.
3. **Note / show handoff** from the same gate when note or ticket-status phrases match (still via Policy → Runtime).
4. **Post-ticket copy** that invites follow-up in the same chat without inventing SLA.
5. **`espera_agente` hook** in `canal_abonado._try_incident_cx_en_espera`: after N2 handoff, follow-up phrases still reach Journeys (note / continuity / show) without reopening generic N1, and without leaving the human queue.

`ticket_customer_note` remains **READY_WITH_GUARDRAILS** — code path ready; production ACTIONS **not** changed.

---

## Files changed

| File | Role |
|---|---|
| `app/services/eko_journeys.py` | Phrases, continuity gate, post-ticket UX |
| `app/services/canal_abonado.py` | espera_agente → incident CX bridge |
| `tests/test_eko_incident_cx_2_7d.py` | Dedicated 2.7D suite (created) |
| `docs/EKO-2.7D-INCIDENT-CX-IMPLEMENTATION.md` | This document (created) |

**Not modified:** 2.7C scope doc, config, ACTIONS, portal, mobile, Runtime registry, Policy, CASI authorities, production.

---

## Behavioral changes

| Scenario | Before (gap) | After |
|---|---|---|
| Single-service “sin internet” | Existing diag path | Unchanged authority; tests assert `login_used` / `service_id` |
| Multi-service ambiguous | Selection / needs_input | Unchanged; regression asserts no diag/ticket |
| After selection | Diag via `selected_service_ref` | Unchanged; continuity of ref asserted |
| Repeat “todavía no tengo internet” with ticket | Could re-enter diag | Continuity: no duplicate ticket, no probe |
| “sigue sin funcionar” with ticket | Weak phrase coverage; lost in espera_agente | Continuity in journey + espera hook |
| “quiero agregar que…” | Partial phrases | Note journey / Runtime when covers |
| Post-create ticket message | Short handoff | Mentions follow-up / note without SLA |

---

## Tests

Module: `tests/test_eko_incident_cx_2_7d.py`

| # | Scenario | Asserts |
|---|---|---|
| 1 | Single service | Correct service ref + diag |
| 2 | Multi ambiguous | needs_input; no diag; no ticket |
| 3 | Multi after selection | Diag uses selected login/service_id |
| 4 | Existing ticket + repeat | `incident_continuity`; no duplicate |
| 5 | Follow-up note | Owned ticket + TicketEvent nota |
| 6 | Foreign ticket | DENY |
| 7 | Ambiguous tickets | NEEDS_INPUT |
| 8 | No ticket | missing_ticket |
| 9 | CASI | LLM cannot force ownership |
| 10 | XOR | Runtime ON → Legacy 0; OFF → Legacy 1; note gate off → unavailable |
| + | espera_agente hook | Follow-up stays `espera_agente` |

---

## Regression results (local)

Executed green (representative):

* `tests/test_eko_incident_cx_2_7d.py` (15)
* `tests/test_eko_agentic_journeys_5.py`
* `tests/test_eko_n1_ticket_customer_note_2_6i.py`
* `tests/test_eko_create_ticket_runtime_2_6k.py`
* `tests/test_eko_runtime_isolation_2_6nc.py`
* `tests/test_eko_ticket_customer_note_2_6e.py`
* `tests/test_eko_canonical_service_read_2_5d1.py`
* `tests/test_eko_playbook_handoff_continuity_2_5d4.py`
* `tests/test_eko_conversational_regression_2_5c.py`
* `tests/test_eko_service_management_2_2c.py`
* `tests/test_eko_effective_config_observability_2_6q.py`

`ruff check` on touched Python files: PASS.

Known unrelated PPPoE / Legacy debt: **not** addressed (OUT_OF_SCOPE per 2.7C).

---

## Known limitations

1. **Production `ticket_customer_note` still OFF** (ACTIONS typically `create_ticket` only) → note path returns honest unavailable when `covers(note)=False`.
2. Continuity gate requires incident context (`last_diagnostic_result` / `create_ticket` / `pppoe_informado` / `step=done`). A bare `ticket_id` alone on a brand-new journey start does not block a first diagnostic.
3. Explicit re-diagnose phrases still allow a new probe even with an open ticket.
4. Residual Legacy create paths outside this journey remain documented 2.6 debt — not cleaned.
5. Portal / mobile UI unchanged; Activity already surfaces TicketEvents when note is enabled later.

---

## Out of scope (confirmed)

* payment WRITE / BSS / install EFFECT / Sensa-VoIP WRITE
* `update_ticket` / `escalate_human` as customer Actions
* New proactive event types
* General Legacy cleanup
* Reopen 2.5 / 2.6
* Production ACTIONS / env / smoke

---

## Production activation requirements (`ticket_customer_note`)

**Not performed in 2.7D.**

When ops approve:

1. Add `ticket_customer_note` to effective `ACTION_RUNTIME_ACTIONS` CSV (keep `create_ticket`).
2. Restart API; confirm boot log lists both actions (2.6Q observability).
3. Smoke (authorized identity only): owned ticket → note phrase → one `TicketEvent` tipo `nota` visible → `eko_action` path=runtime → foreign ticket DENY.
4. Rollback: remove note from CSV + restart.

---

## Exit gate checklist

| # | Criterion | Result |
|---|---|---|
| 1 | Single-service correct service | PASS |
| 2 | Multi no diag when ambiguous | PASS |
| 3 | Selection continues same journey | PASS |
| 4 | Diagnostic retains service identity | PASS |
| 5 | Ticket continuity | PASS |
| 6 | Follow-up without reset | PASS |
| 7 | Existing ticket reused | PASS |
| 8 | Foreign DENY | PASS |
| 9 | Ambiguous NEEDS_INPUT | PASS |
| 10 | Note guarded / prod inactive | PASS |
| 11 | CASI | PASS |
| 12 | Runtime/Legacy XOR | PASS |
| 13 | Relevant regressions | PASS |
| 14 | No production change | PASS |
| 15 | No BSS effect | PASS |
| 16 | 2.5 / 2.6 intact | PASS |

```text
2.7D Exit Gate: PASS
Production touched: NO
Configuration changed: NO
Production ACTIONS changed: NO
Tickets created: 0
Tickets modified: 0
```
