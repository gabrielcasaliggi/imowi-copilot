# EKO 2.2G — COMMERCIAL AUTHORITY & INTEGRATION CONTRACT

**Status:** FUTURE CONTRACT / NOT ACTIVE  
**Phase:** Discovery + contract design only  
**Runtime impact:** NONE — this document is not imported by application code.

**Sources of truth (prior phases):**

| Phase | Gate | Relevant conclusion |
|---|---|---|
| 2.2A | PASS | Commercial catalog READ (`service_list`) |
| 2.2B | PASS | `selected_service_ref` authority for service identity |
| 2.2C | PASS | Bounded diagnostics for fixed Internet |
| 2.2D | PASS | Installation factual status = UNAVAILABLE |
| 2.2E | PASS | All commercial EFFECTS = HANDOFF_ONLY / UNAVAILABLE |
| 2.2F | PASS | No accessible commercial WRITE authority in workspace |

---

## 1. Executive Summary

Eko **must not** become the commercial system of record. Until Ecolan/Batán exposes an authoritative commercial API (CRM/BSS/ERP), Service Management commercial operations remain:

| Capability | Status |
|---|---|
| `service_high` | HANDOFF_ONLY |
| `service_add` | UNAVAILABLE (no distinct path) |
| `service_plan_change` | HANDOFF_ONLY |
| `service_cancel` | HANDOFF_ONLY |

This contract defines the **future** boundary for a `CommercialAdapter` that would sit **after** Policy / confirmation / Runtime and **before** an external authoritative system. It does **not** authorize implementation, registry entries, endpoints, or mocks.

Architecture (unchanged):

```text
LLM interpretation/proposal
  → ConversationState
  → Policy
  → Conversation Motor
  → confirmation (trusted)
  → Runtime (XOR Legacy)
  → CommercialAdapter   [FUTURE — not present]
  → Authoritative commercial system  [EXTERNAL — not in workspace]
  → Verification (READ-back)
  → Deterministic response
```

Rule: **LLM content ≠ authority.**

---

## 2. Evidence Inspected

| Area | Evidence |
|---|---|
| BillTrack | RO Postgres; `billtrack.py` rejects non-SELECT; SECURITY: writes prohibited |
| `api_service` | READ model/padrón; writer origin UNKNOWN in-repo |
| Runtime | No `service_high` / `service_add` / `service_plan_change` / `service_cancel` actions |
| Journeys | `service_catalog`, connectivity, billing, `installation_status` (honest unavailable) |
| Playbooks | `alta_plan`, `baja_servicio` = HANDOFF_HUMANO |
| OV/JSAT | Navigation / session handoff only |
| JSC | Demo READ; not live commercial backend |
| Installation | 2.2D UNAVAILABLE |
| `selected_service_ref` | `service_id`, `login`, `service_type`, `client_number`, `label`, `product`, `active` |
| Confirmation | Exists for `create_ticket` etc.; not for commercial EFFECT (no EFFECT actions) |
| Idempotency commercial | NOT FOUND |

---

## 3. Current Service Management Boundary

**In scope today (implemented):**

- READ commercial catalog → `service_list`
- Deterministic selection → `selected_service_ref`
- Bounded Internet diagnostics
- Honest unavailable installation status
- Handoff paths (contact / ticket / OV NAV)

**Out of scope today (must remain):**

- Any commercial WRITE
- Treating BillTrack as transactional BSS
- Treating labels/`product_code` as authorizing catalog
- Treating `create_ticket` or `open_OV` as commercial EFFECT

---

## 4. Future Commercial Adapter Boundary

```text
┌─────────────────────────────────────────────────────────┐
│ Eko (orchestration)                                     │
│  TrustedContext ownership                               │
│  selected_service_ref                                   │
│  User intent + confirmation                             │
│  Policy ALLOW / DENY / NEEDS_*                          │
│  Idempotency key (Eko-generated)                        │
│  Correlation / audit                                    │
└───────────────────────┬─────────────────────────────────┘
                        │ CommercialRequest (authorized)
                        ▼
┌─────────────────────────────────────────────────────────┐
│ CommercialAdapter  [FUTURE / NOT ACTIVE]                │
│  Maps authorized request → external API                 │
│  Never invents catalog/price/eligibility                │
│  Returns Result + external_transaction_id               │
└───────────────────────┬─────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────┐
│ Authoritative commercial system  [EXTERNAL]             │
│  Catalog · eligibility · price · execute · status       │
└───────────────────────┬─────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────┐
│ Verification                                            │
│  Prefer authoritative status API; optionally re-READ    │
│  BillTrack api_service IF confirmed as eventual mirror  │
└─────────────────────────────────────────────────────────┘
```

