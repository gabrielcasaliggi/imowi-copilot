# EKO 2.2H — COMMERCIAL ADAPTER BOUNDARY

**Status:** FUTURE CONTRACT / NOT ACTIVE  
**Phase:** Architectural boundary preparation  
**Runtime impact:** NONE — documentation only; not imported by application code.  
**Depends on:** [EKO 2.2G — Commercial Authority & Integration Contract](./EKO-2.2G-COMMERCIAL-AUTHORITY-INTEGRATION-CONTRACT.md)

> **No inventar backend.** Mientras `EXTERNAL DEPENDENCY — NOT AVAILABLE IN WORKSPACE`, las operaciones comerciales permanecen `HANDOFF_ONLY` / `UNAVAILABLE`.

Este documento **no** repite el contrato de datos de 2.2G. Define **dónde** se enchufa el futuro adapter en la arquitectura existente de Eko y **qué debe cumplirse** antes de activarlo.

---

## 1. Purpose

Preparar la frontera técnica para un futuro `CommercialAdapter` real **sin**:

- implementar integración comercial
- registrar Runtime Actions comerciales
- inventar mocks/APIs/credenciales
- habilitar EFFECT
- cambiar comportamiento productivo

Eko debe poder recibir el adapter más adelante **sin rediseñar** CASI, ConversationState, Policy, Conversation Motor, ownership, confirmation, audit, handoff ni Runtime.

---

## 2. Current State

| Item | Estado |
|---|---|
| BSS/CRM autoritativo accesible | NOT FOUND |
| API WRITE comercial | NOT FOUND |
| Catálogo / pricebook autoritativo | NOT FOUND |
| Eligibility engine | NOT FOUND |
| Status API transaccional | NOT FOUND |
| Idempotencia comercial real | NOT FOUND |
| `service_high` | HANDOFF_ONLY (playbook / humano) |
| `service_add` | UNAVAILABLE |
| `service_plan_change` | HANDOFF_ONLY |
| `service_cancel` | HANDOFF_ONLY |
| Runtime registry | Sin actions `service_high` / `add` / `plan_change` / `cancel` |
| Coverage EXECUTED_BY_RUNTIME comercial | NO |

**Comportamiento productivo:** sin cambios respecto a 2.2F/G.

---

## 3. Future Architecture (plug points)

```text
USER
  ↓
LLM / interpreter          → ActionProposal (allowlist + sanitize)
  ↓
ConversationState          → journey + selected_service_ref + eko_action.*
  ↓
Policy                     → evaluate_policy(ActionRequest, TrustedContext)
  ↓
Conversation Motor         → journeys / bridge; confirmation trusted
  ↓
Runtime ActionSpec         → [FUTURE] commercial_* executor
  ↓
CommercialAdapter          → [FUTURE / NOT ACTIVE] integration only
  ↓
AUTHORITATIVE COMMERCIAL SYSTEM   → EXTERNAL
  ↓
Verification (READ / status API)
  ↓
ConversationState + Deterministic Renderer
```

**Separación obligatoria:**

| Stage | Not equal to |
|---|---|
| USER INTENT | AUTHORIZED REQUEST |
| PROPOSED OPERATION | EXTERNAL EXECUTION |
| EXTERNAL ACCEPTED | VERIFIED COMPLETED |

---

## 4. Adapter Boundary (placement)

### 4.1 Where it should live (conceptual)

| Candidate | Verdict |
|---|---|
| `app/domain/domain_adapter.py` | **NO** — conversation lifecycle only; not BSS |
| `app/services/eko_context.py` | **NO** — Context Adapter = READ facts for N1 |
| Readers (`eko_invoice_reader`, portal_*, billtrack) | **NO** — READ models; not transactional |
| New module under `app/services/` (e.g. `eko_commercial_adapter.py`) | **YES (future)** — called **only** from Runtime executor |
| Direct call from LLM / journeys / Policy | **NEVER** |

El adapter es el **mecanismo de integración**, no la autoridad. La autoridad es el sistema comercial externo.

