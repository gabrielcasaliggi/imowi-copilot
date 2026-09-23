# EKO 2.4A — COMMERCIAL & OFFERS AUTHORITY DISCOVERY

**Status:** PASS WITH FINDING (discovery complete; commercial WRITE SoT absent)  
**Phase type:** DISCOVERY ONLY — no runtime changes  
**Depends on:** Billing 2.1, SM 2.2A–I, Proactive 2.3 closed in prod (`40ea8e2`)  
**External WRITE calls:** NONE  
**CommercialAdapter:** NOT ACTIVATED  

Principio: **LLM content ≠ commercial authority.**  
KB ≠ commercial authority. `api_service` ≠ automáticamente commercial SoT.  
OV navigation ≠ commercial transaction. JSAT handoff ≠ commercial transaction.

---

## 1. Executive summary

Eko **puede** leer de forma factual el inventario de servicios actuales del abonado (BillTrack `api_service` RO → `service_list` / portal).

Eko **no puede** hoy, con autoridad verificable en este workspace:

- exponer un pricebook/catálogo comercial autorizante;
- calcular promociones/elegibilidad contractual;
- ejecutar alta / add / cambio de plan / baja como EFFECT;
- crear ni verificar órdenes comerciales;
- activar `CommercialAdapter`.

Clasificación dominante para operaciones comerciales transaccionales:

**EXTERNAL_DEPENDENCY / HANDOFF_ONLY / NOT_FOUND**

La ausencia de autoridad comercial **no** es fallo de discovery: es el resultado factual.

---

## 2. Systems inventory

| System | Function | Type | READ (Eko) | WRITE (Eko) | Auth | Interface | Commercial SoT? | Classification |
|---|---|---|---|---|---|---|---|---|
| BillTrack Postgres | Padrón person/service/invoice | External DB | SELECT only | **Forbidden** | DB RO user | SQL (`billtrack.py`) | Writer of tables **UNKNOWN** | **READ_MODEL** |
| Data Estate | Tickets, abonados cache, KB, devices | Local Postgres | Yes | Yes (estate) | App JWT | ORM | **No** product SoT | TECHNICAL / ops |
| OV Batán | Oficina virtual abonado | External web/API | Session + deep-links | Session login only | Service user (config) | `ov_batan.py` | **No** | **NAVIGATION_ONLY** |
| JSAT / OV handoff | Auth handoff to OV | External optional | Status | Handoff POST | Config flag | `ov_handoff.py` | **No** | **HANDOFF_ONLY** |
| Playbooks `alta_plan` / `baja_servicio` | N1 conversation | In-app | — | Human path | — | `flujos_abonado.py` | **No** | **HANDOFF_ONLY** |
| KB / RAG comercial | Content | Docs | RAG | — | — | KB | **No** | **DOCUMENTATION_ONLY** |
| Radius / BCM / UISP | Access tech | External | Probe RO | No (policy) | API keys | clients | **No** | **TECHNICAL_ONLY** |
| JSC | Mobile lines | Demo/planned | Demo | Demo seed | — | `jsc/` | **No** | DEMO / DOCUMENTATION |
| CRM/BSS/ERP named clients | — | — | — | — | — | — | — | **NOT_FOUND** |
| Dedicated commercial order API | — | — | — | — | — | — | — | **NOT_FOUND** |
| Salesforce / HubSpot / Odoo / SAP / VTEX clients | — | — | — | — | — | — | — | **NOT_FOUND** |

**No AUTHORITATIVE commercial WRITE system identified in-repo.**

---

## 3. Commercial authority inventory

| Candidate | Authority class | Evidence |
|---|---|---|
| BillTrack `api_person` / `api_service` / `api_invoice` | TRUSTED READ (padrón / billing snapshot) | SELECT-only; RO role |
| Writer of `api_service` | **UNKNOWN / NOT_FOUND** | No INSERT/UPDATE/ETL in workspace (reconfirmed 2.2I + 2.4A) |
| Pricebook / tariff / offer API | **NOT_FOUND** | No tables/clients/queries |
| Eligibility engine | **NOT_FOUND** | — |
| Order management API | **NOT_FOUND** | — |
| OV paths (pagar, talón, …) | NAVIGATION | `ov_batan` PATH_* — payment/nav, not catalog WRITE |
| Playbooks comercial | HANDOFF | `[HANDOFF_HUMANO]` |

---

## 4. Product / plan catalog

### What exists (factual inventory — not authorizing catalog)

From `DEFAULT_SERVICES_SQL` / related joins on `public.api_service`:

| Field | Present | Role |
|---|---|---|
| id, login/identifier | Yes | Service identity |
| label, product, product_code | Yes | **Descriptive** labels |
| service_type_code / label | Yes | Type (INTFO/INTBA/…) |
| state, service_on | Yes | Current state flags |
| locality | Yes | Location hint |
| last_state_date, effective_date_from/to | Yes | Dates on row (STATE, not commercial offer window) |
| price / currency / billing_period | **No** in Eko SELECTs | — |
| availability / geo offer scope | **No** | — |
| eligibility flags | **No** | — |

