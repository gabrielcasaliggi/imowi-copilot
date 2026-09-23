# EKO 2.6 — Product Capability Gap & Next-Build Discovery

**Status:** DISCOVERY ONLY — PASS  
**Date:** 2026-09-23  
**Type:** Documentation only — no code, DB, endpoints, adapters, capabilities, or Runtime Actions  
**Baseline frozen:** `docs/EKO-2.5-CONVERSATIONAL-LAYER-FREEZE.md` (CLOSED / FROZEN)

---

## 1. Executive Summary

Eko already has a **working conversational/operational READ + bounded WRITE** surface over TrustedContext, BillTrack (RO), Estate tickets/outages, portal connectivity readers, and an allowlisted Action Runtime. Commercial transactional effects, managed campaigns, installation orders, payment lifecycle, and due-date authority remain **absent or external**.

This discovery does **not** invent sources. Classifications use only evidence in this workspace (code + prior EKO audits 2.1–2.5 / 2.2I / 2.3F–H / 2.4A–D).

**Technically first-enabled next-build candidate (dependency order, not product preference):**

> Customer-visible **ticket SLA-breach proactive push**, reusing Estate `sla_breached_at` + existing Expo proactive pipeline + ticket ownership patterns already proven in 2.3G/H.

Everything commercial EFFECT / campaign EFFECT stays blocked until an external BSS/content authority exists.

---

## 2. Current Product Baseline

| Layer | State |
|---|---|
| CASI (Policy / Motor / Runtime / confirmation) | Closed — intact |
| 2.1 Billing READ | Live: balance + invoice headers (FC) |
| 2.2 Service Management | Live: `service_list`, selection, bounded diagnostics; installation honest UNAVAILABLE; commercial HANDOFF |
| 2.3 Proactive | Live: outage + ticket lifecycle pushes; dedup + token hygiene |
| 2.4 Commercial / managed comms | Contracts only — **EFFECT_READY = NO** |
| 2.5 Continuity | **CLOSED / FROZEN** |
| Mobile | Expo push + portal APIs; reactive agent messages |

**Registered Runtime actions (evidence `list_registered_actions`):**

`send_message`, `show_balance`, `show_invoice`, `service_list`, `installation_status`, `show_ticket`, `open_OV`, `request_account_selection`, `run_diagnostic_pppoe`, `run_diagnostic_bcm`, `run_diagnostic_uisp`, `create_ticket`, `update_ticket`, `escalate_human`, `close_conversation`.

---

## 3. Authority Inventory

| Source | Mode | Ownership | Evidence | Notes |
|---|---|---|---|---|
| **TrustedContext** | TRUST | Backend rebuild | `eko_action_runtime.TrustedContext` | Never from LLM |
| **BillTrack `api_person`** | READ | `client_number` / DNI→CN | `billtrack.py` | Balance snapshot |
| **BillTrack `api_invoice`** | READ | `account_number` = CN | `eko_invoice_reader.py` | FC headers only; **no due_date/currency/lines** |
| **BillTrack `api_service`** | READ | CN | `portal_services` / billtrack | Inventory; **writer UNKNOWN/NOT_FOUND** |
| **BillTrack `api_billed_concept`** | — | — | Explicitly **not** used for amounts | Not authority for invoice total |
| **BillTrack payment tables** | — | — | **NOT wired** as Eko readers | Probe may see tables; not integrated |
| **Estate tickets + TicketEvent** | READ/WRITE | `ticket_pertenece_abonado` | `repository`, `abonado_tickets`, `ticket_bridge` | Authoritative support SoT |
| **Estate NetworkOutage** | READ/WRITE (ops) | NAS→abonado→PortalDevice | Outage API + 2.3D/H | Proactive READY |
| **PortalDevice / Expo tokens** | READ/WRITE | Owner DNI after ownership | `app_push.py` | Delivery, not content SoT |
| **Portal connectivity** | READ | Selected service / login | `portal_connectivity.py` | Canonical for PPPoE diag path |
| **Radius** | READ (tech) | Login from selected ref | `conexion_pppoe` / Runtime | Probe, not Facts auto |
| **BCM** | READ (tech) | Login / wifi | `conexion_bcm`, `wifi_bcm` | Bounded diagnostic |
| **UISP** | READ (tech) | Radio login | `conexion_uisp` | Bounded diagnostic |
| **OV / JSAT** | NAV / HANDOFF | Session handoff | `ov_handoff.py`, `open_OV` | Not commercial WRITE |
| **JSC** | — | — | Legacy telemetry — **not** ops UI SoT | Out of Eko product path |
| **WhatsApp / Telegram** | DELIVERY reactive | Conversation | Canal clients | Not campaign engine |
| **Email SMTP** | OPS | Agent emails | `handoff_notify`, SLA email | Not customer campaign |
| **KB / RAG** | DOCUMENTATION | Org KB | `knowledge_unified` / qa_bot | Not transactional authority |
| **LLM** | INTERPRET only | — | CASI | ≠ authority |

