# EKO 2.6H — Agentic Ops Capability Selection & Build Discovery

**Status:** DISCOVERY COMPLETE  
**Date:** 2026-09-23  
**Mode:** READ ONLY — code changes: **NONE**  
**Primary evidence:** live registries (`eko_action_runtime`, `eko_capability_contract`, `eko_action_coverage`, `config.ACTION_RUNTIME_ACTIONS`, `eko_proactive_contract`, portal APIs)  

---

## 1. Status

```text
DISCOVERY COMPLETE
```

---

## 2. Current Architecture

```text
LLM → interpretation / proposal (content only)
  → Policy
  → Conversation Motor
  → Runtime (ActionSpec allowlist)
  → adapter / reader / effect
  → authoritative source
  → deterministic result
  → renderer
```

**CASI:** `LLM content != authority`. TrustedContext rebuilt by backend.  
**2.5 Conversational Layer:** CLOSED / FROZEN (`selected_service_ref`, domain_stack, handoff).  
**Gates:** `ACTION_RUNTIME_ENABLED` (default false) ∧ membership in `ACTION_RUNTIME_ACTIONS`.  
**Runtime XOR Legacy:** `eko_action_bridge.action_runtime_covers` — never Runtime+Legacy same side-effect when gate covers.

Registered ActionSpecs (**16**):  
`close_conversation`, `create_ticket`, `escalate_human`, `installation_status`, `open_OV`, `request_account_selection`, `run_diagnostic_bcm`, `run_diagnostic_pppoe`, `run_diagnostic_uisp`, `send_message`, `service_list`, `show_balance`, `show_invoice`, `show_ticket`, `ticket_customer_note`, `update_ticket`.

Default `ACTION_RUNTIME_ACTIONS` (**12**): includes reads/diag/OV/`ticket_customer_note`.  
**Excluded from default:** `create_ticket`, `update_ticket`, `escalate_human`, `close_conversation`.

Proactive events enabled:  
`outage.started|material_update|resolved`, `ticket.created|updated|closed|sla_breached`.

---

## 3. Capability Inventory

