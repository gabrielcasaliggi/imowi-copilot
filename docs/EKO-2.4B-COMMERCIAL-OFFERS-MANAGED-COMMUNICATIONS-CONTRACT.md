# EKO 2.4B — COMMERCIAL OFFERS & MANAGED COMMUNICATIONS CONTRACT

**Status:** FUTURE CONTRACT / NOT ACTIVE  
**Phase:** Documentation-only  
**Runtime impact:** NONE — not imported by application code  
**Depends on:**  
- [EKO 2.4A — Commercial & Offers Authority Discovery](./EKO-2.4A-COMMERCIAL-OFFERS-AUTHORITY-DISCOVERY.md)  
- [EKO 2.2G — Commercial Authority & Integration Contract](./EKO-2.2G-COMMERCIAL-AUTHORITY-INTEGRATION-CONTRACT.md)  
- [EKO 2.2H — Commercial Adapter Boundary](./EKO-2.2H-COMMERCIAL-ADAPTER-BOUNDARY.md)  
- Proactive 2.3 (event-driven) — **unchanged**

> **No inventar backend.** Mientras las autoridades externas no existan:  
> `COMMERCIAL EFFECT_READY = NO` · `MANAGED_COMMUNICATION_EFFECT_READY = NO`

Principio: **LLM content ≠ authority.**

---

## 1. Scope

Este documento prepara el contrato técnico futuro entre Eko y autoridades externas de:

| Letter | Authority |
|---|---|
| A | BSS / CRM / ERP comercial |
| B | Product Catalog (sellable) |
| C | Pricebook |
| D | Promotion Engine |
| E | Eligibility Engine |
| F | Order / Commercial Transaction API |
| G | Order Status / Verification API |
| H | Managed Communications / Campaign Authority |

**No** implementa EFFECTS, journeys comerciales, notificaciones reales, escrituras externas ni adapters activos.

Evolución comercial esperada (futuro):

```text
READ ONLY → OFFER DISCOVERY → ELIGIBILITY → USER CONFIRMATION
  → COMMERCIAL ORDER → VERIFICATION
```

Evolución comunicaciones gestionadas (futuro, paralelo):

```text
MANAGED CONTENT → POLICY → AUDIENCE → CHANNEL → DELIVERY
```

---

## 2. Two domains (must not conflate)

### DOMAIN A — COMMERCIAL OFFERS

Promoción, upgrade, cambio de plan, alta, descuento, beneficio temporal, bundle, campaña comercial **como oferta contratables**.

Entidades: catalog, pricebook, promotion, eligibility, CommercialOffer, CommercialOrder.

### DOMAIN B — MANAGED COMMUNICATIONS

Mantenimiento programado, aviso administrativo, cambio operativo, institucional, recordatorio de facturación, información de servicio, mensajes de atención, comunicación segmentada.

Entidad: ManagedCommunication (+ audience, approval, channel policy).

| Rule |
|---|
| Not every communication is a promotion |
| Not every promotion requires a notification |
| `type=COMMERCIAL` on a communication ≠ CommercialOffer |
| Offers live in Domain A; messages about offers may live in Domain B |

---

## 3. Authority model

### 3.1 Commercial Authority (BSS/CRM/ERP)

Authoritative for: customer/account, ownership binding, products, plans, sellable offers, prices, billing period, promotions, eligibility, commercial orders, transaction status, completion.

Per entity (when available): `source_of_truth`, `identifier`, `version`, `effective_from`, `effective_to`, `status`, auditability.

**Today:** Commercial Authority = **NOT_AVAILABLE** (2.4A).

### 3.2 Communication Authority

Authoritative for: content, audience, vigencia, priority, channels, campaign, approval workflow.

**Today:** **NOT_AVAILABLE**.

### 3.3 Proactive Event Authority (2.3)

Authoritative for operational events (outage, ticket lifecycle). **Do not modify in 2.4B.**

