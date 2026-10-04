# EKO 2.7B — PRODUCT DECISION MATRIX

## Status

DECISION_REQUIRED

## Baseline

* 2.6 Agentic Ops: CLOSED
* 2.7 Discovery: COMPLETE
* 2.7A Scope Decision Audit: COMPLETE
* Implementation: NONE

Sources: `docs/EKO-2.7A-SCOPE-DECISION-AUDIT.md`, `docs/EKO-2.7-PRODUCT-COVERAGE-DISCOVERY.md`, `docs/EKO-2.6T-FINAL-AGENTIC-OPS-COVERAGE.md`, 2.3H/2.3F, 2.6I, 2.6P (historical). No new capabilities claimed beyond those audits.

| Criterio | A — Proactive | B — Billing READ+OV | C — Incident/CX | D — Mobile |
| --- | --- | --- | --- | --- |
| Scope | Harden outage + ticket (+ SLA) proactive already READY; Activity/Home consistency; tests/smoke | Maximize BillTrack READ clarity + OV handoff UX; honest unavailable for due/PDF/history | Guided “sin internet” + multi-service UX; ticket follow-up; optional prod ACTIONS include `ticket_customer_note` | Production FCM/voice builds; QA matrix; store packaging; functional parity only |
| Existing capability | 2.3 outage+ticket detectors/policy/push/dedup; SLA 2.6A; Expo | show_balance/show_invoice; open_OV; App BalanceCard/OV links | create_ticket Runtime prod; diagnostics; selection SoT; note 2.6I code+tests; escalate composition | App Home/chat/tickets/billing/services/connectivity; `/portal/audio`; push stack |
| Missing implementation | Ops smoke/docs; optional UI polish for Activity; **not** new billing detectors | UX/copy for limits; N1 honesty for unavailable fields; **not** new BillTrack columns | CX narrative/UX; config decision for ACTIONS CSV; Activity polish | Firebase on prod profile; EAS/store QA; empty/error polish optional |
| SoT | NETWORK outage; TICKETING Events; SLA fields | BILLTRACK balance/invoice header; OV for pay/PDF | EKO_STATE selection; TICKETING create/note/Events | Same APIs as portal; FCM tokens |
| External dependency | NONE for narrow; BLOCKED_EXTERNAL if billing/connectivity-lost invent | BillTrack PARTIAL; OV AVAILABLE for handoff; BLOCKED_EXTERNAL for due/PDF/history/pay WRITE | NONE for UX; BLOCKED_DECISION for note CSV widen | FCM/EAS/store PARTIAL→BLOCKED_EXTERNAL until configured |
| Effects | CUSTOMER_VISIBLE_EFFECT (push already); no new commercial | READ + NAVIGATION/HANDOFF | READ/DIAG + CUSTOMER_VISIBLE_EFFECT (ticket/note/push) | CHANNEL delivery of existing effects |
| Production risk | MEDIUM (mass notify; mitigated by existing claim/dedup) | LOW (READ/handoff) | MEDIUM (if ACTIONS widened → Events/push) | MEDIUM (release/channel) |
| Blast radius | proactive, push, portal Activity, tests; config only if enable flags already exist | portal, mobile billing UI, N1 copy; BillTrack readers unchanged contract | N1 UX, journeys copy, possibly production ACTIONS, push; not Motor/CASI redesign | mobile, EAS, FCM; backend mostly untouched |
| Reuse | 2.3D/E/G/H pipeline; estate Events | Billing 2.1 readers; OV allowlist | 2.6 create/note; 2.5 SoT; 2.3 ticket push | Existing Expo app + portal API |
| Hard exclusions | billing/payment/connectivity-lost proactive without SoT; LLM reco as authority | payment WRITE; OV scrape; invent due_date | update_ticket; close/resolve/reassign; escalate ACTIONS | new Agentic Actions; polish-only as whole milestone |
| Exit criteria | SoT-only notify paths verified; tests; smoke if changed; no invented events | Proven READ only exposed; OV handoff; honest unavailable documented; tests | Documented sin-internet path; multi-service intact; if note CSV → boot log + smoke; CASI intact | Prod push/voice verified; QA checklist; release artifact |

---

## Option A — Proactive ISP Narrow