**Modes key:** READ · WRITE · EVENT · STATUS · OWNERSHIP · TRANSACTION · VERIFICATION — applied per capability below.

---

## 4. Capability Matrix

| Capability | Source | Authority | READ | WRITE | Ownership | Verification | Status |
|---|---|---|---|---|---|---|---|
| Account identity (abonado) | Estate + BillTrack | TrustedContext | Y | — | CN/DNI bind | Session | **READY** |
| Multi-account by phone | BillTrack/WA MSISDN | Auth + disambiguation | Y | — | Explicit pick | Gate | **READY** |
| Account selection ask | Runtime `request_account_selection` | Policy | Y | STATE | Trusted | Needs_input | **READY** |
| Contact means (phone on conv) | Estate ConversacionCanal | Channel | Y | Y (ops) | Conv | — | **PARTIAL** (not full CRM contact book) |
| Titularidad change | Playbook | Human | — | — | — | — | **HANDOFF_ONLY** |
| Balance | `api_person.billing_balance` | BillTrack READ | Y | — | CN | Snapshot | **READY** / **READ_READY** |
| Invoice headers (list FC) | `api_invoice` | BillTrack READ | Y | — | CN | Headers only | **READ_READY** |
| Invoice due_date / period / PDF / lines | — | — | — | — | — | — | **UNAVAILABLE** |
| Payment history | — | — | — | — | — | — | **UNAVAILABLE** / **EXTERNAL_DEPENDENCY** |
| Payment execute / receipt | Fiserv/OV | NAV | — | — | — | — | **HANDOFF_ONLY** / NAV |
| Informar pago (N1 copy) | Conversation + OV links | Not payment SoT | — | — | — | — | **HANDOFF_ONLY** / informational |
| Statement (`api_billing_statement`) | — | Not wired | — | — | — | — | **UNAVAILABLE** |
| `service_list` inventory | `api_service` | BillTrack READ | Y | — | CN | Catalog | **READY** / **READ_READY** |
| Service selection (`selected_service_ref`) | Catalog + ownership | 2.5 frozen | Y | STATE | CN | Catalog | **READY** |
| Diagnostic PPPoE | Portal connectivity / Radius | Tech READ | Y | — | Selected ref | ActionResult | **READY** |
| Diagnostic BCM / UISP | BCM / UISP | Tech READ | Y | — | Selected ref | ActionResult | **READY** |
| Installation status | — | None | — | — | — | Honest empty | **UNAVAILABLE** (Runtime returns unavailable) |
| Service add / plan change / cancel / alta | — | No BSS WRITE | — | — | — | — | **HANDOFF_ONLY** / **EXTERNAL_DEPENDENCY** |
| WiFi password / router config WRITE | — | No CPE WRITE API | — | — | — | — | **UNAVAILABLE** / playbook guidance |
| ONT reboot remote | — | No authenticated CPE WRITE | — | — | — | — | **UNAVAILABLE** (guidance only) |
| Telefonía fija / VoIP diagnostic | Catalog type only | No probe | listing | — | CN | — | **READ_READY** (list) / **HANDOFF_ONLY** (fix) |
| Sensa / IMOWI diagnostic | Catalog | No fixed-line diag | listing | — | CN | Honest unavailable | **READ_READY** / **HANDOFF_ONLY** |
| Create ticket | Estate | WRITE + confirm | — | Y | Abonado/conv | Ticket id | **READY** |
| Show / list tickets (abonado) | Estate | READ | Y | — | `ticket_pertenece_abonado` | Portal/Eko | **READY** / **READ_READY** |
| Update ticket | Estate | WRITE + policy | — | Y | Ownership | Event | **READY** (agent/ops paths; customer-bounded) |
| Ticket close / reopen | Estate / inbox | WRITE | — | Y | Ops/agent | Events | **PARTIAL** (ops); customer reopen not productized |
| Ticket timeline / events | TicketEvent | READ | Y | append | Ownership | Event id | **READY** / **READ_READY** |
| SLA ops email | `sla_breached_at` | Estate | — | notify ops | Ticket | Existing | **READY** (ops) |
| SLA customer proactive push | Same field | Estate EVENT | — | push | Ticket→abonado→device | Claim pattern | **PARTIAL** → **READY AFTER SMALL GAP** |
| Escalate human | Conv estado | WRITE STATE | — | Y | Conv | `espera_agente` | **READY** |
| Outage proactive | NetworkOutage | AUTHORITATIVE | — | EVENT | NAS map | Claims | **READY** |
| Ticket proactive (created/updated/closed) | TicketEvent | AUTHORITATIVE | — | EVENT | Portal ownership | Claims | **READY** |
| Billing/payment/connectivity proactive | — | No event stream | — | — | — | — | **UNAVAILABLE** / **PARTIAL** (state≠event) |
| Commercial catalog/price/promo/eligibility/order | — | NOT_FOUND | — | — | — | — | **EXTERNAL_DEPENDENCY** / **UNAVAILABLE** |
| OV navigation (`open_OV`) | OV URLs | NAV | Y | — | Session | — | **HANDOFF_ONLY** / NAV |
| Managed campaigns / inbox product | — | NOT_FOUND | — | — | — | — | **EXTERNAL_DEPENDENCY** / **UNAVAILABLE** |
| WhatsApp/TG reactive N1 | Meta/TG | Delivery | — | msg | Conv | — | **READY** (reactive) |
| Campaign WA/TG/Email | — | Consent/templates missing | — | — | — | — | **UNAVAILABLE** |
| KB answers | RAG/KB | Documentation | Y | — | Org | Citations | **READ_READY** (non-transactional) |
| Handoff continuity (2.5D-4) | `eko_handoff` | Transport≠authority | Y | STATE | Re-validate CN | Return path | **READY** (frozen) |
| Domain resume / refs (2.5) | CS + resolver | Deterministic | Y | STATE | Stack/catalog | Tests | **READY** (frozen) |

