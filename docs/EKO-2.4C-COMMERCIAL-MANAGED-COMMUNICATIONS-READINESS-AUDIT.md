# EKO 2.4C — COMMERCIAL & MANAGED COMMUNICATIONS AUTHORITY READINESS AUDIT

**Status:** PASS WITH FINDING  
**Phase type:** DISCOVERY / READINESS ONLY — no runtime changes  
**Depends on:**
- [EKO 2.4A — Commercial Offers Authority Discovery](./EKO-2.4A-COMMERCIAL-OFFERS-AUTHORITY-DISCOVERY.md)
- [EKO 2.4B — Commercial Offers & Managed Communications Contract](./EKO-2.4B-COMMERCIAL-OFFERS-MANAGED-COMMUNICATIONS-CONTRACT.md)
- [EKO 2.2G](./EKO-2.2G-COMMERCIAL-AUTHORITY-INTEGRATION-CONTRACT.md) · [2.2H](./EKO-2.2H-COMMERCIAL-ADAPTER-BOUNDARY.md) · [2.2I](./EKO-2.2I-FINAL-COMMERCIAL-AUTHORITY-TRACE.md)
- Proactive 2.3 (event-driven) — **unchanged**

**External WRITE calls:** NONE  
**CommercialAdapter:** NOT ACTIVE  
**ManagedCommunicationAdapter:** NOT ACTIVE  

Principio: **LLM content ≠ authority.**  
Documentación futura (2.4B) ≠ evidencia de integración existente.  
Credencial/config existente ≠ autoridad funcional.

---

## 1. Executive summary

Tras 2.4A/2.4B, una auditoría dirigida al workspace **reconfirma** (y en algunos puntos **precisa**) que:

| Domain | Verdict |
|---|---|
| **A — Commercial Offers** | Sin BSS/CRM WRITE, pricebook, promotion engine, eligibility engine ni order API. Inventory READ (`api_service`) y handoff humano existen. **EFFECT_READY = NO** |
| **B — Managed Communications** | Sin CMS/campaign authority, audience model, approval workflow ni scheduler de campañas. Delivery APP_PUSH existe **solo** para 2.3 event-driven. **MANAGED_COMMUNICATION EFFECT/DELIVERY_READY = NO** |

La ausencia de autoridades externas es **EXTERNAL DEPENDENCY NOT AVAILABLE**, no un fallo del audit.

**Hallazgo (FINDING):** el capability `service_list` documenta notas/postcondiciones con lenguaje “catálogo comercial” / `active=commercial_only` (`eko_capability_contract.py`), pero la fuente es inventario de servicios del abonado (BillTrack RO) — **no** un sellable catalog. No contradice 2.4A; es riesgo semántico de mislectura.

---

## 2. Scope

| In scope | Out of scope |
|---|---|
| Read-only evidence search in repo | Code/runtime changes |
| Map 2.4B contracts → real systems | Activating EFFECTS / adapters |
| Activation matrix + missing deps | External WRITE / notifications / campaigns |
| Contradictions vs 2.4A | Changing Billing, SM, Proactive, CASI, mobile |

---

## 3. Evidence standard

| Label | Meaning |
|---|---|
| **FACT** | Observable in code, SQL, models, UI, or config keys (values not exposed) |
| **INFERENCE** | Reasonable conclusion from FACT; marked as such |
| **DOCUMENTATION** | Docs/contracts only (2.2G–I, 2.4A/B, 2.3*) — not proof of live authority |

Authority classes used:  
`DOCUMENTATION_ONLY` · `READ_MODEL` · `DERIVED_STATE` · `HANDOFF` · `AUTHORITATIVE_READ` · `AUTHORITATIVE_WRITE` · `EXECUTION_AUTHORITY` · `VERIFICATION_AUTHORITY`

Activation levels used exclusively:  
`NOT_READY` · `DISCOVERY_READY` · `READ_READY` · `HANDOFF_ONLY` · `EFFECT_READY` · `DELIVERY_READY` · `VERIFICATION_READY`

---

## 4. Commercial authority findings (summary)