The adapter **must not** be registered until the external system is identified, authenticated, and contractually approved.

---

## 5. Operation Matrix

| Operation | Current | Future EFFECT needs | Handoff when |
|---|---|---|---|
| HIGH (`service_high`) | HANDOFF_ONLY | Create account/service order; may need install | Backend missing / eligibility unknown / install blocked |
| ADD (`service_add`) | UNAVAILABLE | Add product to existing account | No distinct op / backend missing |
| PLAN_CHANGE | HANDOFF_ONLY | Change product/plan on `service_id` | No pricebook / not eligible |
| CANCEL | HANDOFF_ONLY | Cancel/deactivate `service_id` | Debt/retention/equipment requires human |

Distinction **HIGH vs ADD** must come from the external system (or explicit product taxonomy). Eko must not invent it.

---

## 6. Request Contract

### 6.1 USER REQUEST (non-authoritative)

May originate from LLM/heuristics; **never** trusted alone:

- Natural-language intent (`high` | `add` | `plan_change` | `cancel`)
- Requested product/plan **labels** as spoken by user
- Channel, free-text reason

### 6.2 AUTHORIZED COMMERCIAL REQUEST (conceptual)

Only assembled after Policy + ownership + (future) eligibility + confirmation:

| Field | Source | Notes |
|---|---|---|
| `operation` | Deterministic mapping from confirmed intent | Enum |
| `client_number` | **TrustedContext only** | Never LLM |
| `selected_service_ref` | 2.2B ConversationState | Required for plan_change/cancel; optional for high |
| `requested_product_ref` | External catalog after resolution | Not raw user string |
| `requested_plan_ref` | External catalog | Same |
| `user_confirmation` | Trusted confirmation state | Explicit |
| `idempotency_key` | Generated by Eko (UUID) | Stable per user intent episode |
| `correlation_id` | Journey / Runtime | Audit |
| `channel` | TrustedContext / conv | |
| `contract_version` | This document version | e.g. `eko-commercial-1` |

### 6.3 Intention ≠ authorization

> “Quiero el plan X” ≠ product exists, is eligible, has price P, or may execute.

---

## 7. Authoritative Catalog Contract

**Informational (today):** `api_service.product` / `product_code` / labels / KB — **not** authorizing.

**Authorizing catalog (future external)** should expose at least:

| Field | Required for EFFECT |
|---|---|
| `product_id` | Yes (stable ID) |
| `product_code` | Preferred |
| `product_name` | Display |
| `plan_id` | Yes when plans exist |
| `plan_name` | Display |
| `service_type` | Yes |
| `price` | Yes if quoted to user before confirm |
| `currency` | Yes with price |
| `billing_frequency` | If applicable |
| `effective_from` / `effective_to` | If returned by authority |
| `availability` | Yes |
| `commercial_constraints` | Opaque structured constraints |

Human names alone are **never** transaction keys.

---

## 8. Eligibility Contract

Future external call (conceptual):

**Input:** `client_number`, optional `selected_service_ref`, `requested_product_ref`, `operation`, channel.

**Output (conceptual):**

| Outcome | Meaning |
|---|---|
| `ELIGIBLE` | May proceed to confirmation / execute |
| `NOT_ELIGIBLE` | Deterministic deny + reason_code |
| `REQUIRES_HUMAN` | Handoff |
| `REQUIRES_INSTALLATION` | Blocked until installation authority exists (2.2D) |
| `UNKNOWN` | Do not execute; handoff or honest unavailable |

Eko does **not** implement eligibility locally from RAG.

---

## 9. Confirmation Model

`confirmation_required = true` for **all** future commercial EFFECTS.

Before confirmation, user-visible summary must include (when known from authority):

- Trusted client identity (non-sensitive presentation)
- Affected `selected_service_ref` (label/product)
- Operation
- Authorized product/plan name
- Price + currency **only if** returned by authority
- Material constraints returned by authority
- Explicit ask for yes/no