### 1. Scope concreto
* Operate/harden **outage** started/material/resolved proactive  
* Operate/harden **ticket** created/updated/closed proactive  
* Optional **SLA breach** path already in code (2.6A)  
* Consistency of Home/Activity for those events  
* Tests / ops smoke documentation  

### 2. Qué ya existe
* Detectors, policy, push runtime, dedup/cooldown, ownership (2.3A–H)  
* TicketEvent map + claim (2.3G)  
* Production create → creacion Event path (2.6P)  

### 3. Qué falta
* backend: little/none for narrow harden  
* runtime/motor: none (do not reopen)  
* portal/mobile: optional display consistency  
* push: ops verification  
* UX: Activity/Home polish optional  
* tests/observability: extend if touch detectors  

### 4. Dependencias externas
* Narrow stack: **NONE** / **AVAILABLE** (Expo already)  
* Billing/connectivity-lost proactive: **BLOCKED_EXTERNAL**  

### 5. Data authority
* Outage: NETWORK — READ_ONLY estate CRUD — AUTHORITATIVE  
* Ticket events: TICKETING — READ_ONLY Event stream — AUTHORITATIVE  
* Due/payment: **UNAVAILABLE** → any initiative **BLOCKED**  
* Connectivity lost transition: **UNAVAILABLE** → **BLOCKED**  

### 6. Effects
CUSTOMER_VISIBLE_EFFECT (push). No COMMERCIAL_EFFECT. No payment.

### 7. Production risk
**MEDIUM** — broadcast notify; existing at-most-once claim reduces duplicate risk.

### 8. Blast radius
proactive modules, push, Activity UI, tests. Not Conversation Motor / CASI redesign. Not ACTIONS unless separately decided.

### 9. Reuse
Full 2.3 proactive stack; estate; Expo delivery.

### 10. Hard exclusions
billing due/payment proactive; connectivity-lost invent; LLM recommendations as authority; BSS; payment WRITE.

### 11. Exit criteria
Only SoT-backed events in scope; detectors/policy/dedup verified by tests; documented smoke if behavior changed; zero invented billing events.

---

## Option B — Billing READ + OV

### 1. Scope concreto
* Present **existing** BillTrack balance + invoice header clearly in N1/App  
* Strengthen **OV** navigation for pay/PDF/talon  
* Mark due/PDF/history as **honest unavailable** where no SoT  

### 2. Qué ya existe
* `show_balance`, `show_invoice`, `open_OV`  
* BillTrack RO posture  
* App BalanceCard / OV hooks  

### 3. Qué falta
* backend: none required for new SoT; possible presentation helpers only  
* portal/mobile/N1: copy/UX for limits and OV CTAs  
* tests: reader/handoff regressions  
* No new BillTrack columns without schema proof  

### 4. Dependencias externas
* BillTrack: **PARTIAL** (header yes; due/lines **BLOCKED_EXTERNAL**)  
* OV: **AVAILABLE** for handoff  
* Payment WRITE: **BLOCKED_EXTERNAL**  

### 5. Data authority
* Balance/invoice header: BILLTRACK READ_ONLY  
* Due date: **UNAVAILABLE** → **BLOCKED**  
* PDF/pay: OV — NAVIGATION only  

### 6. Effects
READ + NAVIGATION/HANDOFF. No CUSTOMER_VISIBLE ticket mutation. No COMMERCIAL_EFFECT.

### 7. Production risk
**LOW**

### 8. Blast radius
portal, mobile billing UI, N1 messaging. Not Runtime ACTIONS. Not Motor.

### 9. Reuse
Billing 2.1 + OV allowlist + portal/app cards.

### 10. Hard exclusions
payment WRITE; scrape OV; invent due_date/history; BSS EFFECTS.

### 11. Exit criteria
UI/N1 expose only proven fields; OV handoff documented; unavailable fields explicit; tests green; no payment WRITE.

---

## Option C — Incident / Customer Experience

### 1. Scope concreto
* Product narrative for “sin internet” (selection → outage/diag → ticket → follow-up)  
* Multi-service clarity  
* Ticket Activity / show_ticket UX  
* **Optional:** widen prod `ACTION_RUNTIME_ACTIONS` to include `ticket_customer_note` (ops)  