| Capability | Exists? | Authority class | Confidence |
|---|---|---|---|
| Customer/account (channel trust) | Yes | TrustedContext + BillTrack READ | High |
| Sellable product catalog | No | NOT_FOUND | High |
| Plan catalog (upgrade paths) | No | NOT_FOUND | High |
| Pricebook | No | NOT_FOUND | High |
| Promotion engine | No | NOT_FOUND / DOCUMENTATION_ONLY (KB text) | High |
| Eligibility (commercial) | No | NOT_FOUND | High |
| Commercial order API | No | NOT_FOUND | High |
| Order status / verification | No | NOT_FOUND | High |
| Installation / work order | No | UNAVAILABLE (2.2D runtime honest) | High |
| Commercial WRITE authz | No | NOT_FOUND | High |
| Writer of `api_service` | Unknown | WRITER_UNKNOWN | High |

---

## 5. Managed Communications findings (summary)

| Capability | Exists? | Authority class | Confidence |
|---|---|---|---|
| Communication content CMS | No | NOT_FOUND | High |
| Campaign entity | No | NOT_FOUND | High |
| Audience authority | No | NOT_FOUND (outage NAS segment ≠ campaign audience) | High |
| Approval workflow (comms) | No | NOT_FOUND (KB review tray ≠ campaign approval) | High |
| Campaign scheduler | No | NOT_FOUND | High |
| APP_PUSH delivery | Yes (2.3) | EXECUTION for **events**, not campaigns | High |
| APP_INBOX (customer) | No | NOT_FOUND (agent inbox ≠ customer inbox) | High |
| WA / TG / Email / SMS broadcast | Partial reactive clients | NOT campaign-ready | High |
| Dedup / frequency for campaigns | No | NOT_FOUND (2.3 claim/dedup ≠ campaign dedup) | High |

---

## 6. Customer / account authority

| Source | Role | Authority | Evidence |
|---|---|---|---|
| `TrustedContext` | Ownership binding for actions | Channel trust / runtime gate | **FACT:** `app/services/eko_action_runtime.py` `class TrustedContext` |
| BillTrack `api_person` / `client_number` | Padrón READ | READ_MODEL / AUTHORITATIVE_READ for billing identity snapshot | **FACT:** `app/services/billtrack.py` SELECT-only |
| Estate abonado cache | Ops support | DERIVED / cache | **FACT:** estate models |
| OV / JSAT | Session / handoff | HANDOFF / NAVIGATION | **FACT:** `ov_batan.py`, `ov_handoff.py` |
| Phone → account / DNI alone under multi-account | Must not decide ownership | Forbidden as sole SoT | **DOCUMENTATION** + existing N1 disambiguation patterns |

**Future commercial SoT candidate:** external BSS/CRM (NOT_FOUND). Until then, TrustedContext + BillTrack CN remain identity/ownership for READ/handoff — **not** commercial WRITE SoT.

**Do not replace TrustedContext.**

---

## 7. Catalog

### Inventory (what customer has)

| Item | Detail |
|---|---|
| Source | BillTrack `public.api_service` via `DEFAULT_SERVICES_SQL` |
| Fields | id, login, label, product, product_code, service_type_*, state, service_on, locality, dates |
| Capability | `service_list` → `evaluar_servicios_portal` |
| Class | **READ_MODEL** |
| Activation | **READ_READY** for inventory listing |

**FACT:** no price / currency / billing_period / sellable / eligibility columns in Eko SELECTs (`billtrack.py`).

### Sellable commercial catalog

| Question | Answer |
|---|---|
| Authoritative sellable catalog? | **NOT_FOUND** |
| Maps to 2.4B Product Catalog contract? | Contract exists (DOCUMENTATION); no backend |
| Activation | **NOT_READY** / DISCOVERY_READY only |

**FINDING (semantic):** `eko_capability_contract.py` notes for `service_list` say “catálogo comercial” and postcondition `active=commercial_only`. **INFERENCE:** “commercial_only” filters inventory rows (vs technical), not “sellable offer catalog.” Treat as naming hazard; authority class remains READ_MODEL inventory.

---

## 8. Pricebook