### 3.4 Non-authorities (must not be reinterpreted)

| System | Role |
|---|---|
| BillTrack | READ ONLY / billing + padrón READ |
| `api_service` | READ MODEL / customer service **inventory** |
| OV | NAVIGATION / HANDOFF |
| JSAT | HANDOFF |
| Estate | Operations / support |
| KB / LLM text | DOCUMENTATION / wording only |
| Invoice amount | Billing document — **≠ plan price** |

---

## 4. Sellable product catalog

### 4.1 Contract fields (future)

| Field | Required |
|---|---|
| product_id | Yes |
| product_code | Yes |
| product_name | Yes |
| product_type | Yes |
| description | Optional |
| service_type | Yes |
| technical_attributes | Optional |
| commercial_attributes | Optional |
| active | Yes |
| effective_from / effective_to | Yes |
| version | Yes |

### 4.2 Distinction

| Catalog | Meaning |
|---|---|
| **Inventory / customer service catalog** | What the customer **already has** (`api_service` READ) |
| **Sellable commercial catalog** | What may be **sold / changed to** |

`api_service` labels/`product_code` are **informational inventory**, not automatically sellable authority.

**Today:** sellable catalog = **NOT_FOUND**.

---

## 5. Pricebook

| Field | Required |
|---|---|
| price_id | Yes |
| product_id / plan_id | Yes |
| amount | Yes |
| currency | Yes |
| billing_period | Yes |
| tax_inclusion | Yes |
| effective_from / effective_to | Yes |
| version | Yes |
| status | Yes |

**Rule:** `invoice.amount` ≠ `plan_price`. Historical invoice amounts must not substitute the pricebook.

**Today:** pricebook = **NOT_FOUND**.

---

## 6. Promotions — `CommercialPromotion`

| Field | Notes |
|---|---|
| promotion_id, promotion_code, name, description | Identity |
| product_ids, plan_ids | Scope |
| benefit_type, benefit_value, price_override, discount | Economics |
| effective_from / effective_to, status | Lifecycle |
| terms_and_conditions | Customer-facing legal |
| eligibility_rule_id | Link to eligibility |
| priority, stackable | Composition |
| version | Audit |

**States:** `DRAFT` | `SCHEDULED` | `ACTIVE` | `PAUSED` | `EXPIRED` | `CANCELLED`

Promotion must be an **authoritative entity**. Eko must not infer promotions from KB text.

**Today:** promotion authority = **NOT_FOUND**.

---

## 7. Eligibility — `check_eligibility()`

### Input (minimum)

`trusted_client_number`, account, `selected_service_ref`, `product_id`/`plan_id`, `promotion_id`, channel, context, `correlation_id`

### Output (minimum)

`eligible`, `reason_code`, `reason_detail`, `eligible_offer`, `constraints`, `evaluated_at`, `authority`, `version`

### Forbidden inference sources

LLM · conversation text · current speed alone · technical coverage alone · name matching · DNI alone · phone→account

**Technical availability ≠ commercial eligibility.**

**Today:** eligibility engine = **NOT_FOUND**.

---

## 8. CommercialOffer (normalized discovery object)

| Field | Notes |
|---|---|
| offer_id | Stable id from authority or composition key |
| product, plan, price, promotion | Nested refs + versions |
| eligibility | Result of check_eligibility |
| benefits, terms, effective dates | |
| source, version | Authority provenance |
| CTA, presentation metadata | Non-authoritative UX |

| Stage | Meaning |
|---|---|
| OFFER DISCOVERY | Show / list |
| OFFER AUTHORIZATION | Policy + eligibility + ownership |
| ORDER EXECUTION | Runtime → CommercialAdapter |

Showing an offer ≠ user may contract it.

---

## 9. Commercial operations (future declaration only)

Operations: `service_add` | `plan_change` | `service_cancel` | `service_high`

Each request declares:

`operation`, `trusted_client_number`, `selected_service_ref`, `product_id`, `plan_id`, `promotion_id`, `eligibility_result`, `confirmation`, `idempotency_key`, `correlation_id`, `channel`, `contract_version`

**Not implemented in 2.4B.**

---

## 10. Confirmation

Required when operation produces: alta, baja, plan change, contratación, costo, compromiso comercial.

Bound to: operation + product/plan + promotion + price + `selected_service_ref` + `client_number` + `idempotency_key`.

If any bound element changes → **INVALIDATE CONFIRMATION**.

Reuse conceptual pattern `confirmation_pending` + `resolve_user_confirmation` — **do not activate** for commercial EFFECTS in this phase.

---

## 11. CommercialOrder

| Field | Required |
|---|---|
| order_id | Yes (external or mirrored) |
| external_transaction_id | Yes when authority provides |
| client_number | Yes |
| operation, items, price, promotion | Yes |
| requested_at, accepted_at, completed_at | As available |
| status | Yes |
| correlation_id, idempotency_key | Yes |
| source, version | Yes |

**States:** `REQUESTED` | `ACCEPTED` | `PROCESSING` | `COMPLETED` | `REJECTED` | `FAILED` | `CANCELLED` | `UNKNOWN`

| Rule |
|---|
| ACCEPTED ≠ COMPLETED |
| TIMEOUT ≠ SUCCESS |
| UNKNOWN ≠ SUCCESS |
| HTTP 200 ≠ COMPLETED |

---

## 12. Idempotency

| Party | Generates |
|---|---|
| Eko | `idempotency_key`, `correlation_id` |
| External authority | `external_transaction_id`, `order_id` |

Same intent must not create two commercial orders.

Contract must define (when authority exists): TTL, replay behavior, duplicate response, conflict behavior.

**Today:** commercial idempotency semantics = **NOT_FOUND** (do not invent).

---

## 13. Post-write verification

```text
REQUEST → ACCEPTED → STATUS → VERIFY → COMPLETED
```

Never assume completion from HTTP 200 alone. Authoritative READ-back required. If verification fails → **do not** tell the customer success.

**Today:** COMPLETION_VERIFICATION = **NOT_FOUND**.

---

## 14. Installation / work order dependency

When commercial op requires field work:

```text
CommercialOrder → InstallationOrder / WorkOrder
```

Future fields (minimum): `installation_order_id`, `order_id`, `status`, `scheduled_at`, `completed_at`, technician, address/reference, appointment data.

**Today:** UNAVAILABLE / EXTERNAL_DEPENDENCY (2.2D / 2.4A). Do not invent agenda.

---

## 15–16. ManagedCommunication

Independent of CommercialOffer.

**Types (initial):** `ADMINISTRATIVE` | `OPERATIONAL` | `BILLING_INFORMATION` | `SERVICE_INFORMATION` | `INSTITUTIONAL` | `COMMERCIAL`

`COMMERCIAL` type ≠ automatic CommercialOffer.

### Fields (minimum)

`communication_id`, `campaign_id`, `type`, `title`, `body`, `rich_body`/`content`, `image_url`, `icon`, `cta`, `cta_url`, `priority`, `status`, `created_at`, `updated_at`, `effective_from`, `effective_to`, `created_by`, `approved_by`, `version`, `audience_id`, `channel_policy`, `frequency_policy`, `correlation_id`

**States:** `DRAFT` | `SCHEDULED` | `ACTIVE` | `PAUSED` | `EXPIRED` | `CANCELLED`

**No delivery in this phase.**

---

## 17. Audience / segmentation

Audience examples: all subscribers; product/plan cohorts; service cohorts; authorized geo; administrative condition; promotion-eligible set.

| Rule |
|---|
| No LLM inference for audience |
| Deterministic rules / commercial or admin authority / TrustedContext ownership |
| Never phone→account or DNI→account under multi-account ambiguity |
| Prefer `client_number` + proven ownership |

**Today:** audience authority = **NOT_FOUND**.