---

## 5. READ_READY Capabilities

Deterministic answers possible **without** transactional EFFECT:

- Balance (`show_balance`)
- Invoice FC headers list (`show_invoice` / `eko_invoice_reader`)
- Service inventory (`service_list` / portal services)
- Ticket facts for owned tickets (`show_ticket` / portal tickets)
- Connectivity observation after explicit diagnostic
- OV public navigation links (payment slip URL, etc.) — **navigation facts**, not payment confirmation
- KB/RAG informational answers
- Catalog listing of telefonia / TV / móvil (identity only)

---

## 6. READY Capabilities

Full chain (proposal → Policy → Runtime/Legacy XOR → result) with ownership:

- Multi-account disambiguation + account selection
- Canonical service selection (`apply_service_ref` / 2.5)
- Bounded diagnostics PPPoE / BCM / UISP
- Create ticket (with confirmation contract)
- Escalate / close conversation
- Outage proactive push (started / material / resolved)
- Ticket proactive push (created / updated / closed)
- Expo delivery + token hygiene (as implemented)
- Reactive agent→app message notify

---

## 7. PARTIAL Capabilities

| Item | What exists | What’s missing |
|---|---|---|
| Contact book / medios | Phone on conversation | Full CRM contact authority |
| Invoice “status changed” proactive | `state` field readable | Prior snapshot / transition event |
| Ticket assign customer notify | `asignado_a` | Not all paths emit customer-safe events |
| Customer SLA push | `sla_breached_at` + ops email | Customer policy allowlist + detector hook + claim |
| Ticket reopen by subscriber | Ops can mutate | No customer product path |
| Dual-write service shadow | `login_seleccionado` LEGACY_READ_REMAINS | Gradual migration (2.5 freeze L-04/L-05) |
| Update ticket from N1 | Runtime registered | Narrow confirmation / coverage vs legacy |

