# EKO 2.3B — PROACTIVE EVENT CONTRACT

**Status:** FUTURE CONTRACT / DOCUMENTATION ONLY — NOT ACTIVE as a runtime layer  
**Depends on:** [EKO 2.3A — Proactive Signals Discovery](./EKO-2.3A-PROACTIVE-SIGNALS-DISCOVERY.md)  
**Runtime impact:** NONE  
**Notifications / writes / schedulers:** NONE  

Principio: **SOURCE OF TRUTH → DETERMINISTIC EVENT**. Nunca **LLM → EVENT**.

---

## 1. Purpose

Definir el **idioma común** de un evento proactivo canónico (`ProactiveEvent`) para que, en fases posteriores, pueda fluir:

```text
SOURCE → EVENT → PROACTIVE POLICY → DEDUP/COOLDOWN → DELIVERY
```

Sin implementar detection engine, policy engine, ledger, queue ni delivery nuevos.

2.3A estableció disponibilidad. 2.3B establece **representación**.

---

## 2. Architecture

```text
AUTHORITATIVE / TRUSTED SOURCE
        ↓
  EVENT DETECTION          [future / partial today]
        ↓
  CANONICAL ProactiveEvent   ← this contract
        ↓
  PROACTIVE POLICY           [future]
        ↓
  DEDUP / COOLDOWN           [partial: outage claims]
        ↓
  DELIVERY                   [exists: Expo for outages]
        ↓
  AUDIT                      [partial: logs + claim timestamps]
```

| Actor | May | Must not |
|---|---|---|
| Source system / ops CRUD | Produce facts | — |
| Detector (future) | Normalize into ProactiveEvent | Invent facts |
| Policy (future) | eligible / suppress / channel | Create events |
| Delivery | Send / retry | Change event_type or ownership |
| LLM (future) | Draft message variants from FACTS | Create event, change ownership, invent `source_event_id`, set severity, mark resolved, claim delivered |

---

## 3. Canonical Event Contract (`ProactiveEvent`)

Conceptual schema (not implemented). Fields are **optional unless marked required for that event_type**.

### 3.1 Identity (required for any normalized event)

| Field | Meaning |
|---|---|
| `event_id` | Stable id of **this** canonical event instance (future ledger). Today: often absent; outage push uses `outage_id` + push `event` string. |
| `event_type` | Namespaced type (see §5) |
| `event_version` | Schema version of this payload (see §6) |
| `source` | Logical source (`estate.network_outages`, `billtrack.api_invoice`, …) |
| `source_event_id` | Id in the source of truth (e.g. `outage_id`, `ticket_id`, `invoice_id`) |

### 3.2 Ownership / scope (optional per type)

| Field | When |
|---|---|
| `client_number` | Account-scoped events |
| `account_number` | Alias only if source uses it (= BillTrack account for invoices) |
| `service_id` | Service-scoped |
| `ticket_id` | Ticket-scoped |
| `outage_id` | Outage-scoped |
| `organizacion_id` | Tenant |
| `customer_scope` | Enum conceptual: `account` \| `service` \| `ticket` \| `outage_fanout` |
| `service_scope` | Optional refinement |

Missing safe ownership → event may exist internally as `NOT_ELIGIBLE_FOR_CUSTOMER` (§20).

### 3.3 Authority

| Field | Values |
|---|---|
| `source_authority` | `AUTHORITATIVE` \| `TRUSTED_READ` \| `DERIVED` \| `UNKNOWN` |

Customer-facing delivery **must not** originate from `UNKNOWN`.  
`DERIVED` requires explicit policy.  
**LLM is not a valid `source_authority`.**

### 3.4 Facts vs message

| Field | Role |
|---|---|
| `facts` | Structured authoritative facts (object) |
| `customer_message` | Representation string for UI/push body |
| `customer_title` | Optional title |

**`customer_message ≠ authority.`** Changing copy does not change the event identity or facts.

### 3.5 Internal metadata (never customer payload)

`internal` / `metadata`: NAS, probe dumps, actor emails, raw rows, credentials — stripped before delivery (see existing `_PAYLOAD_FORBIDDEN` in `app_push.py`).

---

## 4. Identity

**Logical idempotency key (future):**

```text
idempotency_key ≈ hash(source + source_event_id + event_type + event_version [+ material_revision])
```

For outage material updates, a **revision** discriminator is required so updates are not collapsed into `started`/`resolved` (§17).

**Today (outages):** no separate `event_id` ledger; identity ≈ `(outage_id, push_event)` where push_event ∈ `{declared, updated, resolved}`.

---

## 5. Event Type Namespace

**Convention:** `{domain}.{verb}` in `snake_case`, past or stative verb of the **business transition**, not the raw DB status string.

