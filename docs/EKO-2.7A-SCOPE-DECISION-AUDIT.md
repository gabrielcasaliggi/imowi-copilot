# EKO 2.7A — Scope Decision Audit

**Date:** 2026-09-23  
**Mode:** READ ONLY — scope decision input only  
**Baseline docs:** `EKO-2.6T-FINAL-AGENTIC-OPS-COVERAGE.md`, `EKO-2.7-PRODUCT-COVERAGE-DISCOVERY.md`, 2.3H/2.3F, 2.6I, 2.6P  
**Not done:** implementation, config, Runtime/ACTIONS changes, production, ranking/choice of axis  

---

## Baseline

```text
2.6 Agentic Ops = CLOSED
2.7 Discovery = COMPLETED
```

Frozen / do not reopen in 2.7A:

* 2.5 Conversational Continuity  
* 2.6 Agentic Ops architecture (CASI, Motor, Policy, ActionProposal, Runtime model)  
* Production `create_ticket` path (2.6P) as working mutation Runtime  

Production Runtime mutation scope (historical):

```text
ACTION_RUNTIME_ENABLED=true
ACTION_RUNTIME_ACTIONS=create_ticket
```

---

## Decision Criteria

Comparable gates used for each option (no preference language):

1. **Data authority (SoT)** exists and is accessible from this repo’s integrations  
2. **Dependencies** identified (INTERNAL / EXTERNAL / MIXED / UNKNOWN)  
3. **Architecture** already present to extend without redesigning CASI/Runtime  
4. **Scope** can be bounded with hard exclusions  
5. **Exit criteria** can be stated without inventing systems  

Gate labels:

* `READY_TO_SCOPE`  
* `BLOCKED_BY_DECISION`  
* `BLOCKED_BY_EXTERNAL_DEPENDENCY`  

---

## Option A — Proactive ISP

### Initiative inventory

| Initiative | SoT | Event | Detection | Decision | Notify | Channel | Dedup/Cooldown | Ownership | Prod readiness | Ext dep | Class |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Outage started/material/resolved | NETWORK (NetworkOutage CRUD) | outage.* | YES | 2.3C | Expo | App | YES 2.3E | NAS→abonado | **READY** (2.3H) | Low | **READY** |
| ticket.created | TICKETING (TicketEvent creacion) | ticket.created | YES | allowlist visible | Expo | App | claim Event.id | portal ownership | **READY** | — | **READY** |
| ticket.updated | TICKETING (nota/actualizacion) | ticket.updated | YES | visible+allowlist | Expo | App | YES | portal | **READY** | — | **READY** |
| ticket.closed | TICKETING (actualizacion+Cerrado) | ticket.closed | YES | YES | Expo | App | YES | portal | **READY** | — | **READY** |
| SLA breach | TICKETING / SLA fields | (2.6A path) | YES in code | policy | Expo | App | YES | ticket | **READY**/tested | — | **READY** / **SMALL_GAP** ops enable |
| Billing due reminder | — | — | NO | — | — | — | — | — | — | BillTrack due absent (2.3F) | **UNAVAILABLE** |
| Payment reminder / completed | — | — | NO | — | — | — | — | — | — | OV/PSP / unused tables | **UNAVAILABLE** / **DEPENDENCY** |
| Service degradation proactive | NETWORK probes | — | No event stream | — | — | — | — | — | — | Would invent from STATE | **UNAVAILABLE** |
| Connectivity lost/restored proactive | SESSION STATE | — | STATE_ONLY | — | — | — | — | — | — | No transition SoT (2.3H) | **UNAVAILABLE** |
| Proactive recommendations (LLM) | — | — | Forbidden as authority | — | — | — | — | — | — | — | **UNAVAILABLE** (CASI) |

### Scope-shaped option (if chosen later)

**In:** deepen/harden already-READY outage+ticket+SLA proactive; documentation/ops smoke; optional UX of Activity/Home for those events.  
**Not in:** inventing billing/connectivity proactive without SoT.