| Candidate | Verdict |
|---|---|
| Dedicated pricebook / tariff API | **NOT_FOUND** |
| `api_invoice.amount` | Billing document amount — **≠** plan_price (**FACT** + 2.4A/B rule) |
| KB / seed plan tiers | DOCUMENTATION_ONLY / orientative (**FACT:** `estate/seed.py` warns “confirmar precios”) |
| JSC `saldo_resumen` / plan strings | DEMO / PREVIEW (**FACT:** `app/jsc/contract.py`) |

**PRICE AUTHORITY = NOT_FOUND** → activation **NOT_READY**.

---

## 9. Promotions

| Search | Result |
|---|---|
| Tables/APIs campaign/promo/discount | **NOT_FOUND** in app clients |
| Playbook/KB promotional copy | DOCUMENTATION_ONLY; N1 **blocks invented promo** (**FACT:** `canal_abonado.py`, `eco_voice.py`, tests anti-promo) |
| Class | NOT_FOUND / DOCUMENTATION_ONLY |

**PROMOTION AUTHORITY = NOT_FOUND** → **NOT_READY**.  
KB text ≠ CommercialPromotion.

---

## 10. Eligibility

| Kind | Status | Evidence |
|---|---|---|
| Technical coverage (BCM/UISP/Radius) | Tech READ | ≠ commercial eligibility |
| Commercial “can this account buy X?” | **NOT_FOUND** | No eligibility API/client |
| Debt snapshot | Billing READ | ≠ offer gate engine |

**Technical availability ≠ commercial eligibility.**  
Activation: **NOT_READY**.

---

## 11. Orders (commercial operations)

| Operation | Runtime EFFECT | Path today | Class |
|---|---|---|---|
| `service_high` / alta | Not registered | Playbook `alta_plan` | **HANDOFF_ONLY** |
| `service_add` | Not registered | — | **UNAVAILABLE** / HANDOFF |
| `plan_change` | Not registered | Human / playbook | **HANDOFF_ONLY** |
| `service_cancel` | Not registered | Playbook `baja_servicio` | **HANDOFF_ONLY** |
| Order CREATE API | — | — | **NOT_FOUND** |

**FACT:** Grep over `app/` finds **no** `CommercialAdapter` / `service_high` / `service_plan_change` runtime registration.  
**FACT:** Confirmation pattern `confirmation_pending` + `resolve_user_confirmation` exists for non-commercial actions (`eko_journeys.py`, `eko_action_runtime.py`) — reusable **later**, not activated for commerce.

Checks required by 2.4B for any future WRITE (authn/z, ownership, idempotency, tx id, status, verification, compensation): **all absent** for commercial domain.

Activation: commercial WRITE = **NOT_READY**; conversational handoff = **HANDOFF_ONLY** (already live, no new EFFECT).

---

## 12. Verification

| Item | Status |
|---|---|
| Post-write commercial verification READ | **NOT_FOUND** |
| Order status machine (REQUESTED→COMPLETED) | **NOT_FOUND** |
| HTTP 200 as completion | Forbidden by contract; no commercial path to misuse |

**VERIFICATION_READY = NO**.

---

## 13. Installation / work order

| Item | Status | Evidence |
|---|---|---|
| Structured agenda / work order SoT | UNAVAILABLE | **FACT:** `_exec_installation_status` returns unavailable (`eko_action_runtime.py`) |
| CommercialOrder → InstallationOrder | EXTERNAL_DEPENDENCY | **DOCUMENTATION** 2.4B; no implementation |

Activation: **NOT_READY**.

---

## 14. Communication authority

| Candidate | Class | Why not ManagedCommunication SoT |
|---|---|---|
| Outage admin UI + `NetworkOutage` | Proactive Event Authority (2.3) | EVENT-driven ops declare, not campaign CMS |
| Agent inbox (`/inbox`) | Operator conversation tray | Not customer campaign content |
| KB + contribution review tray | Knowledge approval | RAG content ≠ approved campaign |
| TicketNotification / handoff_notify | Ops agent alerts | Not subscriber campaign |
| AutomationPanel “CRM webhooks” | UI roadmap copy | **DEMO / DOCUMENTATION** — not wired authority |
| 2.4B ManagedCommunication model | DOCUMENTATION_ONLY | Future contract |

