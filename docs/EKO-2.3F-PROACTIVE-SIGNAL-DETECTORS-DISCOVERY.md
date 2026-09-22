# EKO 2.3F — PROACTIVE SIGNAL DETECTORS DISCOVERY

**Status:** DISCOVERY ONLY — no runtime / notification / detector implementation  
**Depends on:** 2.3A–2.3E PASS  
**Runtime impact:** NONE  

Principio: **STATE ≠ EVENT**. Timestamp ≠ identity. Row ≠ authority. LLM ≠ source.

---

## 1. Purpose

Mapear qué señales proactivas adicionales podrían generarse de forma **determinística** a partir de fuentes existentes, sin inventar detectors, schedulers ni backends.

Producción hoy (única ruta):

```text
OUTAGE CRUD → EVENT → POLICY → DEDUP → DELIVERY → Expo
```

Eventos enabled: `outage.started` | `outage.material_update` | `outage.resolved`.

---

## 2. Outages — READY / ALREADY IMPLEMENTED

| Aspect | Evidence |
|---|---|
| Source of truth | Estate `NetworkOutage` (ops CRUD) |
| Transitions | create → activo; material PATCH; resolve → resuelto |
| Identity | `outage_id` (+ material body fingerprint) |
| Timestamps | `started_at`, `updated_at`, `resolved_at` |
| Ownership | NAS → `abonado_afectado_por_nas` → PortalDevice |
| Dedup | Conditional claims `push_declared_at` / `push_resolved_at` / `push_material_fingerprint` |
| Detector | Existing write path (API outages) |
| Status | **READY / ALREADY IMPLEMENTED** |

No changes in 2.3F.

---

## 3. Billing

### Sources inspected

| Source | Role in workspace |
|---|---|
| `public.api_invoice` via `eko_invoice_reader` | TRUSTED READ FC headers: `id`, `number`, `amount`, `date`, `state`, `account_number` |
| `api_person.billing_balance` via `billtrack` | TRUSTED READ snapshot → `deuda` / estate `deuda_monto` |
| `api_billed_concept` | Explicitly **not** used for amount (reader contract) |
| Due date / period / currency | **Absent** from reader (`due_date=None`) |
| Payment history capability | `can_answer_payment_history=False`; journey `honest_unavailable` |

### Candidate signals

| Event | Classification | Why |
|---|---|---|
| invoice issued / “new invoice” | **STATE_ONLY** / **PARTIAL** | Rows + `date` exist; `date` ≠ proven “just issued”; no snapshot/store of prior invoice set; **NO_DETECTOR** |
| invoice status changed | **PARTIAL** | `state` field readable; no persisted previous status / transition log in Eko |
| invoice cancelled | **PARTIAL** | Would need state semantics + prior; not proven |
| debt appeared / changed / cleared | **STATE_ONLY** | Current `billing_balance` only; no authoritative debt event stream |
| due_date approaching | **UNAVAILABLE** | No `due_date` in accessible invoice contract |

**Do not treat** `api_invoice.date` as `occurred_at` for proactive “invoice just issued”.

---

## 4. Payments

| Evidence | Finding |
|---|---|
| BillTrack payment / receipt tables as wired Eko readers | **NOT_FOUND** in application code |
| `tools/billtrack_ro_probe.py` | Schema probe may find payment-like tables in live BillTrack — **not** integrated as readers; probe itself says do **not** infer payment from `billing_balance` |
| Fiserv / QR | Context hints `pago_qr_reciente` / “integrar Fiserv”; OV NAV / plantillas — not payment SoT |
| User “ya pagué” | Conversation only — not authority |

| Event | Classification |
|---|---|
| payment initiated / accepted / completed / failed / reversed | **UNAVAILABLE** (or **EXTERNAL_DEPENDENCY** if tables exist in BillTrack but unused) |
| balance→0 as payment confirmed | **UNAVAILABLE** — forbidden inference |

No payment transition detector exists. No Eko payment history API.

---

## 5. Tickets

### Sources

| Source | Evidence |
|---|---|
| `tickets_estate` | AUTHORITATIVE estate row: `estado`, `created_at`, `updated_at`, ownership via org + channel/abonado links |
| `ticket_events` | Append-only timeline: `id`, `tipo`, `estado`, `visible_cliente`, `created_at` |
| Writers | `add_ticket_event` from `create_ticket`, ticket API patches, seguimiento, KB, CSAT, learning_loop |
| Customer push | **None** today (inbox push is conversation-scoped) |

### Candidates