### 4.2 Existing patterns to reuse (not reinvent)

| Pattern | Location | Reuse for commercial |
|---|---|---|
| `TrustedContext` | `eko_action_runtime` | Ownership + confirmation flags + `correlation_id` |
| `ActionRequest` / `ActionResult` | same | Envelope in/out of Runtime |
| `ActionSpec` + `_REGISTRY` | same | Future registration **only** after activation gate |
| `sanitize_parameters` / `_UNTRUSTED_PARAM_KEYS` | same | Strip LLM ownership / ids |
| `evaluate_policy` | same | Pre-adapter gate |
| `confirmation_state_for` + `resolve_user_confirmation` | runtime + `eko_action_bridge` | Explicit confirm before EFFECT |
| `set_action_state` / `eko_action.*` | Conversation State | Pending confirm, last status |
| `ServiceRef` / `selected_service_ref` | `eko_service_selection` (2.2B) | Service identity |
| `effective_execution_path` XOR | `eko_action_coverage` | Runtime XOR Legacy |
| `_ticket_via_runtime_o_legacy` | `canal_abonado` | Pattern for exclusive path (do not dual-fire) |

**Convention:** dataclasses (no Pydantic required for this boundary). Prefer extending `ActionResult.data` with commercial fields over inventing a parallel type system until activation.

### 4.3 Inactive safety

Until activation:

- No module imported by Runtime
- No `register_action` for commercial ops
- No env URLs / credentials / `enabled=true`
- Conceptual constant only (documentation): `COMMERCIAL_INTEGRATION = NOT_AVAILABLE`

Código abstracto **no** se añade en 2.2H: 2.2G + este doc bastan; un stub Python aumentaría riesgo de import accidental sin valor operativo.

---

## 5. Request Boundary

Maps to future payload assembled **after** Policy + ownership + confirmation (see 2.2G §6).

Reuse Runtime shapes:

```text
ActionRequest(
  action = "service_plan_change" | …   # only when registered post-gate
  parameters = { … sanitized … }
  source = "decision" | "playbook" | "llm_proposal"
)
+ TrustedContext(abonado, confirmation_*, correlation_id, ctx)
```

Authorized commercial fields (conceptual; authority-validated product/plan IDs, not raw LLM strings):

| Field | Source |
|---|---|
| `operation` | Mapped intent (`high` / `add` / `plan_change` / `cancel`) |
| `client_number` | TrustedContext / abonado **only** |
| `selected_service_ref` | ConversationState (2.2B) |
| `requested_product` / `requested_plan` | External catalog resolution |
| `requested_service_type` | Catalog / ref |
| `confirmation` | Trusted confirmation state |
| `idempotency_key` | Eko-generated per confirmed episode |
| `correlation_id` | TrustedContext / journey |
| `channel` | TrustedContext |
| `contract_version` | e.g. `eko-commercial-1` (2.2G) |

Adapter **rejects** any request that supplies `client_number` / ownership from LLM params.

---

## 6. Result Boundary

Prefer extending existing `ActionResult`:

| Field | Mapping |
|---|---|
| `status` | Existing `ActionStatus` + commercial detail in `data` |
| `reason_code` | Existing |
| `correlation_id` | Existing |
| `execution_path` | `"runtime"` only when adapter path used |
| `data.commercial_status` | Conceptual: SUBMITTED / ACCEPTED / PENDING / COMPLETED / … |
| `data.external_transaction_id` | From external system |
| `data.idempotency_key` | Echo of Eko key |
| `data.verification_required` | bool |
| `data.retryability` | bool / enum |
| `data.source` | External system id (when known) |
| `data.contract_version` | Echo |

Commercial lifecycle statuses (conceptual; detail in 2.2G §11):  
`NEEDS_INPUT` · `NEEDS_CONFIRMATION` · `NOT_ELIGIBLE` · `READY` · `SUBMITTED` · `ACCEPTED` · `PENDING` · `COMPLETED` · `FAILED` · `VERIFICATION_REQUIRED` · `VERIFICATION_FAILED` · `HANDOFF_REQUIRED`