**COMMUNICATION MANAGEMENT AUTHORITY = NOT_FOUND.**

---

## 15. Audience / segmentation

| Mechanism | Purpose today | Campaign audience? |
|---|---|---|
| Outage NAS / locality segmentation (`app_push._enviar_incidente_segmentado`) | Event push targeting | **No** — event-scoped (**FACT**) |
| Ticket ownership → device tokens | Ticket proactive | **No** |
| TrustedContext / client_number | Ownership | Required base; not segment CMS |
| LLM / phone / DNI inference | — | **Forbidden** as audience SoT |

**AUDIENCE AUTHORITY = NOT_FOUND.**

---

## 16. Approval workflow

| Candidate | States | Maps to 2.4B DRAFT→APPROVED→ACTIVE? |
|---|---|---|
| KB contributions | pendiente → approved/rejected | Analog only; **not** campaign approval |
| Outage declare/resolve | Ops lifecycle | Event authority, not campaign |
| Managed Communication approval | — | **NOT_FOUND** |

**APPROVAL_AUTHORITY (comms) = NOT_FOUND.**  
LLM never approves (CASI preserved).

---

## 17. Scheduling

| Mechanism | Exists? | Campaign scheduling? |
|---|---|---|
| Dedicated campaign cron/worker/queue | **NOT_FOUND** | — |
| FastAPI `BackgroundTasks` | Yes (request-scoped) | Not campaign scheduler |
| Proactive delivery on outage/ticket transitions | Yes | Event-driven, not `effective_from` campaign schedule |
| `scheduled_at` fields in installation action | Always null / unavailable | Honest unavailable |

No timezone/campaign cancel model for managed comms.  
**SCHEDULING AUTHORITY = NOT_FOUND.**

---

## 18. Channels

| Channel | Provider / adapter | Production usage | Managed-comms suitable today? |
|---|---|---|---|
| **APP_PUSH** | Expo via `enviar_push_expo` / `app_push.py` | Outage + ticket proactive (2.3) | Delivery **layer** reusable later; **not** campaign-ready without content/audience/approval/dedup |
| **APP_INBOX** (customer) | — | **NOT_FOUND** | No |
| Agent inbox | `api/v1/inbox.py` | Operator WA/TG/web | Not subscriber campaign channel |
| **WHATSAPP** | `whatsapp_client.enviar_texto` | Reactive N1 / handoff replies | Reactive ≠ broadcast campaign; consent/rate/template policy for campaigns **NOT_FOUND** |
| **TELEGRAM** | `telegram_client.enviar_texto` | Reactive | Same |
| **EMAIL** | SMTP `email.py` | Invites, OTP, agent handoff notify | Not subscriber campaign engine |
| **SMS** | Context for tickets only (`ticket_contexto.py`) | Support data, not A2P campaign sender | **NOT_AVAILABLE** as campaign |

Credential keys exist for WA/TG/SMTP/Expo/BillTrack/OV — register **“credential exists”** only; values not inspected. Credential ≠ campaign authority.

---

## 19. Proactive 2.3 boundary

| Model | Pipeline |
|---|---|
| 2.3 | EVENT → POLICY → DEDUP → DELIVERY |
| 2.4 (future) | CONTENT → AUDIENCE → POLICY → SCHEDULE → DEDUP → DELIVERY |

**FACT:** Policy allows only `app_push` for supported `outage.*` / `ticket.*` (`eko_proactive_policy.py`).  
**Rule:** Do not reuse outage/ticket `push_claimed_at` / fingerprint dedup as campaign dedup.  
**This audit did not modify 2.3.**

---

## 20. CASI boundary

Preserved architecture for any future activation:

```text
LLM → interpretation / proposal / wording
ConversationState → context
Policy → authorization
Motor → transition
Runtime → execution
Adapter → external authoritative effect
Renderer → customer response
```

**Forbidden (still absent as paths):**
- LLM → commercial WRITE / BSS  
- LLM → campaign activation  
- LLM → notification send authorization  

**FACT:** Anti-promo / anti-invention guards in N1 reinforce LLM ≠ commercial authority.