| Canonical `event_type` | Maps from / equals |
|---|---|
| `outage.started` | Push `event=declared` / outage create |
| `outage.material_update` | Push `event=updated` after `outage_update_es_material` |
| `outage.resolved` | Push `event=resolved` |

**EVENT TYPE ≠ SOURCE STATUS**

| Source status | Event type |
|---|---|
| `NetworkOutage.estado = activo` | Does **not** alone emit `outage.started` on every read |
| Transition to created | `outage.started` |
| Material PATCH while activo | `outage.material_update` |
| `estado = resuelto` transition | `outage.resolved` |

Future domains: `billing.*`, `ticket.*`, `connectivity.*`, `service.*` (same convention).

---

## 6. Event Version / Compatibility

| Mechanism | Rule |
|---|---|
| `event_version` | Integer or semver string on payload; propose start at `1` |
| Additive | New optional fields OK without bumping major |
| Breaking | Rename/remove required fields, change meaning of `event_type` → new major / new type |
| Unknown fields | Consumers ignore |
| Producers | Must not invent required facts absent from source |

Not implemented in code.

---

## 7. Temporal Model

| Field | Meaning | If missing |
|---|---|---|
| `occurred_at` | When the business fact happened | `unavailable` — **do not** substitute |
| `detected_at` | When Eko normalized the event | Wall clock of detector |
| `source_created_at` | Source row created | From source or `unavailable` |
| `source_updated_at` | Source row updated | From source or `unavailable` |
| `delivered_at` | Delivery attempt/success time | Delivery layer only |

**Hard rule (Billing):** `api_invoice.date` → may appear in `facts.invoice_date`. It is **not** automatically `occurred_at` for “invoice became available to notify”.

**Outages today:**

| Event | Temporal evidence |
|---|---|
| started | `started_at` / `created_at` on `NetworkOutage` |
| material_update | `updated_at` (+ PATCH time) |
| resolved | `resolved_at` |
| push claim | `push_declared_at` / `push_resolved_at` = **claim/attempt**, not Expo receipt |

---

## 8. Event Status (lifecycle of the *canonical event*)

Conceptual pipeline status (not source outage status):

| `event_status` | Meaning |
|---|---|
| `detected` | Normalized from source |
| `eligible` | Passed policy |
| `suppressed` | Policy/cooldown/quiet hours |
| `queued` | Awaiting delivery |
| `delivered` | Delivery reported success (**optional**; prefer separate delivery status) |
| `failed` | Terminal processing failure |

Prefer keeping business event immutable and tracking delivery separately (§9).

---

## 9. Delivery Status

| Field | Meaning |
|---|---|
| `delivery_status` | `not_attempted` \| `skipped` \| `submitted` \| `succeeded` \| `failed` |
| `channel` | e.g. `app_push` |
| `destination` | Device token id / opaque handle — never raw secret in audit dumps |
| `provider_message_id` | If provider returns one |
| `delivery_error_code` | Provider/HTTP |
| `delivered_at` | Attempt or success timestamp |

**Invariant:** `delivery_status=failed` does **not** undo `outage.resolved` facts.

Existing Expo path returns `{ok, sent, skipped?, …}`; claim columns ≠ delivery confirmation.

---

## 10. Customer-Safe Payload

### Allowed in customer-facing data

- `event_type`, `outage_id` / `ticket_id` / `invoice_id` (as product needs)
- Approved `customer_title` / `customer_message`
- Structured FACTS already classified customer-safe (amount, invoice number, resolved boolean)

### Forbidden (align with `_PAYLOAD_FORBIDDEN` + policy)

- `nas`, `nas_shortname`, `nas_ip`, OLT, serials
- Radius/BCM/UISP internals
- Credentials, tokens, cookies
- Internal comments, `created_by`
- Unverified causes, invented ETA, compensation promises

`customer_message` is representation; `facts` are authority.

---

## 11. Outage Concrete Contract

### Reference pipeline (as implemented today)

```text
POST /outages (ops)
  → NetworkOutage row (estado=activo, mensaje_cliente, started_at, nas_*)
  → notificar_incidente_app (claim push_declared_at)
  → listar_tokens_afectados_por_nas (abonado_afectado_por_nas)
  → Expo push event=declared

PATCH /outages/{id}
  → update fields / regenerate mensaje_cliente
  → if outage_update_es_material(...): notificar_incidente_actualizado_app
  → Expo event=updated  (no cycle claim)

PATCH /outages/{id}/resolve
  → resolve_network_outage
  → notificar_incidente_resuelto_app (claim push_resolved_at)
  → Expo event=resolved
```