**Invariants:** `ACCEPTED ≠ COMPLETED`; `UNKNOWN ↛ COMPLETED`.

---

## 7. Ownership Boundary

Unchanged from CASI / 2.2B:

- `client_number` ← TrustedContext / abonado backend only
- `selected_service_ref.client_number` must match trusted CN or **DENIED** before any future EFFECT
- Adapter must not accept ownership from `ActionRequest.parameters` if those keys were LLM-sourced (`sanitize_parameters` already strips authority keys)
- Foreign service → DENY; never call external WRITE

---

## 8. Policy Boundary

```text
ActionProposal → Policy → Conversation Motor → (confirm) → Runtime → Adapter
```

**Forbidden:** `ActionProposal → Adapter`, `LLM → Adapter`.

| Validated by Eko (Policy / Motor / Runtime) | Validated by external commercial system |
|---|---|
| Action registered + allowlist | Authoritative catalog / product / plan |
| Abonado present | Price / currency |
| Ownership / ServiceRef match | Eligibility / availability |
| Confirmation received for RISK EFFECT | Contractual constraints |
| Idempotency class gates | Execution outcome |
| Channel / capability flags | Transaction id / status |

While integration is NOT_AVAILABLE, Policy must never ALLOW a commercial EFFECT path (today: actions not registered → `unknown_action` DENY).

---

## 9. Confirmation Boundary

Reuse existing machinery; do not invent a parallel commercial confirm store.

| Signal | Meaning |
|---|---|
| `eko_action.status == confirmation_pending` + matching `action` | Awaiting user |
| `TrustedContext.confirmation_received` | Accepted for **that** pending action |
| `confirmation_rejected` | Abort |
| `ActionSpec.confirmation_required = True` | Mandatory for all future commercial EFFECTS |

**Anti-reuse:** confirmation is bound to `(action, idempotency_key or pending payload fingerprint)`. Changing operation / product / service invalidates prior confirm (clear `confirmation_pending` and require a new summary). Do not implement commercial confirm persistence in 2.2H.

---

## 10. Idempotency

| Key | Generated by | When | Stored (conceptual) | Retry / timeout |
|---|---|---|---|---|
| `idempotency_key` | **Eko** | On entering READY / first submit | Conversation State `eko_action` | Same key on retry; no second WRITE semantics |
| `correlation_id` | **Eko** | Request / journey | TrustedContext + logs | Observability only |
| `external_transaction_id` | **External** | On accept/submit | Conversation State after response | Poll / verify by this id |

No commercial persistence or simulated idempotency in 2.2H. Ticket idempotency ≠ commercial idempotency.

---

## 11. Verification

Conceptual second stage after `execute`:

```text
Adapter.execute → External Result → Adapter.verify (or status READ) → Verified Result
```

- Prefer authoritative status API (EXTERNAL DEPENDENCY)
- Optional secondary: re-READ `api_service` **only if** Ecolan confirms mirror + lag
- Verification failure → never claim COMPLETED; prefer `VERIFICATION_FAILED` / `HANDOFF_REQUIRED`

Not implemented in 2.2H.

---

## 12. Error Boundary

Map external failures into `ActionResult.status` + `reason_code` + `data.retryability` (see 2.2G §13). Categories: invalid request, unauthorized, not found, not eligible, unavailable product, conflict, duplicate, pending, timeout, external failure, verification failure, unknown.

**Never** map exception / timeout / unknown → success.

---

## 13. Handoff

While backend missing, keep current HANDOFF_ONLY / playbook human paths.

Future adapter may return `HANDOFF_REQUIRED` when:

- authority unavailable / down
- eligibility unknown / REQUIRES_HUMAN
- result not verifiable
- installation required (2.2D still UNAVAILABLE)
- unrecoverable external error

Handoff payload fields: see 2.2G §15. No new handoff infrastructure in 2.2H.

---

## 14. Audit

When integration exists, audit (no PII) should separate:

| Event | What |
|---|---|
| proposal | LLM/decision proposed action |
| authorization | Policy verdict |
| confirmation | User confirm/reject |
| submission | Adapter call with idempotency_key |
| external_acceptance | external_transaction_id + ACCEPTED/REJECTED |
| completion | Authority COMPLETED claim |
| verification | Verified / failed |
| failure | reason_code |
| handoff | handoff_reason |

Reuse `ActionResult.to_log` pattern. Do not add production commercial audit events until infrastructure exists.

---

## 15. CASI Interaction

| Layer | Role |
|---|---|
| LLM | Propose / draft only |
| ConversationState | Hold selection, pending confirm, keys |
| Policy + Motor | In-Eko authority to proceed |
| Runtime | Sole dispatch (XOR Legacy) |
| CommercialAdapter | Integration pipe |
| External system | Commercial authority |
| Verification | Facts after effect |

LLM must never: set ownership, invent price/eligibility/tx id, mark COMPLETED, skip confirm, or call the adapter.

---

## 16. Runtime XOR Legacy

When a commercial EFFECT is eventually enabled:

- Register Runtime action + wire **one** path only
- `effective_execution_path` → `"runtime"` for that action
- Remove / disable Legacy commercial write for the same `idempotency_key`
- Never Runtime + Legacy dual execution

Today there is **no** commercial EFFECT path on either side (Legacy = handoff/playbook text only).

---

## 17. Capability Activation Gate

**Do not** set for commercial ops until gate passes:

- EFFECT_READY / ACTION_RUNTIME_ENABLED for those names
- Coverage `EXECUTED_BY_RUNTIME`
- Registry entries for `service_high` / `service_add` / `service_plan_change` / `service_cancel`

Remain:

| Capability | Status |
|---|---|
| `service_high` | HANDOFF_ONLY |
| `service_add` | UNAVAILABLE |
| `service_plan_change` | HANDOFF_ONLY |
| `service_cancel` | HANDOFF_ONLY |

Future documentary state only: `COMMERCIAL_EFFECT_CANDIDATE` (not a live enum in code).

---

## 18. External Dependencies

`EXTERNAL DEPENDENCY — NOT AVAILABLE IN WORKSPACE` — unchanged from 2.2G §19–20.

---

## 19. Activation Prerequisites (FUTURE → EFFECT ENABLED)

All must be true (evidence, not aspiration):

- [ ] Authoritative BSS/CRM identified  
- [ ] Write API documented  
- [ ] Authentication available  
- [ ] Catalog authoritative  
- [ ] Eligibility authoritative  
- [ ] Confirmation mechanism defined (reuse Trusted + bind to idempotency)  
- [ ] Idempotency mechanism available on external API  
- [ ] Transaction status available  
- [ ] Verification source available  
- [ ] Ownership mapping validated (`client_number` ↔ external account)  
- [ ] Failure/error contract documented  
- [ ] Audit requirements implemented  
- [ ] Production credentials configured (ops; never in git)  
- [ ] E2E against real **non-production** environment  
- [ ] CASI audit PASS  
- [ ] Policy audit PASS  
- [ ] Runtime XOR Legacy audit PASS  
- [ ] Explicit activation approval  

Until then: `FUTURE CONTRACT / NOT ACTIVE`.

---

## 20. Explicit Non-Goals (2.2H)

- No commercial backend / mock / fake API  
- No network or DB commercial calls  
- No EFFECT / Runtime registration  
- No capability activation  
- No env flags, URLs, or credentials  
- No Billing 2.1 changes  
- No CASI redesign  
- No 2.2I implementation  
- No simulated success  

---

## Document control

| Field | Value |
|---|---|
| Document id | `eko-2.2h-commercial-adapter-boundary` |
| Contract version (future) | `eko-commercial-1` (from 2.2G) |
| Active in runtime | **NO** |
| EFFECT enabled | **NO** |
| Code artifact | **None** (docs-only by design) |
| Prior phase | 2.2G PASS |