---

## 18. Channel policy

Declared channels: `APP_PUSH` | `APP_INBOX` | `WHATSAPP` | `TELEGRAM` | `EMAIL` | `SMS`

Per channel: `ENABLED` | `DISABLED` | `NOT_AVAILABLE`

Also: preferred/fallback, eligibility, consent, rate limits, quiet hours, frequency caps.

Missing channel must not auto-enable another. **Do not activate new channels in 2.4B.**

---

## 19. Relation to Proactive 2.3

| Model | Flow |
|---|---|
| **2.3 Event-driven** | EVENT → POLICY → DEDUP → DELIVERY |
| **2.4 Managed/campaign** | CONTENT → AUDIENCE → POLICY → SCHEDULE → DEDUP → DELIVERY |

May share delivery adapters **in the future**. **Do not modify 2.3** in this step. Do not mix models.

---

## 20. Dedup / frequency / anti-spam (managed)

Conceptual keys: `communication_id`, `campaign_id`, audience identity, channel, delivery identity, dedup key.

Policies: `once_per_campaign`, `once_per_period`, cooldown, frequency_cap, quiet_hours, suppression.

**Do not implement engine; do not modify 2.3E anti-spam.**

---

## 21. Approval workflow (communications)

```text
DRAFT → REVIEW → APPROVED → SCHEDULED → ACTIVE → PAUSED / EXPIRED
```

Fields: `created_by`, `reviewed_by`, `approved_by`, timestamps, version.

**LLM never approves** a communication.

---

## 22. Authority separation (summary)

| Authority | Authorizes |
|---|---|
| Commercial | product, plan, price, promotion, eligibility, order |
| Communication | content, audience, vigencia, priority, channels, campaign, approval |
| Proactive event (2.3) | real operational events |

None replaceable by LLM.

---

## 23. CASI integration

```text
LLM → interpretation / proposal / wording
ConversationState → context
Policy → authorization
Conversation Motor → transition
Runtime → execution
External Authority / Adapter → authoritative effect
Renderer → customer response
```

Communications path:

```text
ManagedCommunication Authority → Policy → Delivery Adapter → Channel Provider
```

LLM may draft conversational variants **only when Policy allows**. Existence, vigencia, audience, and authorization of the communication **must not** depend on the LLM.

---

## 24. CommercialAdapter boundary

Reuses [EKO-2.2H](./EKO-2.2H-COMMERCIAL-ADAPTER-BOUNDARY.md).

**Only** component authorized to invoke commercial WRITE authority for EFFECTS.

Forbidden:

```text
LLM → BSS
Journey → BSS
Policy → BSS
Renderer → BSS
```

Allowed future call chain:

```text
Policy → Runtime → CommercialAdapter → External Commercial Authority → Verify
```

**Status:** NOT ACTIVE.

---

## 25. ManagedCommunicationAdapter (future)

Responsibilities: load approved content; validate version; resolve authorized audience; apply channel + dedup + frequency policy; deliver via provider; record result.

Forbidden: LLM / Journey / Renderer calling providers directly.

**Status:** NOT ACTIVE / NOT IMPLEMENTED.

---

## 26. Audit trail

### Commercial

`offer_proposed`, `eligibility_checked`, `confirmation_requested`, `confirmation_received`, `order_submitted`, `order_accepted`, `order_processing`, `order_completed`, `order_failed`, `order_verified`, `order_handoff`

### Communication

`communication_created`, `communication_updated`, `communication_approved`, `communication_scheduled`, `communication_activated`, `communication_suppressed`, `communication_delivered`, `communication_failed`, `communication_expired`, `communication_cancelled`

Never log success without corresponding authority confirmation.

---

## 27. Error model