| Capability | Domain | READ/EFFECT | Authority | Reader/Adapter | Ownership | Policy | Runtime | Confirmation | Idempotency | Mobile | Classification |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Identity / TrustedContext | Identity | TRUST | Backend rebuild | Runtime | Trusted | — | — | — | — | session | ALREADY DONE |
| Multi-account selection | Identity | READ/STATE | Catalog + STATE | `eko_service_selection` | CN match | yes | `request_account_selection` | no | SAFE | portal services | ALREADY DONE |
| show_balance | Billing | READ | BillTrack `api_person` | facts / BillTrack | CN/DNI | yes | EXECUTED_BY_RUNTIME | no | SAFE | summary | ALREADY DONE |
| show_invoice | Billing | READ | BillTrack `api_invoice` FC | `eko_invoice_reader` | CN | yes | EXECUTED_BY_RUNTIME | no | SAFE | limited | ALREADY DONE |
| Invoice due_date / PDF / lines | Billing | READ | — | none | — | journey honest | — | — | — | — | UNAVAILABLE |
| Payment history | Billing | READ | — | none | — | honest unavailable | — | — | — | — | UNAVAILABLE |
| Payment execute | Billing | EFFECT | OV/Fiserv external | `open_OV` NAV only | — | allowlist URL | NAV | — | UNKNOWN | deep link | EXTERNAL DEPENDENCY |
| service_list | Services | READ | BillTrack/portal inventory | `evaluar_servicios_portal` | CN | yes | EXECUTED_BY_RUNTIME | no | SAFE | `/portal/services` | ALREADY DONE |
| Service add / plan change / cancel | Services | EFFECT | BSS WRITE | none | — | HANDOFF playbooks | none | — | — | OV | EXTERNAL DEPENDENCY |
| run_diagnostic_pppoe | Connectivity | READ | Radius/PPPoE readers | canal_pppoe | selected_ref | yes | EXECUTED_BY_RUNTIME | no | RISK | connectivity | ALREADY DONE |
| run_diagnostic_bcm | Connectivity | READ | BCM | executor + Legacy | selected_ref | yes | PARTIAL | no | RISK | — | READY AFTER SMALL GAP |
| run_diagnostic_uisp | Connectivity | READ | UISP | executor + Legacy | selected_ref | yes | PARTIAL | no | RISK | — | READY AFTER SMALL GAP |
| CPE reboot / config WRITE | Connectivity | EFFECT | — | none | — | — | none | — | — | — | UNAVAILABLE |
| Outage proactive | Proactive | EVENT | NetworkOutage | outages API → push | segment | proactive | 2.3D/E | — | claim | incidente push | ALREADY DONE |
| Connectivity portal READ | Connectivity | READ | estate/readers | `GET /portal/connectivity` | auth | — | — | — | — | Home | ALREADY DONE |
| show_ticket | Tickets | READ | Estate Ticket | Runtime + `ticket_pertenece` | yes | yes | EXECUTED_BY_RUNTIME | no | SAFE | Activity | ALREADY DONE |
| create_ticket | Tickets | EFFECT | Estate WRITE | Runtime/N1 | linea/conv | yes | EXECUTED_BY_RUNTIME | **yes** | PROTECTED | portal POST | READY AFTER SMALL GAP (CSV) |
| update_ticket (evidence) | Tickets | EFFECT | Estate fields | `_append_evidencia` | yes | yes | RUNTIME_EXECUTOR_ONLY | no | PROTECTED | — | READY AFTER SMALL GAP (N1 wire) |
| ticket_customer_note | Tickets | EFFECT | TicketEvent | emit + agent API | defensive | yes | RUNTIME_EXECUTOR_ONLY | no | PROTECTED | updated push | ALREADY DONE (agent); READY AFTER SMALL GAP (N1 dispatch) |
| SLA breach push | Tickets | EVENT | `sla_breached_at` | 2.6A emit | ticket owner | proactive | post-commit | — | claim | sla_breached | ALREADY DONE |
| ticket.created/updated/closed push | Tickets | EVENT | TicketEvent | 2.3G-B | owner | proactive | detector | — | claim | ticket events | ALREADY DONE |
| ticket reopen / resolved | Tickets | EFFECT | — | unsupported | — | — | — | — | — | — | UNAVAILABLE |
| installation_status | Installation | READ | none | honest UNAVAILABLE | — | yes | EXECUTED_BY_RUNTIME | no | SAFE | message | ALREADY DONE as UNAVAILABLE |
| Work order / appointment / ETA | Installation | READ/EFFECT | external | none | — | — | none | — | — | — | EXTERNAL DEPENDENCY / UNAVAILABLE |
| Commercial offers / price / eligibility | Commercial | READ/EFFECT | BSS | NOT_FOUND | — | HANDOFF | none | — | — | — | EXTERNAL DEPENDENCY |
| Managed campaigns | Commercial | EFFECT | CMS | NOT_FOUND | — | — | none | — | — | — | EXTERNAL DEPENDENCY |
| open_OV | Navigation | NAV | allowlisted URLs | Runtime | — | yes | EXECUTED_BY_RUNTIME | no | UNKNOWN | deep link | ALREADY DONE (≠ transaction) |
| escalate_human | Support | EFFECT | conv/ticket | composition | — | yes | RUNTIME_EXECUTOR_ONLY | **yes** | PROTECTED | — | READY AFTER SMALL GAP |
| close_conversation | Support | EFFECT | conv + CSAT | Legacy | — | yes | RUNTIME_EXECUTOR_ONLY | **yes** | PROTECTED | — | READY AFTER SMALL GAP |
| send_message | Presentation | READ-ish | — | N1 presentation | — | — | RUNTIME_EXECUTOR_ONLY | no | SAFE | chat | ALREADY DONE |
| Billing/service lifecycle proactive | Proactive | EVENT | — | none | — | — | none | — | — | — | UNAVAILABLE / EXTERNAL |

---

## 4. Authority Inventory

| System | Mode | Used for |
|---|---|---|
| TrustedContext / ConversationState | TRUST / STATE | Identity, confirmation, `selected_service_ref`, handoff |
| BillTrack `api_person` | READ | Balance |
| BillTrack `api_invoice` | READ | Invoice **headers only** (no due/PDF/lines) |
| BillTrack `api_service` / portal_services | READ | Service inventory |
| Estate Ticket / TicketEvent | READ/WRITE | Tickets, customer notes, SLA field, timeline |
| SLA engine | WRITE field | `sla_breached_at` (deterministic) |
| NetworkOutage | AUTHORITATIVE EVENT | Outage proactive |
| Radius / BCM / UISP readers | TECH READ | Diagnostics |
| Expo / PortalDevice | DELIVERY | Push (not business SoT) |
| OV public URLs | NAV | Handoff — **not** payment/commerce authority |
| BSS commercial WRITE / pricebook / Fiserv ledger / work-order | — | **NOT IN WORKSPACE** |

