# EKO 2.6T — Final Agentic Ops Coverage

**Date:** 2026-09-23  
**Mode:** READ ONLY — closure audit only  
**Sources:** code (`config`, coverage, runtime), docs 2.6A–2.6S, harness 2.6N-C, production smoke 2.6P (historical)  
**Not done:** code/config/DB/prod mutations; no new tickets; no ACTIONS changes  

---

## Final Status

```text
CLOSED
```

2.6 Agentic Ops cierra un **conjunto coherente** de capacidades customer-facing seguras. No requiere Agentic completo de toda mutación administrativa ni de efectos BSS/CRM.

---

## Closure Criteria

| # | Criterion | Met? |
|---|---|---|
| 1 | Customer-facing selected set closed | **YES** |
| 2 | `create_ticket` production evidence | **YES** — 2.6P / IBOT-1066 |
| 3 | `ticket_customer_note` Runtime + Event + proactive | **YES** — 2.6E/I (code+tests); prod CSV currently excludes it (rollout choice) |
| 4 | Reads/diagnostics clear contracts | **YES** |
| 5 | CASI PASS | **YES** |
| 6 | No security/authority blocker | **YES** |
| 7 | Non-closed caps explicitly classified | **YES** |
| 8 | No need to activate `update_ticket` | **YES** |
| 9 | No need to activate `escalate_human` Action | **YES** — composition via create |
| 10 | No external dependency blocking closed set | **YES** |

---

## Customer-Facing Capabilities

### Mutations (closed)

| Capability | Evidence |
|---|---|
| **create_ticket** | AGENTIC_READY (2.6K) + prod smoke 2.6P: ENABLED + ACTIONS=`create_ticket`; confirm; `path=runtime`; Ticket **IBOT-1066**; Event `creacion`; XOR helper PASS |
| **ticket_customer_note** | 2.6E/I: N1 wire; Policy; ownership; Event `nota` Sí; self-note no push; proactive 2.3G-B; CASI PASS |

### Reads / selection / diagnostics (closed with stated limits)

| Capability | Evidence |
|---|---|
| **show_balance** | EXECUTED_BY_RUNTIME; Billing 2.1; CASI |
| **show_invoice** | EXECUTED_BY_RUNTIME |
| **service_list** | EXECUTED_BY_RUNTIME |
| **request_account_selection** / service selection | EXECUTED_BY_RUNTIME; 2.2B/2.5D SoT `selected_service_ref` |
| **show_ticket** | EXECUTED_BY_RUNTIME |
| **run_diagnostic_pppoe** | EXECUTED_BY_RUNTIME; selected_ref; known test fixture/legacy noise |
| **run_diagnostic_bcm** | PARTIAL coverage (executor + Legacy hot path) — usable; not a 2.6 blocker |
| **run_diagnostic_uisp** | PARTIAL — same |
| **open_OV** | EXECUTED_BY_RUNTIME; allowlist destinations |
| **send_message** | executor / presentation |

READ actions: **no** TicketEvent/proactive required by contract.

---

## Composition Capabilities

| Capability | Final class | Note |
|---|---|---|
| **escalate_human** | **COMPOSITION_READY** | N1 escape → `create_ticket` Runtime (2.6P). ActionSpec executor = espera_agente only; **do not** add to ACTIONS. 2.6S |

---

## Out of Scope / Dependencies

| Item | Class | Why |
|---|---|---|
| **update_ticket** | OUT_OF_SCOPE / PARTIAL — **no activar** | 2.6R: no N1 Runtime wire; XOR FAIL; evidence-only; no Event; ticket_id param |
| **close_ticket** | OUT_OF_SCOPE | No ActionSpec; helpdesk `repo.update_ticket` |
| **resolved** | UNAVAILABLE / OUT_OF_SCOPE | Not a supported N1 Action contract |
| **reassign_ticket** | OUT_OF_SCOPE | Admin `reasignacion` Event |
| Administrative ticket mutation | OUT_OF_SCOPE | `PUT /tickets`, agents pipeline |
| **close_conversation** | OUT_OF_SCOPE (N1 Lifecycle) | RUNTIME_EXECUTOR_ONLY; CSAT complexity; not activated |
| Payment execution | DEPENDENCY | OV / externo |
| Commercial effects | DEPENDENCY | BSS/CRM (2.4*) |
| Installation order/effect | DEPENDENCY | No BSS authority |
| **installation_status** | **HONEST_UNAVAILABLE** | Runtime executor returns honest unavailable — not a failure |

---

## Runtime Scope

### Code default ACTIONS (when env CSV empty)

13 names including reads, diagnostics, OV, `ticket_customer_note`, `create_ticket`.  
**Excluded by design:** `update_ticket`, `escalate_human`, `close_conversation`.

### Production effective (2.6P — historical, not re-run)

```text
ACTION_RUNTIME_ENABLED=true
ACTION_RUNTIME_ACTIONS=create_ticket
```

Boot log:

```text
action_runtime.enabled=true action_runtime.actions=create_ticket
```

**Production mutation Runtime = only `create_ticket`.**  
This audit **does not** change that. Expanding CSV (e.g. add `ticket_customer_note`) is a future ops decision, not a 2.6 code gap.

---

## CASI Final

```text
CASI FINAL = PASS
```

Pattern maintained for closed paths:

* LLM interprets / may propose  
* Policy authorizes  
* Conversation Motor / TrustedContext hold state  
* Runtime executes when covered  
* Adapters/writers mutate  
* Events/proactive deterministic where contracted  