### 2. Qué ya existe
* Diagnostics + selected_service_ref  
* create_ticket Runtime **in prod**  
* ticket_customer_note full stack in **code** (2.6I)  
* escalate via create composition  
* ticket push pipeline  

### 3. Qué falta
* UX/journey copy and guided flow  
* Decision + controlled config for note in ACTIONS  
* Smoke if note enabled  
* Not: new ActionSpecs for update/close  

### 4. Dependencias externas
* UX work: **NONE**  
* Note enable: **BLOCKED_DECISION** until Product/Ops approves CSV change  
* Probes: AVAILABLE (existing)  

### 5. Data authority
* Selection: EKO_STATE  
* Ticket create/note Events: TICKETING  
* Note in prod: capability AUTHORITATIVE in code; **coverage gate** is config  

### 6. Effects
DIAGNOSTIC READ; CUSTOMER_VISIBLE_EFFECT (create/note/push). No admin COMMERCIAL_EFFECT.

### 7. Production risk
**MEDIUM** if ACTIONS change (more Runtime mutators + push). **LOW–MEDIUM** if UX-only without CSV change.

### 8. Blast radius
N1 journeys/UX, possibly `.env` ACTIONS, push volume, Activity. Must not redesign CASI/Motor.

### 9. Reuse
2.5 SoT, 2.6 create/note, 2.3 ticket proactive.

### 10. Hard exclusions
update_ticket activation; close/resolve/reassign; escalate_human in ACTIONS; payment/BSS.

### 11. Exit criteria
Documented sin-internet path; multi-service selection preserved; if note in ACTIONS → boot `action_runtime.actions` includes note + controlled smoke; CASI unchanged; no admin Actions.

---

## Option D — Mobile / Channel Experience

### 1. Scope concreto
* Production profile with FCM + voice  
* QA checklist (Home, chat, billing, services, connectivity, tickets, push, OV)  
* Store/AAB path as documented  
* Functional parity gaps only (not pure visual redesign)  

### 2. Qué ya existe
* Expo app screens/hooks for all core surfaces  
* Portal API parity for chat/tickets/billing/connectivity  
* Push/voice code paths  

### 3. Qué falta
* Firebase/`google-services` on production builds  
* EAS production QA  
* Optional empty/error polish  
* backend: none required for channel packaging  

### 4. Dependencias externas
* FCM/EAS/Play: **PARTIAL** → may be **BLOCKED_EXTERNAL** until accounts/config exist  
* Backend: **NONE** for packaging  

### 5. Data authority
Same as portal APIs (BILLTRACK/TICKETING/NETWORK via existing endpoints). No new SoT.

### 6. Effects
CHANNEL delivery of existing READ/push/ticket effects. No new COMMERCIAL_EFFECT.

### 7. Production risk
**MEDIUM** (store/FCM misconfig; customer install base).

### 8. Blast radius
`mobile/`, EAS secrets, FCM. Minimal backend. Not ACTIONS by default.

### 9. Reuse
Current Expo app + portal contracts.

### 10. Hard exclusions
New Agentic Actions; BSS; payment WRITE; milestone = polish-only without functional release goals.

### 11. Exit criteria
Prod build push+voice verified on device; QA checklist signed; release artifact; listed functional gaps closed or explicitly deferred.

---

## Cross-cutting hard exclusions (all options)

* payment WRITE  
* BSS EFFECTS  
* installation orders  
* admin ticket mutation  
* update_ticket as customer-facing Action  
* escalate_human as new ACTION in ACTIONS  
* Sensa WRITE  
* VoIP/Asterisk operational mutation  
* reopen 2.5  
* proactive without SoT  
* unauthorized commercial effects  

---

## Decision Required

Producto/Ops debe elegir exactamente UN eje:

* A — Proactive ISP Narrow  
* B — Billing READ + OV  
* C — Incident / Customer Experience  
* D — Mobile / Channel Experience  

Una vez elegida la opción, el siguiente milestone será:

**EKO 2.7C — IMPLEMENTATION SCOPE**

allí se definirán archivos, contratos, tests, runtime, producción, rollout, rollback y exit gate.

**NO** se ejecuta 2.7C en este documento.

```text
Production touched: NO
Configuration changed: NO
Runtime changed: NO
Tickets created: 0
Tickets modified: 0
Implementation performed: NO
```