**Rejected as authority:** KB/RAG, LLM text, free-text heuristics, undocumented derived totals.

---

## 5. READY NOW

Capabilities fully usable under current architecture (no new SoT):

- Billing READ: balance, invoice headers  
- Services READ: service list + selection STATE  
- Diagnostics: PPPoE Runtime path  
- Tickets READ: show_ticket / portal GET  
- Tickets EFFECT (agent path): customer note, create (when CSV enabled), console updates  
- Proactive: outage + ticket lifecycle + SLA breach  
- Identity: account selection, ownership gates  
- OV navigation (handoff only)  
- Installation honest UNAVAILABLE message  

*(“READY NOW” here = already shippable product surface, not “next build”.)*

---

## 6. READY AFTER SMALL GAP

| Item | Gap (technical only) |
|---|---|
| **N1 dispatch `ticket_customer_note`** | Call-site in canal/journeys; executor+default ACTIONS already exist |
| **BCM / UISP Runtime XOR wire** | Executors exist; hot path still Legacy PARTIAL — avoid double probe |
| **`create_ticket` in default ACTIONS** | N1 already `EXECUTED_BY_RUNTIME`; config/rollout + tests |
| **N1 dispatch `update_ticket`** | Executor evidence-only exists; keep separate from customer note |
| **`escalate_human` / `close_conversation` Runtime wire** | Executors exist; CSAT/composition semantics must be preserved |
| Residual ticket projection hardening | Historical `actualizacion` filter already partial (2.6E/G) |

---

## 7. EXTERNAL DEPENDENCY

- Payment **execute** / Fiserv receipt SoT  
- Commercial pricebook, eligibility, promo, order EFFECT  
- Managed campaign CMS / audience authority  
- Installation work-order / appointment / technician ETA BSS  
- Service lifecycle WRITE (add/change/cancel) in BSS  

---

## 8. UNAVAILABLE

- Invoice due_date / PDF / line items (BillTrack FC insufficient)  
- Payment history reader  
- CPE WRITE (reboot/config)  
- Ticket reopen / `ticket.resolved` domain state  
- Billing/service lifecycle proactive event streams  

---

## 9. ALREADY DONE

Closed phases relevant to Agentic Ops:

| Phase | Outcome |
|---|---|
| CASI / Action Runtime core | Closed |
| Billing 2.1 | CLOSED |
| SM 2.2A/B/C | Implemented |
| 2.2D Installation | Honest UNAVAILABLE |
| 2.2E–I Commercial | EXTERNAL / HANDOFF |
| 2.3 Proactive | Outage + ticket push |
| 2.5 Continuity | FROZEN |
| 2.6A SLA push | PASS |
| 2.6E/G Customer note | PASS (+ hardening) |
| 2.6F Readiness | PASS WITH FINDINGS (smoke deferred) |

---

## 10. Top Technical Readiness Candidates

Maximum **5** (technical readiness only — not product ranking):

| ID | Candidate |
|---|---|
| A | N1 wire for `ticket_customer_note` |
| B | BCM/UISP diagnostic Runtime XOR completion |
| C | Enable `create_ticket` on default Runtime ACTIONS (config gate) |
| D | N1 wire for `update_ticket` (evidence-only) |
| E | Runtime wire for `close_conversation` / `escalate_human` (preserve CSAT/composition) |

---

## 11. Candidate Detail

### Candidate A — N1 `ticket_customer_note` dispatch

- **Why technically possible:** Executor + emit + ownership + default ACTIONS + agent path + tests 2.6E/G exist.  
- **Authority:** TicketEvent / Estate.  
- **Missing:** N1 call-site (`canal_abonado` / journey) when `action_runtime_covers`.  
- **Surface:** Small (dispatch + regression).  
- **Risks:** Confirmation UX; self-note no-push already handled.  
- **Dependencies:** None external. `ACTION_RUNTIME_ENABLED` still required in env.

### Candidate B — BCM / UISP Runtime XOR

- **Why:** Executors registered; already in default ACTIONS; coverage PARTIAL.  
- **Authority:** Existing tech readers.  
- **Missing:** Replace Legacy post-PPPoE path with XOR dispatch; no double probe.  
- **Surface:** Medium (canal_pppoe call sites + tests).  
- **Risks:** Diagnostic semantics / probe duplication.  
- **Dependencies:** None external.

### Candidate C — `create_ticket` default ACTIONS