`service_list` / portal catalog (2.2A): READ projection of **what the customer already has**, not a sellable pricebook.

### Classification

| Question | Answer |
|---|---|
| Authoritative sellable product catalog? | **NOT_FOUND** |
| Authoritative plan catalog for upgrade paths? | **NOT_FOUND** |
| Factual “what I have today”? | **READY** (TRUSTED READ / READ_MODEL) |

---

## 5. Price authority

| Source | Price authority? |
|---|---|
| BillTrack service SELECTs | No price columns used |
| Invoice amount (`api_invoice`) | Billing document amount — **not** plan pricebook |
| KB / prompts / frontend / LLM | **Forbidden** as transactional price |
| Dedicated pricebook | **NOT_FOUND** |

**PRICE AUTHORITY = NOT_FOUND**

---

## 6. Promotion authority

| Search | Result |
|---|---|
| campaign / promotion / discount / bundle tables or APIs in Eko clients | **NOT_FOUND** |
| KB/playbook promotional copy | DOCUMENTATION_ONLY / HANDOFF |

**PROMOTION AUTHORITY = NOT_FOUND** (or DOCUMENTATION_ONLY if RAG mentions offers — not actionable).

---

## 7. Eligibility authority

| Kind | Status |
|---|---|
| Technical eligibility (coverage probes) | Partial tech READ (BCM/UISP/Radius) — **≠ commercial eligibility** |
| Commercial eligibility (can buy/change under contract) | **NOT_FOUND** |
| Debt/antigüedad as commercial gate API | **NOT_FOUND** as eligibility engine (debt snapshot ≠ offer gate) |

---

## 8. Alta / service_add

| Path | Classification |
|---|---|
| Playbook `alta_plan` | **HANDOFF_ONLY** |
| Runtime EFFECT `service_high` / `service_add` | **Not implemented** / HANDOFF or UNAVAILABLE (2.2E/G) |
| Commercial order API | **NOT_FOUND** |
| OV “contratar” as Eko WRITE | **No** — NAVIGATION only |

**EFFECT_READY = NO**

---

## 9. Plan change

| Requirement | Status |
|---|---|
| Origin/destination catalog | NOT_FOUND (labels only) |
| Price / proration | NOT_FOUND |
| Eligibility | NOT_FOUND |
| Write API + order ID | NOT_FOUND |
| Playbook / human | **HANDOFF_ONLY** |

---

## 10. Cancellation

| Path | Classification |
|---|---|
| Playbook `baja_servicio` | **HANDOFF_ONLY** |
| EFFECT `service_cancel` | Not implemented as commercial WRITE |
| Equipment return / debt gates as APIs | NOT_FOUND |

---

## 11. OV / JSAT analysis

| Capability | Classification |
|---|---|
| Session login / check | Limited READ/auth to OV |
| Deep-links (pago, talón, …) | **NAVIGATION_ONLY** |
| JSAT handoff v2 | **HANDOFF** (identity → OV session) when enabled |
| Commercial order CREATE via OV API used by Eko | **NOT_FOUND** |
| Scraping / cookie reuse / SSO inventado | **Forbidden** — not present as solution |

**OV ≠ commercial transaction authority for Eko.**

---

## 12. `api_service` analysis

| Aspect | Classification |
|---|---|
| Eko access | **READ MODEL / PADRÓN** |
| Writer in workspace | **UNKNOWN / NOT_FOUND** |
| Usable for “qué tengo” | Yes (factual) |
| Usable for “qué puedo comprar / a qué precio” | **No** |
| `active=true` / state | STATE — not activation EVENT / not offer |

Reconfirmed: no INSERT/UPDATE/DELETE/ETL targeting `api_service` in this repo; BillTrack client rejects non-SELECT.

---

## 13. Transaction readiness (future EFFECT)

| # | Requirement | Status |
|---|---|---|
| 1 | Authoritative customer identity | PARTIAL (TrustedContext / CN) |
| 2 | Ownership | READY for READ paths |
| 3 | Product/plan catalog (authorizing) | **NOT_FOUND** |
| 4 | Pricebook | **NOT_FOUND** |
| 5 | Eligibility source | **NOT_FOUND** |
| 6 | Write API | **NOT_FOUND** |
| 7 | Auth for WRITE (≠ RO credentials) | **NOT_FOUND** / must not reuse RO |
| 8 | Idempotency | **NOT_FOUND** for commercial |
| 9 | Transaction/order ID | **NOT_FOUND** |
| 10 | Deterministic result states | **NOT_FOUND** |
| 11 | Post-WRITE verification | **NOT_FOUND** |
| 12 | Failure semantics | N/A |
| 13 | Rollback/compensation | **NOT_FOUND** |
| 14 | Installation/order tracking | **UNAVAILABLE** (2.2D) |