### READY_TO_SCOPE

```text
READY_TO_SCOPE = YES
```

for a **narrow** proactive milestone on existing SoTs only.  

Billing/payment/connectivity-loss proactive:

```text
BLOCKED_BY_EXTERNAL_DEPENDENCY / UNAVAILABLE SoT
```

---

## Option B — Billing Depth

| Capability | SoT | Current API | UI | N1 | Auth | Ext | Implementability | Class |
|---|---|---|---|---|---|---|---|---|
| Balance/deuda | BILLTRACK | show_balance / portal summary | App BalanceCard | YES | Portal JWT / WA trust | BillTrack RO | Exists | **READY** |
| Invoice header | BILLTRACK api_invoice | show_invoice | Partial | YES | CN | BillTrack | Exists limited | **READY** |
| Due date | — | due_date=None (2.3F) | No | No | — | BillTrack schema gap | Cannot invent | **UNAVAILABLE** |
| Full invoice / lines | BILLTRACK limits | Partial FC | No | Limited | CN | BillTrack | Needs proven columns | **EXTERNAL_DEPENDENCY** / **UNAVAILABLE** until schema |
| PDF / slip | OV | open_OV | Links | open_OV | OV by celular | OV | Handoff only | **EXTERNAL_DEPENDENCY** |
| Payment history | UNKNOWN / unused | No reader | No | No | — | BillTrack?/OV | Probe ≠ integration | **UNAVAILABLE** |
| Payment status / execution | OV/PSP | No | OV | Handoff | OV | OV | Forbidden WRITE BSS | **EXTERNAL_DEPENDENCY** |
| Comprobante | OV | No | OV | Handoff | OV | OV | Handoff | **EXTERNAL_DEPENDENCY** |
| OV navigation | OV | open_OV allowlist | App OV links | YES | Trusted CN/celular | OV | Exists | **READY** |

### Scope-shaped option

**In:** improve presentation of existing BillTrack READ + clearer OV handoff copy/UX; honest unavailable for due/PDF/history.  
**Not in:** payment WRITE; scraping OV; inventing due_date.

### READY_TO_SCOPE

```text
READY_TO_SCOPE = YES
```

for **READ depth + OV handoff UX** only.  

Due-date / payment lifecycle / PDF-in-Eko:

```text
BLOCKED_BY_EXTERNAL_DEPENDENCY
```

---

## Option C — Incident / Customer Experience

### Flow “sin internet” — closed vs improvement

| Step | State |
|---|---|
| Account identity | READY |
| Service selection | READY (2.5 SoT) |
| Outage | READY + proactive |
| Status / diagnostic | READY (fixed Internet); PARTIAL BCM/UISP |
| Result / recommendation | READY |
| create_ticket | READY + **prod** 2.6P |
| escalate composition | COMPOSITION_READY |
| ticket_customer_note | **IMPLEMENTED** (2.6I) Runtime+Event+proactive+tests; **prod ACTIONS CSV excludes note** |
| show_ticket / follow-up | READY / PARTIAL timeline UX |
| Push ticket events | READY (2.3G) |
| Customer close/resolve | OUT_OF_SCOPE |

### `ticket_customer_note` (critical)

| Aspect | Evidence |
|---|---|
| Implementation | YES — executor + emit + N1 wire |
| Tests | PASS 2.6E/2.6I |
| Runtime | YES when covers |
| Event | `nota` visible Sí |
| Proactive | ticket.updated path |
| Default ACTIONS (code) | includes note |
| Production effective ACTIONS | **`create_ticket` only** (2.6P) → note **not covered** until CSV widened |

Activation of note in prod = **ops config decision**, not greenfield build. Still requires change control / smoke (not done in this audit).

### Scope-shaped option

**In:** guided multi-service “sin internet” narrative; optional prod enable note in ACTIONS; ticket Activity UX; no update_ticket/close.  
**Not in:** admin mutation; escalate Action activation.

### READY_TO_SCOPE