---

## 8. HANDOFF_ONLY Capabilities

- Alta plan / baja servicio / cambio de plan / cambio titularidad / domicilio
- Turno campo / installation ask (no work-order SoT)
- Payment execution (Fiserv/OV talón) — navigate or human
- “Informar pago” conversational path (not payment authority)
- Commercial sales / B2B cotización visitor queue
- Telefonía fija / Sensa / IMOWI **troubleshooting** beyond honest unavailable + human

---

## 9. EXTERNAL_DEPENDENCIES

| Dependency | Needed for |
|---|---|
| BSS/CRM commercial WRITE + identity of `api_service` writer | Alta, baja, plan change, add-on, order |
| Pricebook / promotion / eligibility engines | Offer presentation & EFFECT |
| Order API + idempotent transaction IDs + verification READ | Commercial completion |
| Installation / agenda / work-order SoT | Installation status EFFECT |
| BillTrack payment/receipt readers (if tables exist in env) | Payment history / payment events |
| Campaign content CMS + audience + approval + consent/templates | Managed communications |
| Customer APP_INBOX product | Non-push administrative inbox |

---

## 10. UNAVAILABLE Capabilities

- Invoice due_date, period, currency, line items, PDF (reader contract forbids inventing)
- Payment lifecycle events in Eko
- `api_billing_statement` as wired capability
- Remote ONT/router reboot / config WRITE
- Service commercial transition events (activated/suspended/…)
- Structured installation order status
- `ticket.resolved` as distinct proactive vocabulary (unsupported; closed mapped)
- Autonomic context from transcript (forbidden by 2.5)

---

## 11. Agentic Ops Readiness

| Element | Status |
|---|---|
| Closed tool / action registry | **READY** (`eko_action_runtime`) |
| Policy allow/deny/needs_* | **READY** |
| TrustedContext rebuild | **READY** |
| Confirmation ≠ LLM | **READY** (CASI) |
| Idempotency classes on specs | **READY** (SAFE/PROTECTED/RISK) |
| Runtime ↔ Legacy XOR | **READY** (coverage matrix) |
| Adapters for registered actions | **READY** for listed actions |
| Verification post-WRITE (commercial) | **NOT_FOUND** |
| Free-form tool calling | **Forbidden** (contract) |
| Observability journey/action logs | **PARTIAL** / present for journeys |

**Safe to execute today:** only allowlisted Runtime actions above, under Policy + ownership + confirmation when required.

---

## 12. Mobile Readiness

| Concern | Backend | Mobile UI | Classification |
|---|---|---|---|
| Outage push → Home refresh | READY | Exists (2.3H) | **READY** |
| Ticket push → Activity focus | READY | Exists (2.3G-M) | **READY** |
| Agent message push → Eko chat | READY | Exists | **READY** |
| Portal tickets/services/connectivity/billing APIs | READY (portal) | Portal + app consume | **READY** / **READ_READY** |
| Campaign / offer browse | NOT_FOUND | — | **UNAVAILABLE** |
| SLA customer push | PARTIAL backend | Would reuse ticket-style deep link | **READY AFTER SMALL GAP** |
| Commercial order UI | No backend EFFECT | — | **EXTERNAL_DEPENDENCY** |

**Rule:** Mobile UI ≠ backend capability. Do not claim parity from screens alone.

---

## 13. Cross-domain Dependencies

```text
Identity (TrustedContext / CN)
  → Service catalog READ
  → selected_service_ref (2.5 frozen)
  → Technical diagnostic READ
  → Ticket WRITE (confirm)
  → Proactive EVENT (outage/ticket)

Billing READ ──independent──→ same CN ownership

Commercial WRITE ──blocked──→ external BSS

Managed campaign ──blocked──→ content + audience + approval
```

Multi-account: phone may map to N accounts; capabilities that skip account selection are **not READY**.

---

## 14. Post-2.5 Invariants

Future phases **must** preserve:

1. `selected_service_ref` = READ SoT (`get_selected_ref`)
2. `ConversationState.domain_stack` = domain continuity (max 3)
3. TrustedContext = ownership authority
4. LLM content ≠ authority
5. Runtime / Legacy XOR
6. Confirmation bound to pending action + context
7. Handoff metadata ≠ authority; return re-validates
8. Transcript ≠ state
9. No invented sources / prices / eligibility / installation orders
10. No parallel conversational architecture beside frozen 2.5 contracts

Reference: `docs/EKO-2.5-CONVERSATIONAL-LAYER-FREEZE.md`.

---

## 15. Candidate Next Builds

### READY NOW (already shippable / live — not “new product”)

Inventory above under §6. No new phase required to “enable” them; maintain regression.

### READY AFTER SMALL GAP (workspace-only)

| Candidate | Gap inside workspace | Does not require |
|---|---|---|
| **Customer SLA-breach proactive push** | Detector on first `sla_breached_at` set; policy allowlist; claim column or reuse ticket-event pattern; Expo payload + mobile deep-link reuse | New BSS, new DB product, CASI rewrite, 2.5 changes |
| **Catalog check on handoff return** (freeze L-01) | Canal passes `catalog_for_selection` into `prepare_return_from_handoff` | External systems — **but touches 2.5 continuity → dedicated continuity regression, not incidental** |
| **Narrower customer ticket update notes** | Wire confirmed `update_ticket` paths with visible_cliente events | BSS |

### EXTERNAL DEPENDENCY

- Commercial alta/baja/plan/order/price/promo/eligibility
- Managed communications / campaigns
- Payment history / payment events (until BillTrack readers exist)
- Installation work orders

### NOT FEASIBLE WITH CURRENT ESTATE

- Invent due_date / PDF / line items without BillTrack fields
- Remote CPE reboot without WRITE API
- Autonomic resume from transcript
- LLM-authorized commercial completion

---

## 16. Explicit Non-Goals

- Do not reopen 2.5 conversational contracts without dedicated audit
- Do not invent commercial EFFECT
- Do not treat OV links as payment verification
- Do not treat playbook text as price/eligibility authority
- Do not build campaign engines on Expo alone
- Do not expand NLP / memory in “small” tickets
- Do not modify mobile in discovery phases

---

## 17. Recommended Execution Sequence

Technical dependency order (not preference ranking):

1. **Keep 2.5 frozen** — any continuity change = dedicated phase.
2. **Operate and regress** READY surface (billing READ, SM, diagnostics, tickets, outage/ticket push).
3. **If expanding proactive:** implement **customer SLA-breach push** (READY AFTER SMALL GAP) using Estate + Expo patterns from 2.3G/H — before inventing billing/payment detectors.
4. **If deepening billing READ:** run/env-confirm BillTrack schema for payment/due_date columns; only then add RO readers (else remain UNAVAILABLE). No inference from balance→0.
5. **Commercial EFFECT / managed campaigns:** blocked until external authorities identified (2.2I / 2.4C); keep HANDOFF_ONLY.
6. **Mobile UI work:** only after backend event/READ contracts exist for that feature.

**First capability technically enabled for a future implementation phase:**

```text
Customer-visible ticket SLA-breach proactive notification
```

Evidence: `Ticket.sla_breached_at` + `refresh_tickets_sla` + existing proactive push/claim/ownership stack. Gap is product allowlist + detector wiring — not a new authority system.

---

## Appendix A — Classification legend (used)

READY · READ_READY · PARTIAL · HANDOFF_ONLY · UNAVAILABLE · EXTERNAL_DEPENDENCY

## Appendix B — Evidence anchors

- Runtime registry: `app/services/eko_action_runtime.py`
- Invoice contract: `app/services/eko_invoice_reader.py`
- Commercial: `docs/EKO-2.2I-*`, `docs/EKO-2.4A/C-*`
- Proactive: `docs/EKO-2.3F-*`, `docs/EKO-2.3H-*`
- Continuity freeze: `docs/EKO-2.5-CONVERSATIONAL-LAYER-FREEZE.md`

---

**FINAL:** `EKO 2.6 DISCOVERY — PASS`  
**Code changes in this phase:** NONE