| Event | Transition evidence | Status |
|---|---|---|
| `ticket.created` | `create_ticket` + event append | **READY_FOR_DETECTOR** |
| `ticket.updated` / status transitions | `add_ticket_event` on changes; `estado` on event | **READY_FOR_DETECTOR** (prefer event row, not poll of `Ticket.estado`) |
| `ticket.resolved` / `closed` / `reopened` | Status transitions + events when callers append | **READY_FOR_DETECTOR** if event written on transition |
| `ticket.assigned` / claimed | `asignado_a` + possible event | **PARTIAL** — confirm every assign path emits event |
| SLA breached | `sla_breached_at` set in `refresh_tickets_sla` / `ensure_ticket_sla` | **READY_FOR_DETECTOR** for **ops email** path already; **customer proactive** = product decision + ownership |

**Important:** `Ticket.estado` alone without event/history ≠ proven transition for proactive. Hook **existing write path** (`add_ticket_event` / status API), not a scheduler.

Ownership: portal tickets bound to authenticated abonado; proactive must use same bind — never phone alone.

---

## 6. Connectivity

| Source | Nature |
|---|---|
| Portal connectivity / PPPoE / Radius / BCM / UISP | On-demand TRUSTED READ / DERIVED diagnosis |
| Previous probe / last_known / transition store | **NOT_FOUND** (`previous_state`, probe history, etc.) |
| Outages | Separate AUTHORITATIVE mass-incident path (already proactive) |

| Event | Status |
|---|---|
| connectivity_lost / restored, session_*, quality_* | **STATE_ONLY** / **NO_DETECTOR** |

“Session is down now” ≠ “session just went down”. Creating hysteresis/threshold store would be new infra — out of 2.3F.

Outage precedence remains the customer-safe mass-incident path.

---

## 7. Service lifecycle

| Source | Finding (2.2I / billtrack) |
|---|---|
| `api_service` | READ model; `state`, `last_state_date` SELECT |
| Writer of `api_service` | **UNKNOWN / NOT_FOUND** in workspace |
| Transition store / snapshot | **NOT_FOUND** |
| Commercial alta/baja/cambio | HANDOFF_ONLY / UNAVAILABLE |

| Event | Status |
|---|---|
| service.activated / deactivated / suspended / plan_changed / added / removed | **UNAVAILABLE** / **NO_AUTHORITATIVE_TRANSITION_SOURCE** |

`active=true` / `state=Habilitado` = STATE_ONLY, not EVENT.

---

## 8. Installation

| Candidate | Classification |
|---|---|
| Structured installation / work order / agenda | **UNAVAILABLE** (2.2D confirmed; re-verified) |
| `turno_campo`, tickets, handoff, playbooks, KB | HANDOFF / DOCUMENTATION — not installation SoT |

---

## 9. Commercial

| Item | Status |
|---|---|
| BSS/CRM WRITE, pricebook, eligibility API | **EXTERNAL_DEPENDENCY — NOT AVAILABLE IN WORKSPACE** (2.2F/I) |
| Labels / `product_code` in `api_service` | Informational only |
| OV / JSAT | NAVIGATION / HANDOFF |
| Future CommercialAdapter | NOT ACTIVE |

No commercial proactive transaction events.

---

## 10. Other existing customer-adjacent sources

| Source | Classification | Notes |
|---|---|---|
| PortalDevice register/unregister | **READY_FOR_DETECTOR** (CRUD) | Usually INTERNAL / low customer value for “push about push” |
| Inbox agent → `notificar_conversacion_app` | **READY / IMPLEMENTED** (reactive channel) | Not outage-style domain expansion |
| `TicketNotification` / CSAT / SLA email | Ops / console | Not customer Expo product unless redesigned |
| AuditEvent | Internal | Not customer-facing |
| JSC line seed | DEMO | Not authority |

---

## 11. Readiness matrix

| Domain | Event | Authority | Transition | Identity | Timestamp | Ownership | Dedup | Detector | Status |
|---|---|---|---|---|---|---|---|---|---|
| Outage | started / material_update / resolved | AUTHORITATIVE estate | Yes (CRUD) | outage_id (+ fp) | started/updated/resolved | NAS→abonado→device | Claims | Write path | **READY** |
| Billing | invoice issued | TRUSTED READ | Not proven | invoice id | `date` ≠ event | CN | Would need store | No | **STATE_ONLY/PARTIAL** |
| Billing | debt appeared | TRUSTED READ snapshot | No | — | — | CN | — | No | **STATE_ONLY** |
| Billing | due_date approaching | — | — | — | — | — | — | — | **UNAVAILABLE** |
| Payment | * | — | — | — | — | — | — | — | **UNAVAILABLE** |
| Ticket | created / updated / resolved / closed | AUTHORITATIVE estate | Yes via TicketEvent writers | event_id / ticket+tipo | event.created_at | Ticket↔abonado | event_id | Write path hook | **READY_FOR_DETECTOR** |
| Ticket | assigned | Estate | Partial | — | updated_at weak | Ticket | — | Incomplete | **PARTIAL** |
| Ticket | SLA breached | Estate | Yes in SLA refresh | ticket_id + breached_at | sla_breached_at | Ticket (ops today) | ticket+breach | Exists for email | **READY_FOR_DETECTOR** (ops); customer TBD |
| Connectivity | lost/restored/… | Probe READ | No history | — | probe time only | service_ref | — | No | **STATE_ONLY** |
| Service | activated/… | api_service READ | Writer unknown | — | last_state_date weak | CN | — | No | **UNAVAILABLE** |
| Installation | * | — | — | — | — | — | — | — | **UNAVAILABLE** |
| Commercial | * | — | — | — | — | — | — | — | **EXTERNAL_DEPENDENCY** |
| Device | registered | Estate PortalDevice | CRUD | device_id | created_at | DNI/session | device_id | Write path | **READY_FOR_DETECTOR** (low value) |