```text
READY_TO_SCOPE = YES
```

Primarily **INTERNAL** (+ **BLOCKED_BY_DECISION** if product must decide whether to widen prod ACTIONS to include `ticket_customer_note`).

---

## Option D — Mobile / Channel Experience

| Area | State | Gap type |
|---|---|---|
| Home / Eko chat / billing / services / connectivity / tickets / OV / account | READY | — |
| Push | READY† | FUNCTIONAL if FCM missing on preview; CHANNEL |
| Voice | READY† | FUNCTIONAL/CHANNEL (STT + build flags) |
| Empty/error/loading | PARTIAL | VISUAL POLISH / PRODUCT GAP mild |
| Portal parity | PARTIAL | CHANNEL PARITY (often INTENTIONAL) |
| Store / AAB path | Documented | OPERATIONAL / release |

† Preview APK without `google-services.json` disables push/mic (`mobile/README.md`).

### Scope-shaped option

**In:** production FCM/voice builds; QA matrix; release readiness; non-blocker polish.  
**Not in:** new backend Actions; BSS.

### READY_TO_SCOPE

```text
READY_TO_SCOPE = YES
```

**MIXED** INTERNAL app + EXTERNAL Expo/Google/Apple accounts.  
Push field QA may be **BLOCKED_BY_EXTERNAL_DEPENDENCY** until Firebase/store configured (ops).

---

## Data Authority Matrix

| Initiative / data | SoT class |
|---|---|
| Outage | NETWORK |
| Ticket events | TICKETING |
| SLA | TICKETING |
| Balance / invoice header | BILLTRACK |
| Due date / payment lifecycle | UNKNOWN / UNAVAILABLE in Eko readers |
| Pay / PDF | OV |
| Commercial catalog WRITE | BSS/CRM (absent) |
| selected_service_ref | EKO_STATE |
| Sensa platform actions | SENSA (external) |
| SIP ops | ASTERISK (external) |
| Connectivity session snapshot | NETWORK / Radius (STATE, not proactive transition SoT) |

---

## External Dependencies

| System | Appears in |
|---|---|
| BillTrack | Billing depth; blocks due/payment detectors |
| OV | Pay/PDF/comprobante handoff |
| BSS/CRM | Commercial EFFECTS (excluded) |
| Expo / FCM / Play | Mobile release & push |
| Whisper | Voice quality |
| Radius/BCM/UISP | Connectivity (already integrated READ) |
| Sensa / Asterisk | Explicit hard exclusions for action backends |

---

## Production Risk

| Option | Risk | Why |
|---|---|---|
| A Proactive (outage/ticket only) | **MEDIUM** | Mass notify; mitigated by existing dedup/claim |
| A Proactive billing invent | **HIGH** / **EXTERNAL** | Wrong SoT → customer harm |
| B Billing READ/OV UX | **LOW** | READ + handoff |
| B Payment WRITE | **HIGH** / **EXTERNAL** | Excluded |
| C Incident CX / note CSV | **MEDIUM** | Config flip + customer Events/push |
| D Mobile release | **MEDIUM** | Channel; store/FCM external |

---

## Implementation Class

| Option | Class | Basis |
|---|---|---|
| A narrow (existing SoTs) | **SMALL**–**MEDIUM** | Stack exists 2.3 |
| A with billing proactive | **MULTI-SYSTEM** | Missing SoT |
| B READ/OV UX | **SMALL**–**MEDIUM** | Readers exist |
| B due/PDF/history | **MULTI-SYSTEM** | Schema/OV |
| C CX narrative + note enable | **SMALL**–**MEDIUM** | 2.6I done; UX/config |
| D Mobile FCM/store | **MEDIUM** / **MULTI-SYSTEM** | EAS + Google |

---

## Scope Candidates

### OPTION A — PROACTIVE ISP

**Scope:** Harden/operate outage + ticket (+ SLA) proactive pipelines already READY; Activity/Home consistency; tests/smoke.  
**Dependencies:** Estate, Expo, existing detectors.  
**Exclusions:** billing due/payment proactive; connectivity-lost invent; LLM recommendations as authority.