| Aspect | Evidence |
|---|---|
| Source | Estate `network_outages` (ops AUTHORITATIVE declare) |
| Trigger | HTTP CRUD by permitted agents |
| Source identity | `outage_id` |
| Customer link | NAS → BillTrack logins → Radius session → Abonado → PortalDevice(DNI) |
| Customer message | `mensaje_cliente` or fixed `BODY_RESOLVED` |
| Dedup | declared/resolved claims; updated unlimited if material |
| Channel | App Push Expo `channelId=eko` |
| Delivery result | `{ok,sent}` + logs; not per-device receipt store |

### 11.1 `outage.started` ↔ `declared`

| Field | Content |
|---|---|
| `event_type` | `outage.started` |
| `source` | `estate.network_outages` |
| `source_event_id` / `outage_id` | UUID |
| `source_authority` | `AUTHORITATIVE` |
| `customer_scope` | `outage_fanout` |
| `occurred_at` | `started_at` |
| `facts` | `{ outage_id, estado: "activo", alcance? }` — no NAS in customer facts |
| `customer_message` | `mensaje_cliente` |
| Materiality | N/A (first declare) |

### 11.2 `outage.material_update` ↔ `updated`

| Field | Content |
|---|---|
| `event_type` | `outage.material_update` |
| `source_event_id` | `outage_id` |
| `facts.materiality` | Evidence booleans from drivers (alcance / ETA validada / mensaje client-facing) — mirrors `outage_update_es_material` |
| `source_updated_at` | `updated_at` |
| `customer_message` | Current `mensaje_cliente` |
| ETA in facts | Only if `eta_validada` is true; never invent |

Do **not** invent technical cause. Do **not** replace materiality with a parallel algorithm in this phase.

### 11.3 `outage.resolved` ↔ `resolved`

| Field | Content |
|---|---|
| `event_type` | `outage.resolved` |
| `occurred_at` | `resolved_at` |
| `facts` | `{ outage_id, estado: "resuelto" }` |
| `customer_message` | Fixed safe body today (`BODY_RESOLVED`) |

---

## 12. Future Billing Contract (NOT ENABLED)

| `event_type` | Availability (2.3A) | Notes |
|---|---|---|
| `billing.invoice_available` | PARTIAL | Needs transition detect; `facts.invoice_date` ≠ `occurred_at` |
| `billing.invoice_status_changed` | PARTIAL | Needs prior status snapshot |
| `billing.debt_detected` | PARTIAL | STATE; needs policy vs spam |
| `billing.payment_confirmed` | **UNAVAILABLE** | No verified payment confirmation source |
| `billing.due_date_approaching` | **UNAVAILABLE** | No `due_date` in invoice reader |
| `billing.payment_failed` | **UNAVAILABLE** | No source |

Identity when enabled: `source=billtrack.api_invoice` (or person balance), `source_event_id=invoice_id` or CN+snapshot, `client_number`/`account_number`, `customer_scope=account`, `source_authority=TRUSTED_READ`.

---

## 13. Future Ticket Contract (NOT ENABLED)

| `event_type` | Notes |
|---|---|
| `ticket.created` | Estate AUTHORITATIVE; needs ownership → CN |
| `ticket.updated` | Prefer `TicketEvent` with `visible_cliente=Sí` |
| `ticket.claimed` | Often INTERNAL unless product wants it |
| `ticket.resolved` | Transition on `estado` |
| `ticket.closed` | Transition |
| `ticket.reopened` | Transition |

Identity: `ticket_id` + verified `client_number`/abonado bind.  
Delivery today: **none** (no ticket Expo path). Inbox push is conversation-scoped, not ticket lifecycle.

---

## 14. Future Connectivity Contract (NOT ENABLED)

| `event_type` | Caveat |
|---|---|
| `connectivity.degraded` | Probes are STATE/PULL today |
| `connectivity.down` | Same |
| `connectivity.recovered` | Requires hysteresis vs flapping |

Must **not** notify per probe. Future policy needs: persistence window, threshold, hysteresis, cooldown.  
`source_authority` likely `DERIVED` from Radius/BCM/UISP TRUSTED_READ.

---

## 15. Future Service Contract (NOT ENABLED)

| `event_type` | Status |
|---|---|
| `service.activated` | NOT_AVAILABLE as EVENT (snapshot ≠ event) |
| `service.deactivated` | NOT_AVAILABLE as EVENT |
| `service.changed` | PARTIAL at best after transition store + known writer |

Writer of `api_service` remains UNKNOWN (2.2I).

---

## 16. Idempotency

| Layer | Key idea |
|---|---|
| Event | `(source, source_event_id, event_type, event_version[, revision])` |
| Outage today | Claim `push_declared_at` / `push_resolved_at` per outage_id |
| Delivery retry | Same event_id; new delivery attempt — **not** new business event |

No ledger table in 2.3B.

---

## 17. Deduplication

| Kind | Purpose |
|---|---|
| **EVENT DEDUP** | Same business fact not double-normalized |
| **NOTIFICATION DEDUP** | Same delivery intent not double-sent |