---

## 12. Event contract candidates (READY_FOR_DETECTOR only)

Conceptual — **not implemented**.

### `ticket.created` / `ticket.updated` / `ticket.resolved` (customer-visible)

| Field | Value |
|---|---|
| source | `estate.ticket_events` (+ ticket row) |
| source_record | `TicketEvent.id` |
| event_identity | `ticket_event_id` or `ticket_id + tipo + created_at` |
| occurred_at | `TicketEvent.created_at` |
| detected_at | Hook time on `add_ticket_event` |
| ownership_key | Trusted abonado / CN bound to ticket |
| dedup_key | `ticket_event_id` |
| previous/current | `estado` on event / ticket when present |
| authority | AUTHORITATIVE estate |
| gate | `visible_cliente=Sí`; policy + devices |

### `ticket.sla_breached` (ops-first)

| Field | Value |
|---|---|
| source | SLA engine on ticket |
| identity | `ticket_id` + first `sla_breached_at` |
| occurred_at | `sla_breached_at` |
| ownership | Agent notify today; customer push needs product rule |

### PortalDevice registered (optional / INTERNAL)

| Field | Value |
|---|---|
| source | `/portal/devices` POST |
| identity | `PortalDevice.id` / token fingerprint |
| occurred_at | `created_at` |

---

## 13. Ownership findings

Preferred chain unchanged: TrustedContext → CN/abonado → service/ticket/device.  
Suppress if unresolved. Never phone/DNI/LLM alone.

---

## 14. Temporal findings

| Field | Safe use |
|---|---|
| Outage started/resolved_at | Event times |
| TicketEvent.created_at | Transition append time |
| api_invoice.date | Document date — **not** proactive “issued now” without detector+prior |
| Ticket.updated_at | Weak alone |
| Probe request time | Observation only |
| api_service.last_state_date | Insufficient without writer semantics |

---

## 15. Dedup findings

| Domain | Strongest key |
|---|---|
| Outage | Claims / material fp (done) |
| Ticket | `TicketEvent.id` |
| Billing | Would need invoice id + state version store — **missing** |
| Connectivity / service | No transition identity |

Do not use message text as identity except outage material fp (documented limitation).

---

## 16. Detector findings

| Mechanism | Exists? |
|---|---|
| Outage CRUD callback | Yes (production) |
| Ticket `add_ticket_event` / ticket API | Yes — **hookable**, not proactive today |
| SLA breach notify | Yes (email ops) |
| BillTrack change feed / CDC | **No** in Eko |
| Connectivity persistence / poller | **No** |
| Scheduler / queue / event bus for proactive | **Must not invent in this phase** |

---

## 17. Technical grouping (no business ranking)

| Group | Items |
|---|---|
| **A. READY** | Outage lifecycle (implemented) |
| **B. READY_FOR_DETECTOR** | TicketEvent-based ticket lifecycle (customer-visible); SLA breach (ops); PortalDevice register (low value) |
| **C. PARTIAL** | Invoice status fields; ticket assign paths; billing without prior snapshot |
| **D. STATE_ONLY** | Debt balance; connectivity probes; service active flags |
| **E. HISTORY_WITHOUT_DETECTOR** | Invoice list history without change detector; possible BillTrack payment tables not wired |
| **F. UNAVAILABLE** | due_date, payment lifecycle in Eko, installation, service commercial transitions |
| **G. EXTERNAL_DEPENDENCY** | Commercial SoT / api_service writer / Fiserv payment SoT |

---

## 18. Explicit non-goals (2.3F)

No code, detectors, schedulers, queues, event buses, notifications, mobile, Billing/CASI/SM/2.3D/2.3E changes.

---

## Document control

| Field | Value |
|---|---|
| Document id | `eko-2.3f-proactive-signal-detectors-discovery` |
| Code modified | **None** |
| Next phase (outside this brief) | Only if product picks a **READY_FOR_DETECTOR** item (likely tickets via write-path hook) |