---

## 21. Security

| Topic | Status |
|---|---|
| BillTrack RO posture | **FACT:** module + SQL must be SELECT (`billtrack.py`) |
| Commercial WRITE credentials | **NOT_FOUND** as dedicated client |
| OV cookie scrape / session impersonation as commerce | Not implemented as commercial path; forbidden by contracts |
| Ownership | TrustedContext required on authorized actions |
| Secrets | Config keys present; **values not copied** |
| Author/reviewer/approver separation for campaigns | **NOT_FOUND** |

---

## 22. Activation matrix

### Commercial

| Capability | Authority | Type | Current State | Activation Ready | Missing |
|---|---|---|---|---|---|
| customer/account | TrustedContext + BillTrack | READ_MODEL / trust | Live for READ | READ_READY (identity) | BSS commercial SoT |
| product catalog (sellable) | — | NOT_FOUND | Absent | NOT_READY | External catalog |
| plan catalog | — | NOT_FOUND | Absent | NOT_READY | External plan catalog |
| pricebook | — | NOT_FOUND | Absent | NOT_READY | Pricebook API |
| promotions | — | NOT_FOUND | Absent | NOT_READY | Promotion authority |
| eligibility | — | NOT_FOUND | Absent | NOT_READY | Eligibility engine |
| service_add | — | UNAVAILABLE | No EFFECT | NOT_READY | WRITE API + gates |
| plan_change | Playbook | HANDOFF | Human | HANDOFF_ONLY | WRITE API + catalog/price |
| service_cancel | Playbook | HANDOFF | Human | HANDOFF_ONLY | WRITE API |
| service_high | Playbook | HANDOFF | Human | HANDOFF_ONLY | WRITE API |
| order creation | — | NOT_FOUND | Absent | NOT_READY | Order API + idempotency |
| order status | — | NOT_FOUND | Absent | NOT_READY | Status API |
| verification | — | NOT_FOUND | Absent | NOT_READY | Post-write READ |
| installation/work order | Runtime unavailable | UNAVAILABLE | Honest empty | NOT_READY | Work-order SoT |

### Managed Communications

| Capability | Authority | Type | Current State | Activation Ready | Missing |
|---|---|---|---|---|---|
| communication content | — | NOT_FOUND | Absent | NOT_READY | CMS / content API |
| campaign | — | NOT_FOUND | Absent | NOT_READY | Campaign model |
| audience | — | NOT_FOUND | Absent | NOT_READY | Audience authority |
| approval | — | NOT_FOUND | Absent | NOT_READY | Approval workflow |
| scheduling | — | NOT_FOUND | Absent | NOT_READY | Scheduler |
| APP_PUSH | Expo + PortalDevice | Event delivery | 2.3 live | DISCOVERY_READY (reuse layer later) | Campaign policy + content + audience + dedup |
| APP_INBOX | — | NOT_FOUND | Absent | NOT_READY | Customer inbox product |
| WhatsApp | Meta client | Reactive | N1 replies | NOT_READY (campaigns) | Templates, consent, rate, campaign policy |
| Telegram | Bot API | Reactive | N1 replies | NOT_READY | Same |
| Email | SMTP | Ops/auth | Invites/OTP/handoff | NOT_READY | Campaign content + audience |
| SMS | — | NOT_AVAILABLE | Context only | NOT_READY | Provider + authority |
| dedup (campaign) | — | NOT_FOUND | — | NOT_READY | Campaign dedup keys |
| frequency policy | — | NOT_FOUND | — | NOT_READY | Caps / quiet hours model |
| audit (campaign) | — | NOT_FOUND | — | NOT_READY | Audit events 2.4B |

**Overall:**  
`COMMERCIAL EFFECT_READY = NO`  
`MANAGED_COMMUNICATION EFFECT_READY = NO`  
`MANAGED_COMMUNICATION DELIVERY_READY = NO`

---

## 23. Missing dependencies

### Commercial (from 2.4B §32 — still unmet)