Outage lifecycle must **not** collapse:

- started ≠ material_update ≠ resolved

Current behavior (preserve; do not replace in 2.3B):

| Push | Dedup |
|---|---|
| declared | Atomic claim `push_declared_at` |
| updated | No cycle claim (multiple material OK) |
| resolved | Atomic claim `push_resolved_at` |

---

## 18. Correlation

Conceptual (future):

| Id | Role |
|---|---|
| `event_id` | This ProactiveEvent |
| `correlation_id` | Journey / conversation / campaign thread |
| `causation_id` | Parent event (e.g. started → material_update) |

Useful for: outage chain; later billing → notify → user opens app.

Not implemented.

---

## 19. Retry Semantics

| Concern | Rule |
|---|---|
| Event persistence | One business event |
| Delivery retry | Re-attempt same event; Expo failure ≠ new `outage.resolved` |
| Claim vs delivery | Today claim can succeed before Expo; crash may retry resolved path by design |

No new retry engine in 2.3B.

---

## 20. Multi-Account

- Never assume `phone → single account`.
- Ownership from TrustedContext / verified BillTrack bind / ticket ownership.
- Outage fanout: per-abonado NAS match; devices per DNI.
- If mapping unsafe → `event_status`/`eligibility = NOT_ELIGIBLE_FOR_CUSTOMER` (internal event may still exist).

---

## 21. Security

Contract forbids embedding: credentials, tokens, cookies, session secrets, raw infra identifiers in customer-facing or casually logged payloads.  
No auth bypass. Delivery uses existing portal device registration.

---

## 22. Audit (future checklist)

Conceptual auditable stages:

1. detected  
2. normalized  
3. eligible  
4. suppressed  
5. submitted (to provider)  
6. delivered  
7. failed  

Today: structured logs for outage push + claim timestamps. No general audit store.

---

## 23. Compatibility / Versioning

See §6. Map legacy push strings:

| Legacy `data.event` | Canonical `event_type` |
|---|---|
| `declared` | `outage.started` |
| `updated` | `outage.material_update` |
| `resolved` | `outage.resolved` |

Until a normalizer exists, producers may keep legacy strings; contract documents the alias.

---

## 24. Current Implementation Matrix

| Event | Contract | Source | Detectable | Ownership | Delivery | Status |
|---|---|---|---|---|---|---|
| `outage.started` | Defined §11.1 | Estate outages | Yes (create) | NAS→abonado→device | Expo | **READY** |
| `outage.material_update` | Defined §11.2 | Estate + materiality | Yes (PATCH) | Same | Expo | **READY** |
| `outage.resolved` | Defined §11.3 | Estate resolve | Yes | Same | Expo | **READY** |
| `billing.invoice_available` | Future §12 | BillTrack invoice | STATE only | CN | None | **PARTIAL** |
| `billing.debt_detected` | Future §12 | billing_balance | STATE only | CN | None | **PARTIAL** |
| `billing.payment_confirmed` | Future §12 | — | No | — | — | **UNAVAILABLE** |
| `billing.due_date_approaching` | Future §12 | — | No | — | — | **UNAVAILABLE** |
| `ticket.updated` | Future §13 | TicketEvent | Yes estate | Ticket bind | None | **PARTIAL** |
| `connectivity.degraded` | Future §14 | Probes | Pull STATE | service_ref | None | **PARTIAL** |
| `connectivity.down` | Future §14 | Probes | Pull STATE | service_ref | None | **PARTIAL** |
| `connectivity.recovered` | Future §14 | Probes | Needs hysteresis | service_ref | None | **PARTIAL** |
| `service.changed` | Future §15 | api_service STATE | No transition store | CN+service_id | None | **UNAVAILABLE** |

READY = contract + source EVENT + ownership path + delivery exist (even if not yet wrapped as `ProactiveEvent` object).

---

## 25. Gaps for 2.3C

Suggested 2.3C (design/implementation gate — **not** started here):

1. Optional **normalizer** that maps outage CRUD → canonical `ProactiveEvent` **without** changing push behavior.  
2. Document policy inputs for eligibility/suppression (quiet hours still unset).  
3. Decide whether ticket/billing get detectors + snapshots before any notify.  
4. Clarify claim vs delivery success in audit model.  
5. Do **not** enable UNAVAILABLE billing/service events.

---

## Explicit Non-Goals (2.3B)

No runtime/code/DB/scheduler/worker/queue/event-bus/capability/Runtime Action changes.  
No push/WA/TG sends. No “improvements” to outages materiality. No invented sources.

---

## Document control

| Field | Value |
|---|---|
| Document id | `eko-2.3b-proactive-event-contract` |
| Schema proposal | `event_version = 1` |
| Active normalizer | **NO** |
| Prior | 2.3A PASS |