`LLM content != authority` enforced via sanitize + TrustedContext + ownership (create, note, reads).

---

## Production Evidence

**2.6P (historical — not re-executed):**

| Signal | Value |
|---|---|
| Config | `enabled=true`, `actions=create_ticket` |
| Confirm | `needs_confirmation` / `escape_agente` / `path=runtime` |
| Success | `create_ticket_confirmed` / `path=runtime` / `success` |
| Conversation | `ac08e815-a4be-4c6b-939d-d749155b3013` |
| Ticket | **IBOT-1066** |
| XOR | Runtime=1 success after confirm; Legacy helper=0 |
| Isolation | only create covered |

Identity: DNI designated in `docs/EKO-SMOKE-TEST-IDENTITY.md`.

---

## Known Limitations

| Limitation | BLOCKER? |
|---|---|
| 9 N1 Legacy direct `_crear_ticket_n2` outside XOR helper (2.6M) | **NO** — residual; smoke measured XOR path |
| `canal_diagnostico_ia` escalate → Legacy create | **NO** — OUT_OF_SCOPE for 2.6 close; document |
| BCM/UISP coverage PARTIAL (Legacy hot path) | **NO** |
| PPPoE tests historically noisy (fixtures fixed 99d090a) | **NO** |
| No remote staging (2.6N) | **NO** — harness + prod smoke used |
| Legacy create observability weaker than Runtime | **NO** — smoke observability SUFFICIENT (2.6P-READINESS C) |
| Prod ACTIONS excludes note/reads Runtime | **NO** — intentional isolation; note remains CLOSED in product code |
| `escalate_human` Action confirm-resume incomplete if ACTIONS listed | **NO** — must not activate Action |
| `update_ticket` ticket_id from LLM params | **NO** — not activating |

---

## Final Capability Matrix

| Capability | Status | Customer-facing | Runtime | CASI | XOR | Production Evidence | Final Classification |
|---|---|---|---|---|---|---|---|
| show_balance | EXECUTED_BY_RUNTIME | YES | YES | PASS | path swap | code/tests | **CLOSED** |
| show_invoice | EXECUTED_BY_RUNTIME | YES | YES | PASS | path swap | code/tests | **CLOSED** |
| service_list | EXECUTED_BY_RUNTIME | YES | YES | PASS | path swap | code/tests | **CLOSED** |
| request_account_selection | EXECUTED_BY_RUNTIME | YES | YES | PASS | YES | code/tests | **CLOSED** |
| show_ticket | EXECUTED_BY_RUNTIME | YES | YES | PASS | path swap | code/tests | **CLOSED** |
| run_diagnostic_pppoe | EXECUTED_BY_RUNTIME | YES | YES | PASS | selected_ref | code/tests | **CLOSED** |
| run_diagnostic_bcm | PARTIAL | YES | PARTIAL | PASS | PARTIAL | code/tests | **CLOSED** + **KNOWN_LIMITATION** |
| run_diagnostic_uisp | PARTIAL | YES | PARTIAL | PASS | PARTIAL | code/tests | **CLOSED** + **KNOWN_LIMITATION** |
| installation_status | EXECUTED_BY_RUNTIME | YES | YES (honest) | PASS | n/a | code | **HONEST_UNAVAILABLE** |
| open_OV | EXECUTED_BY_RUNTIME | YES | YES | PASS | allowlist | code/tests | **CLOSED** |
| create_ticket | EXECUTED_BY_RUNTIME | YES | YES | PASS | PASS (helper) | **2.6P IBOT-1066** | **CLOSED** |
| ticket_customer_note | EXECUTED_BY_RUNTIME | YES | YES | PASS | N1 XOR | code/tests 2.6I | **CLOSED** |
| escalate_human | RUNTIME_EXECUTOR_ONLY | YES (via create) | composition | PASS via create | create PASS | create path 2.6P | **COMPOSITION_READY** |
| update_ticket | RUNTIME_EXECUTOR_ONLY | internal | NO N1 | PARTIAL | FAIL | none | **OUT_OF_SCOPE** |
| close_conversation | RUNTIME_EXECUTOR_ONLY | YES | NO N1 | — | — | none | **OUT_OF_SCOPE** |
| close_ticket / resolved / reassign | no ActionSpec / admin | admin | NO | — | — | helpdesk | **OUT_OF_SCOPE** |
| payments / commercial / install order | external | — | NO | — | — | — | **DEPENDENCY** |
| Legacy direct creates (9) | residual | YES | NO | — | outside helper | — | **KNOWN_LIMITATION** |

---

## 2.6 Closure Statement

**EKO 2.6 — Agentic Ops is CLOSED.**

Closed customer-facing core:

* Self-service reads + selection + diagnostics (with honest/partial limits documented)  
* **create_ticket** Runtime with **production** proof  
* **ticket_customer_note** Agentic path (Event + proactive)  
* **escalate_human** as **composition** onto create_ticket — not a separate ACTIONS activation  

Explicitly **not** required for 2.6 close:

* Activating `update_ticket` or `escalate_human` in ACTIONS  
* Admin close/resolve/reassign as Agentic Actions  
* Payment / commercial / installation BSS effects  

```text
production touched (this audit): NO
configuration changed: NO
tickets created: 0
tickets modified: 0
```

Next milestone: product roadmap beyond 2.6 (ops may later widen ACTIONS CSV intentionally; residual Legacy create hardening is optional post-2.6 work).