**EFFECT_READY = NO** for alta/add/plan_change/cancel/order.

---

## 14. Authentication / authorization

| Layer | Today |
|---|---|
| Customer auth (portal JWT / WA MSISDN trust) | Exists for channel |
| Commercial WRITE authorization | **No** dedicated commercial authz |
| BillTrack RO credentials | Must **not** be reused as WRITE authority |
| OV service user | Session/link only — not proven commercial order scope |

---

## 15. Idempotency

Commercial idempotency key / order correlation from external BSS: **NOT_FOUND**.  
Estate ticket ids / proactive claims are **not** commercial order IDs.

---

## 16. Result states

No commercial order state machine (REQUESTED→COMPLETED…) accessible to Eko.

**COMPLETION_VERIFICATION = NOT_FOUND**  
HTTP 200 on unrelated APIs must not be treated as commercial COMPLETED.

---

## 17. Installation / order dependency

Structured installation / work order / agenda: **UNAVAILABLE** (2.2D reconfirmed).  
Commercial order → field visit chain: **EXTERNAL_DEPENDENCY** / NOT_FOUND.

---

## 18. CASI / authority constraints

Future commercial path (unchanged architecture):

```text
LLM interpretation → ActionProposal → Policy → Motor → Runtime
  → CommercialAdapter [FUTURE]
  → external authoritative system
  → verification READ-back
```

LLM may interpret/propose/draft. LLM must **not**: authorize hire, set price, decide eligibility, pick account, EXECUTE WRITE, declare COMPLETED.

`domain_adapter` / ActionProposal: conversation lifecycle — **not** commercial BSS.

---

## 19. Security findings

| Item | Note |
|---|---|
| BillTrack RO posture | Enforced in code (SELECT-only) |
| Commercial API keys / BSS clients | **NOT_FOUND** as dedicated WRITE clients |
| Config secrets for BillTrack/OV/Radius/… | Exist as config keys — **values not inspected/reproduced** |
| Scraping / browser automation for commerce | Not an approved path; not implemented as commercial adapter |
| Risk if someone treats OV session as WRITE | Misuse risk — document only; no change this phase |

---

## 20. Capability matrix

| Capability | Authority | Read | Write | Eligibility | Price | Tx ID | Verification | Status |
|---|---|---|---|---|---|---|---|---|
| catalog (sellable) | — | — | — | — | — | — | — | **NOT_FOUND** |
| product detail (authorizing) | — | — | — | — | — | — | — | **NOT_FOUND** |
| plan detail (authorizing) | — | — | — | — | — | — | — | **NOT_FOUND** |
| inventory “qué tengo” | BillTrack RO | Yes | No | N/A | N/A | N/A | READ | **READY** (READ_MODEL) |
| price | — | — | — | — | — | — | — | **NOT_FOUND** |
| promotion | — | — | — | — | — | — | — | **NOT_FOUND** |
| eligibility | — | — | — | — | — | — | — | **NOT_FOUND** |
| service_high (alta) | — | — | — | — | — | — | — | **HANDOFF_ONLY** |
| service_add | — | — | — | — | — | — | — | **UNAVAILABLE** / HANDOFF |
| service_plan_change | — | — | — | — | — | — | — | **HANDOFF_ONLY** |
| service_cancel | — | — | — | — | — | — | — | **HANDOFF_ONLY** |
| order creation | — | — | — | — | — | — | — | **NOT_FOUND** |
| order status | — | — | — | — | — | — | — | **NOT_FOUND** |
| commercial verification | — | — | — | — | — | — | — | **NOT_FOUND** |

---

## 21. External dependencies (to unlock EFFECT later)

1. Authoritative commercial WRITE API (CRM/BSS/ERP) with documented ops.  
2. Authorizing catalog + pricebook (+ currency/validity).  
3. Eligibility rules/API.  
4. Order ID + status model + post-write verification.  
5. WRITE credentials scoped separately from BillTrack RO.  
6. Confirm whether `api_service` mirrors that SoT (writer identity + lag).  
7. Installation/order tracking if alta requires field work.

Until then: **CommercialAdapter remains NOT ACTIVE** (2.2G/H contract stands).

---

## 22. Final classification

**STATUS: PASS WITH FINDING**

Discovery completed with coherent evidence. Finding = no commercial WRITE/pricebook/eligibility authority in workspace; transactional commercial EFFECTS remain blocked by design.

---

## Document control

| Field | Value |
|---|---|
| Document id | `eko-2.4a-commercial-offers-authority-discovery` |
| Code modified | **None** |
| Next (outside this brief) | Wait for external SoT / 2.4B+ only when brief authorizes contract/activation criteria — **not** invent offers |