Reuse existing patterns (`ActionSpec.confirmation_required`, `resolve_user_confirmation`, TrustedContext flags). Do **not** invent a parallel confirmation store.

`confirmation_token` from external system: optional **only if** the authority issues one; otherwise Eko confirmation + `idempotency_key` suffice.

---

## 10. Idempotency Model

| Key | Generated by | Role |
|---|---|---|
| `idempotency_key` | **Eko** | One key per confirmed commercial intent episode; sent on every retry |
| `correlation_id` | **Eko** | Observability across journey turns |
| `external_transaction_id` | **Commercial system** | Authoritative reference; stored in ConversationState after submit |

Rules:

- Same `idempotency_key` → same logical transaction (no double alta/baja/cambio).
- Do not reuse key across different operations or different product targets.
- Ticket idempotency (`ticket_already_exists`) is **not** commercial idempotency.

---

## 11. Transaction / Result State Model

Recommended conceptual states (names may be adapted when integrating):

| State | Meaning |
|---|---|
| `NOT_REQUESTED` | No commercial intent |
| `NEEDS_INPUT` | Missing selection / product resolution |
| `NEEDS_CONFIRMATION` | Eligibility OK; awaiting user |
| `ELIGIBILITY_UNKNOWN` | Cannot decide; no EFFECT |
| `NOT_ELIGIBLE` | Authority denied |
| `READY` | Confirmed; ready to submit |
| `SUBMITTED` | Sent to external system |
| `ACCEPTED` | External accepted request (may still be async) |
| `REJECTED` | External rejected |
| `PENDING` | External in progress |
| `COMPLETED` | Authority asserts done **and** verification OK |
| `FAILED` | Hard failure |
| `VERIFICATION_REQUIRED` | Accepted/pending; verify outstanding |
| `VERIFICATION_FAILED` | Claimed done but READ-back mismatch |
| `HANDOFF_REQUIRED` | Fall back to human |

**Invariants:**

- `SUBMITTED` ≠ `COMPLETED`
- `ACCEPTED` ≠ `COMPLETED`
- LLM must never set `COMPLETED`

---

## 12. Verification Contract

| Operation | Verification evidence (future) |
|---|---|
| HIGH | New service under trusted `client_number`; product/plan match; status active/pending as defined by authority |
| ADD | Additional service row/id under same ownership |
| PLAN_CHANGE | Same `service_id`; new product/plan from authority |
| CANCEL | Same `service_id`; cancelled/inactive status; effective date if provided |

Preferred verification source: **authoritative status API**.  
Optional secondary: re-READ BillTrack `api_service` **only if** Ecolan confirms it mirrors the writer with known lag.

If verification impossible → `VERIFICATION_FAILED` or `HANDOFF_REQUIRED`, never fake success.

---

## 13. Error Model

| Category | User stance | Retry | Audit | Handoff |
|---|---|---|---|---|
| `INVALID_REQUEST` | Clarify / NEEDS_INPUT | No auto | Yes | Rare |
| `UNAUTHORIZED` | Deny | No | Yes | Possible |
| `NOT_FOUND` | Honest | No | Yes | Possible |
| `NOT_ELIGIBLE` | Explain reason if safe | No | Yes | Optional |
| `PRODUCT_UNAVAILABLE` | Honest | No | Yes | Optional |
| `CONFLICT` | Honest | Careful | Yes | Likely |
| `DUPLICATE` | Treat as idempotent success if same tx | No duplicate write | Yes | No |
| `PENDING` | Inform wait / follow-up | Poll if API | Yes | Optional |
| `EXTERNAL_FAILURE` | Honest | Limited | Yes | Yes |
| `TIMEOUT` | Honest | Idempotent retry | Yes | If exhausted |
| `VERIFICATION_FAILED` | Do not claim done | No silent OK | Yes | Yes |
| `UNKNOWN` | Never success | No | Yes | Yes |

---

## 14. Authority Matrix