### OPTION B — BILLING DEPTH

**Scope:** Maximize BillTrack READ clarity; due/PDF/history as honest unavailable or OV handoff; N1/App copy.  
**Dependencies:** BillTrack RO; OV links.  
**Exclusions:** payment execution; BSS WRITE; OV scraping.

### OPTION C — INCIDENT / CX

**Scope:** End-to-end “sin internet” product narrative; multi-service selection UX; ticket follow-up; optional ops decision to add `ticket_customer_note` to prod ACTIONS; Activity.  
**Dependencies:** Mostly INTERNAL; config decision for ACTIONS.  
**Exclusions:** update_ticket; close/resolve/reassign; escalate_human ACTIONS activation.

### OPTION D — MOBILE

**Scope:** Production push/voice builds; QA matrix; store packaging; parity only where FUNCTIONAL.  
**Dependencies:** Firebase/EAS/store.  
**Exclusions:** New Agentic Actions; visual-only redesign as sole milestone content.

---

## Hard Exclusions (all options)

* Payment execution / PSP WRITE  
* BSS commercial EFFECTS (alta/baja/upgrade)  
* Installation orders / agenda EFFECT  
* Admin ticket mutation; close/resolved/reassign as customer Actions  
* Activating `update_ticket` Runtime  
* Activating `escalate_human` in ACTIONS without dedicated phase  
* Sensa platform account WRITE  
* VoIP/Asterisk operational control  
* Reopening 2.5 continuity architecture  
* Inventing proactive events without SoT  

---

## Exit Criteria

### A — Proactive
SoTs only from estate outage/ticket(/SLA); detectors/policy/dedup/cooldown unchanged or extended with tests; push evidence; no billing invent; production smoke of notify path if changed.

### B — Billing
Documented BillTrack fields used; N1+UI expose only proven READ; OV handoff for pay/PDF; honest unavailable where no SoT; no payment WRITE; tests on readers/handoff.

### C — Incident/CX
Documented sin-internet path; multi-service selection intact; create/show/note behavior verified; if ACTIONS widened → boot log + smoke note; no admin Actions; CASI intact.

### D — Mobile
Push/voice on production profile verified; QA checklist; release artifact; functional parity gaps listed; polish not required for exit unless scoped.

---

## Decision Gate

| Option | Gate | Why |
|---|---|---|
| A Proactive (narrow) | **READY_TO_SCOPE = YES** | SoT+stack exist |
| A + billing proactive | **BLOCKED_BY_EXTERNAL_DEPENDENCY** | no due_date/payment SoT in Eko |
| B Billing READ/OV | **READY_TO_SCOPE = YES** | BillTrack+OV known |
| B due/PDF/history in-Eko | **BLOCKED_BY_EXTERNAL_DEPENDENCY** | schema/OV |
| C Incident/CX | **READY_TO_SCOPE = YES** | mostly internal; note enable = **BLOCKED_BY_DECISION** (ops/product) until CSV policy chosen |
| D Mobile | **READY_TO_SCOPE = YES** | app exists; FCM/store may **BLOCKED_BY_EXTERNAL_DEPENDENCY** for field push |

---

## Final Decision Input

Product/ops must choose **one primary axis** for 2.7 among A–D using:

* whether the cooperative prioritizes **notifications already possible**, **billing honesty+OV**, **incident journey/note enablement**, or **mobile release quality**;  
* acceptance that billing due/payment proactive and payment WRITE remain **out** until external SoT exists;  
* acceptance that widening prod `ACTION_RUNTIME_ACTIONS` is a **separate controlled ops act**, not implied by picking C.

This audit does **not** select the axis.

```text
Production touched: NO
Configuration changed: NO
Runtime activated: NO
ACTION_RUNTIME_ACTIONS changed: NO
Tickets created: 0
Tickets modified: 0
Database changed: NO
Implementation: NO
```