1. BSS/CRM authoritative source  
2. Commercial WRITE API  
3. Product catalog (sellable)  
4. Pricebook  
5. Promotion authority  
6. Eligibility engine  
7. Order API  
8. Order status API  
9. Post-write verification  
10. Authn/z for WRITE (≠ BillTrack RO)  
11. Idempotency contract (live)  
12. Installation/work-order when applicable  
13. Identity of `api_service` writer + lag (**WRITER_UNKNOWN**)

### Managed Communications (still unmet)

1. Communication authority / CMS  
2. Campaign/content model  
3. Audience model  
4. Approval workflow  
5. Scheduling model  
6. Channel policy for campaigns  
7. Dedup/frequency model (separate from 2.3)  
8. ManagedCommunicationAdapter  
9. Audit model  
10. Authorization (author ≠ reviewer ≠ approver ≠ executor)

---

## 24. Contradictory evidence

| Topic | Previous (2.4A) | New evidence (2.4C) | Resolution |
|---|---|---|---|
| Sellable catalog | NOT_FOUND | Reconfirmed; no new tables/clients | **No contradiction** |
| Pricebook | NOT_FOUND | Reconfirmed | **No contradiction** |
| `api_service` writer | UNKNOWN | No INSERT/UPDATE/ETL in-repo; only SELECT client | **WRITER_UNKNOWN** reconfirmed |
| CommercialAdapter | NOT ACTIVE | No class/module in `app/` | Reconfirmed |
| `service_list` naming | Inventory READ_READY | Capability notes say “catálogo comercial” | **FINDING:** semantic ambiguity; does **not** elevate authority. Do not rewrite 2.4A; flag for future clarity if capability docs edited |
| Outage push “segmentación” | (2.3) | Exists for events | **Not** Managed Communications audience — clarify only |

No evidence found that upgrades any 2.4A **NOT_FOUND** commercial WRITE capability to EFFECT_READY.

---

## 25. Possible partial activation (analysis only — NOT implementing)

| Candidate | Would CASI allow later? | Ready now? | Notes |
|---|---|---|---|
| Inventory “qué tengo” READ | Yes (already) | **READ_READY** | Already live via `service_list` |
| Sellable offer browse without price | Only with authoritative catalog | **NOT_READY** | No catalog |
| Price presentation | Only with pricebook | **NOT_READY** | — |
| Commercial HANDOFF playbooks | Yes | **HANDOFF_ONLY** | Already live |
| Admin draft storage for campaigns | Yes if estate-only drafts, no send | **NOT_READY** | No model/UI |
| Preview-only rendering of managed content | Yes if Policy gates + no delivery | **NOT_READY** | No content SoT |
| Reuse Expo push for campaigns | Only after content+audience+approval+dedup | **NOT_READY** | Delivery layer ≠ campaign authority |

**Do not confuse preview/demo (JSC, AutomationPanel roadmap) with production authority.**

---

## 26. Recommended next gate

Evidence-based options (pick one when product prioritizes):

1. **STOP / wait for external BSS + Communication Authority** — default; no EFFECT work.  
2. **2.4D (optional naming hygiene)** — clarify `service_list` “catálogo comercial” wording in capability contract docs/comments so inventory ≠ sellable (still no EFFECT).  
3. **External integration brief** — when partner delivers catalog/pricebook/order/comms APIs, map 2.4B fields → endpoints before any adapter code.

**Do not start CommercialAdapter or ManagedCommunicationAdapter implementation until activation gates in §23 are met.**

---

## 27. Validation (this phase)

| Check | Result |
|---|---|
| Runtime / API / DB / migrations | Unchanged by this audit |
| Billing / SM / Proactive / CASI / mobile | Unchanged |
| External writes / notifications / commercial EFFECTS | None |
| Deliverable | This document only |

---

## 28. Final classification

**STATUS: PASS WITH FINDING**

- Audit completed with evidence for all required authorities.  
- FINDING = semantic naming risk on `service_list` + universal EXTERNAL DEPENDENCY absence for commercial WRITE and managed campaigns.  
- Absence of BSS/CMS is **EXTERNAL DEPENDENCY NOT AVAILABLE**, not audit failure.  
- Commercial Offers and Managed Communications remain separated.  
- LLM has no authority. 2.3 and CASI intact. No effects activated.