| Dato | Eko may propose | Eko may trust | Requires external authority |
|---|---|---|---|
| `client_number` | No | Yes (TrustedContext) | Ownership source |
| `service_id` | No (must validate catalog) | Yes if in trusted catalog for CN | Catalog belonging |
| `login` | No | Yes as tech assoc. of ref | — |
| `service_type` | Heuristic only | From catalog/ref | For EFFECT targeting |
| `product` label | Yes (user/LLM) | No for EFFECT | Authorizing catalog ID |
| `product_code` | No | Only if from RO catalog row | Authorizing ID preferred |
| `plan` | Yes (user/LLM) | No | Authorizing plan_id |
| `price` | No | No | Yes |
| `currency` | No | No | Yes with price |
| `eligibility` | No | No | Yes |
| `availability` | No | No | Yes |
| `contract conditions` | No | No | Yes |
| `installation requirement` | No | No | Yes (+ 2.2D gap) |
| `transaction_id` | No | After external returns | External generates |
| `final status` COMPLETED | No | After verify | External + verify |

---

## 15. Handoff Contract

Remain **HANDOFF_ONLY** when any of:

- Commercial backend missing / inaccessible  
- Authority unknown  
- Catalog non-authoritative  
- Eligibility unverifiable  
- Installation required but 2.2D UNAVAILABLE  
- Result not verifiable  
- External PENDING without query API  
- Unrecoverable external error  
- Policy DENY / human-required eligibility  

**Handoff payload (conceptual, for agents):**

- `operation` requested  
- Trusted `client_number`  
- `selected_service_ref` (if any)  
- User-requested product/plan **as text** (non-authoritative)  
- Confirmation state  
- `handoff_reason` / `reason_code`  
- `correlation_id`  

Do not invent ticket-as-EFFECT semantics.

---

## 16. CASI Authority Boundary

| Layer | May | Must not |
|---|---|---|
| LLM | Interpret, propose, draft | Own CN, price, eligibility, tx id, COMPLETED, skip confirm, call adapter |
| ConversationState | Hold selection, pending confirm, ids | Invent commercial facts |
| Policy | ALLOW/DENY/NEEDS_* | Execute write |
| Conversation Motor | Drive journey | Bypass Policy |
| Runtime | Dispatch registered actions | Dual-path execute |
| CommercialAdapter (future) | Call external only | Local invent catalog/price |
| External system | Authorize & execute | — |
| Verification | Confirm | Mark complete without evidence |

---

## 17. Runtime XOR Legacy

For any future commercial EFFECT:

- Exactly one execution path: **Runtime XOR Legacy**  
- Never Runtime + Legacy for the same `idempotency_key`  
- Prefer Runtime-only when adapter exists  

---

## 18. Versioning Strategy

| Mechanism | Proposal |
|---|---|
| `contract_version` | String, e.g. `eko-commercial-1` on every request/response |
| Negotiation | Adapter advertises supported operations/versions |
| Unknown fields | Ignore on read; never invent meaning |
| Optional fields | Explicit null / absent; never placeholder fake values |
| Breaking changes | New major version; keep HANDOFF until both sides agree |

---

## 19. Missing External Dependencies

`EXTERNAL DEPENDENCY — NOT AVAILABLE IN WORKSPACE`

1. Identity of commercial system of record  
2. WRITE API for high / add / plan_change / cancel  
3. Authorizing product/plan/price catalog  
4. Eligibility API  
5. Auth + permissions for service account  
6. Idempotency + transaction ID semantics  
7. Status/query API for verification  
8. Writer of `api_service` (confirm mirror lag)  
9. Installation/order system if required for HIGH/ADD  

---

## 20. Required Information from Ecolan / Batán

1. Which system creates/modifies/cancels services?  
2. API docs (auth, endpoints, payloads, errors)?  
3. Authorizing catalog + pricebook access?  
4. Eligibility rules/API?  
5. Does BillTrack `api_service` mirror that system? Latency?  
6. Idempotency key support?  
7. Async vs sync completion? Status query?  
8. When must ops remain human-only?  

---

## 21. Recommended Next Phase: 2.2H

**2.2H — External Commercial System Engagement / Access Gate**

Stakeholder-driven: obtain answers in §20, classify system as `ACCESSIBLE_TRANSACTIONAL` or keep HANDOFF.  
Only after access + contract sign-off: design Adapter PoC in a **non-production** path, still without enabling customer-facing EFFECT.

Do **not** start Adapter implementation inside this repo until 2.2H passes with evidence.

---

## Document control

| Field | Value |
|---|---|
| Document id | `eko-2.2g-commercial-authority-contract` |
| Contract version (future) | `eko-commercial-1` (proposed) |
| Active in runtime | **NO** |
| EFFECT enabled | **NO** |
| Last phase evidence | 2.2F PASS |