- **Why:** Already `EXECUTED_BY_RUNTIME` when listed.  
- **Authority:** Estate create.  
- **Missing:** Config default membership + rollout tests; confirmation already required.  
- **Surface:** Config + tests (intentional product enablement).  
- **Risks:** Broader mutate surface when ENABLED=true.  
- **Dependencies:** None external.

### Candidate D — N1 `update_ticket` wire

- **Why:** Executor evidence-only exists.  
- **Authority:** Ticket.evidencia.  
- **Missing:** Dispatch; keep ≠ customer note.  
- **Surface:** Small–medium.  
- **Risks:** Confusing UX if users expect visible notes.  
- **Dependencies:** None.

### Candidate E — close / escalate Runtime wire

- **Why:** Executors + confirmation flags exist.  
- **Authority:** Conversation / ticket composition.  
- **Missing:** Preserve CSAT + escalate→create composition; N1 XOR.  
- **Surface:** Medium–high (lifecycle).  
- **Risks:** Double close / CSAT regression.  
- **Dependencies:** None external, but high regression risk.

---

## 12. CASI Audit

| Check | Result |
|---|---|
| Proposal sanitized (`visible_cliente`, identity, etc.) | PASS (code) |
| Effects only via Policy → Runtime | PASS |
| No LLM TicketEvent / push / ownership | PASS |
| 2.5 SoT frozen | PASS (not modified this discovery) |

**CASI: PASS** for any candidate that reuses existing Runtime path.  
**READY EFFECT** requiring CASI bypass → **none found** that would be classified READY.

---

## 13. Runtime XOR Audit

| Action | XOR status |
|---|---|
| Wired Runtime actions | PASS when `covers()` — Legacy else branch |
| BCM / UISP | **PARTIAL** — executor + Legacy hot path (gap for Candidate B) |
| `ticket_customer_note` | Executor only — no N1 dual path yet (safe) |
| `update_ticket` / close / escalate | Legacy N1; executor unused in hot path |

---

## 14. Confirmation / Idempotency Audit

| Action | Confirmation | Idempotency |
|---|---|---|
| create_ticket | REQUIRED trusted | PROTECTED (`conv.ticket_id`) |
| escalate_human | REQUIRED | PROTECTED (composition) |
| close_conversation | REQUIRED | PROTECTED |
| ticket_customer_note | NOT_REQUIRED | PROTECTED (detalle hash) |
| update_ticket | NOT_REQUIRED | PROTECTED |
| Diagnostics | NOT_REQUIRED | RISK (explicit allow) |
| Reads / OV | NOT_REQUIRED | SAFE / UNKNOWN (OV links) |

EFFECT READY requires confirmation+idempotency where mutating customer-visible or irreversible — create/close/escalate already modeled; customer note uses hash idempotency.

---

## 15. Mobile Readiness

| Surface | Status |
|---|---|
| Ticket push `created/updated/closed/sla_breached` | Supported |
| Outage push | Supported |
| Portal tickets / connectivity / services / OV links | APIs exist |
| New screens for candidates A–E | **Not required** for A/B/C/D |
| Payment/commercial UI | External / OV handoff only |

Candidates A–D: **reuse existing mobile**. Candidate E: no new mobile required.

---

## 16. Known Findings (do not fix here)

| ID | Note |
|---|---|
| 2.6F Event→push window | DEFERRED |
| Smoke productive | NOT AVAILABLE |
| Activity device | NOT VERIFIED |
| `test_4b_explicit_diagnostic_…` | PRE-EXISTING UNRELATED FAILURE |
| Invoice due/PDF | UNAVAILABLE |
| Commercial EFFECT | EXTERNAL |
| Installation SoT | UNAVAILABLE |

---

## 17. Proposed Next Build

**Technical readiness candidate** (least new technical dependency):

```text
Candidate A — N1 dispatch wiring for ticket_customer_note
```

Rationale (technical only): authority, emit helper, ownership defense, default ACTIONS membership, agent path, proactive `ticket.updated`, mobile contract, and tests already exist. Remaining work is primarily **call-site XOR dispatch** under existing Policy/Runtime — no new SoT, migration, mobile event, or BSS.

This is **not** a product “best feature” recommendation.

---

## 18. Final Gate

```text
EKO 2.6H — DISCOVERY COMPLETE
```

---

## Audit meta

| Item | Value |
|---|---|
| Code / tests / mobile / DB changes | **NONE** |
| Docs created | this file |
| Live verification | `list_registered_actions`, coverage_matrix, `ACTION_RUNTIME_ACTIONS`, `SUPPORTED_PROACTIVE_EVENTS` via Python one-liner |