`AUTHORITY_UNAVAILABLE` · `UNAUTHORIZED` · `OWNERSHIP_MISMATCH` · `INVALID_PRODUCT` · `INVALID_PLAN` · `INVALID_PROMOTION` · `NOT_ELIGIBLE` · `PRICE_CHANGED` · `CONFIRMATION_REQUIRED` · `DUPLICATE_REQUEST` · `ORDER_REJECTED` · `ORDER_FAILED` · `ORDER_UNKNOWN` · `VERIFICATION_FAILED` · `COMMUNICATION_INVALID` · `AUDIENCE_UNRESOLVED` · `CHANNEL_UNAVAILABLE` · `DELIVERY_FAILED` · `POLICY_SUPPRESSED`

Never map timeout / unknown / unavailable → success.

---

## 28. Versioning

Responses must carry: `contract_version`, `catalog_version`, `pricebook_version`, `promotion_version`, `communication_version` as applicable — enough to reconstruct which authority versions were used.

Suggested document version: `eko-commercial-comms-contract-1`.

---

## 29. Security

Retain: TrustedContext, `client_number`, ownership checks, least privilege, no cookie reuse, no OV scraping, no session bypass, no credential exposure.

Commercial authority authenticates Eko via **scoped service credentials** (≠ BillTrack RO).

Communication authority separates: author · reviewer · approver · executor.

---

## 30. Current availability (from 2.4A)

| Capability | Status |
|---|---|
| Sellable catalog | NOT_FOUND |
| Pricebook | NOT_FOUND |
| Promotion authority | NOT_FOUND |
| Eligibility engine | NOT_FOUND |
| Commercial WRITE API | NOT_FOUND |
| Order API / status | NOT_FOUND |
| Installation order | NOT_FOUND / UNAVAILABLE |
| Communication management authority | NOT_FOUND |
| Inventory READ (“qué tengo”) | READY (READ_MODEL) |
| Alta / plan change / cancel | HANDOFF_ONLY |
| service_add distinct path | UNAVAILABLE |

**COMMERCIAL EFFECT_READY = NO**  
**MANAGED_COMMUNICATION_EFFECT_READY = NO**

---

## 31. Compatibility with existing systems

| System | Classification |
|---|---|
| BillTrack | READ ONLY / billing + padrón |
| api_service | READ MODEL / inventory |
| OV | NAVIGATION / HANDOFF |
| JSAT | HANDOFF / EXTERNAL |
| Estate | OPERATIONS / SUPPORT |
| Proactive 2.3 | EVENT-DRIVEN NOTIFICATION |
| CASI | AUTHORITY CONTROL |

None reinterpreted as commercial WRITE SoT without new evidence.

---

## 32. Activation gates

### Before any commercial EFFECT

1. BSS/CRM authoritative source  
2. Commercial WRITE API  
3. Product catalog (sellable)  
4. Pricebook  
5. Promotion authority  
6. Eligibility engine  
7. Order API  
8. Order status API  
9. Post-write verification  
10. AuthZ distinct from RO  
11. Idempotency contract agreed with authority  
12. Installation/work-order contract when applicable  

### Before Managed Communications EFFECT

1. Communication authority  
2. Campaign/content model  
3. Audience model  
4. Approval workflow  
5. Scheduling model  
6. Channel policy  
7. Dedup/frequency model  
8. Delivery adapter (reuse 2.3 delivery where safe)  
9. Audit model  
10. Authorization model (author/reviewer/approver/executor)  

Until gates pass: adapters remain **NOT ACTIVE**; handoff/honest unavailable remain.

---

## 33. Explicit non-goals (2.4B)

No runtime · no API · no migrations · no external calls · no notifications · no commercial writes · no mobile · no Billing/CASI/SM/Proactive changes · no EFFECT · no fake catalog/prices/promos.

---

## Document control

| Field | Value |
|---|---|
| Document id | `eko-2.4b-commercial-offers-managed-communications-contract` |
| Contract version | `eko-commercial-comms-contract-1` |
| Code modified | **None** |
| Adapters | CommercialAdapter / ManagedCommunicationAdapter = **NOT ACTIVE** |
