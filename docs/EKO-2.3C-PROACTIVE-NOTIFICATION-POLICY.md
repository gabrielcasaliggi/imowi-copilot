# EKO 2.3C — PROACTIVE NOTIFICATION POLICY

**Status:** FUTURE POLICY CONTRACT / DOCUMENTATION ONLY — NOT ACTIVE as a runtime gate  
**Depends on:**  
- [EKO 2.3A — Proactive Signals Discovery](./EKO-2.3A-PROACTIVE-SIGNALS-DISCOVERY.md)  
- [EKO 2.3B — Proactive Event Contract](./EKO-2.3B-PROACTIVE-EVENT-CONTRACT.md)  

**Runtime impact:** NONE  
**Existing outage push:** UNTOUCHED  
**Notifications sent / DB / schedulers:** NONE  

Principio:

```text
FACT → ProactiveEvent → POLICY DECISION → DELIVERY
```

Nunca: `LLM → NOTIFICATION`.  
Nunca: `STATE → NOTIFICATION` sin transición, evento o regla explícita.

---

## 1. Purpose

Responder:

> Dado un `ProactiveEvent` válido, ¿en qué condiciones Eko está autorizado a intentar comunicarlo al cliente?

Pipeline conceptual:

```text
ProactiveEvent
  → Authority check
  → Ownership check
  → Freshness check
  → Customer relevance
  → Customer eligibility
  → Suppression
  → Dedup / cooldown
  → Channel eligibility
  → DELIVERY_ALLOWED | SUPPRESS | NOT_ELIGIBLE | INVALID
```

La policy **no crea hechos**. Solo decide sobre hechos ya verificados.

---

## 2. Architecture

| Layer | Role |
|---|---|
| Source / Event (2.3A–B) | Facts + identity |
| **This policy** | Authorize or suppress communication |
| Delivery (`app_push`, WA, TG, …) | Attempt send |
| Audit (future) | Record decision + result |

**LLM:** may draft copy from `facts` later; **must not** set `event_type`, ownership, eligibility, severity, delivery auth, or suppression override.

---

## 3. Authority

Evaluate only events with:

| `source_authority` | Policy stance |
|---|---|
| `AUTHORITATIVE` | Eligible for evaluation |
| `TRUSTED_READ` | Only if the signal is **explicitly allowlisted** for proactive use |
| `DERIVED` | Requires an **explicit** named rule (thresholds, hysteresis, etc.) |
| `UNKNOWN` | → `SUPPRESS_REASON = SOURCE_NOT_AUTHORIZED` |
| LLM / free text | → `SOURCE_NOT_AUTHORIZED` (never authority) |

---

## 4. Ownership

### 4.1 Minimum resolved subject

Customer-facing delivery requires a **verified** subject chain. Forbidden: `phone → account` as sole inference.

Preferred chain (as used today for outages / portal):

```text
Verified identity (DNI / TrustedContext / ticket bind)
  → Abonado (estate)
  → client_number / account
  → service / NAS match / ticket ownership
  → PortalDevice (activo, token válido)
```

### 4.2 Fields by event family

| Family | Required for ALLOW | Optional |
|---|---|---|
| Outage | `outage_id` + affected abonado resolution + device(s) | `service_id` per match |
| Billing (future) | `client_number` / `account_number` | `invoice_id` |
| Ticket (future) | `ticket_id` + bind to abonado/CN | — |
| Connectivity (future) | `client_number` + `service_id` / `selected_service_ref` | — |
| Service (future) | `client_number` + `service_id` | — |

If destinatario cannot be resolved safely:

`SUPPRESS_REASON = OWNERSHIP_UNRESOLVED` — **no delivery attempt**.

---

## 5. Event Scope

| Scope | Meaning | Resolution to recipient |
|---|---|---|
| `CUSTOMER` / account | One account | CN → abonado → devices |
| `SERVICE` | One service | service_id under CN → devices of that abonado |
| `TICKET` | One ticket | ticket ownership → abonado → devices |
| `OUTAGE` | Fan-out | `outage_id` + NAS → `abonado_afectado_por_nas` → devices per DNI |

**Critical:** `outage_id` ≠ `customer_id`. Fan-out uses existing affected-subscriber matching; false-negative preferred when NAS evidence missing (current E′1 behavior).

---

## 6. Freshness

| Input | Role |
|---|---|
| `occurred_at` | Business time |
| `detected_at` | Normalization time |
| `source_updated_at` | Source row update |
| `current_time` | Evaluation wall clock |

Conceptual outcomes:

| Result | Meaning |
|---|---|
| `FRESH` | Within policy window for that `event_type` (window **unset** — no invented durations in 2.3C) |
| `STALE` | Too old to notify now |
| `UNKNOWN` | Required timestamp missing |

If a rule **requires** freshness and temporal authority is `UNKNOWN` → **SUPPRESS** (`EVENT_STALE` or treat as invalid freshness).  
**Do not invent timestamps.** Do not use `invoice.date` as notify freshness for “just became available” without an explicit detect transition.

---

## 7. Customer Relevance

Objective membership only — **no** LLM / text similarity.

| Event | Relevant if |
|---|---|
| Outage | Abonado in affected set (NAS match) |
| Ticket | Ticket belongs to that abonado/CN |
| Billing | Invoice/balance row for that CN/account |
| Connectivity / service | Service under that CN |

Else → `CUSTOMER_NOT_AFFECTED`.

---

## 8. Customer-Safe Validation

Internal metadata may exist on the event. **Notification payload** must pass a deny-list aligned with `_PAYLOAD_FORBIDDEN` (`app_push.py`) and 2.3B:

Block: NAS, Radius internals, internal IPs, infra ids, probe dumps, credentials, unverified causes, ETA not backed by `eta_validada`.

Fail → `CONTENT_NOT_SAFE`.

`customer_message` is representation; `facts` remain authority.

---

## 9. Severity

| Rule | |
|---|---|
| Source-provided severity | Use as-is when present |
| Not provided | `severity = UNKNOWN` |
| Policy use (future) | Quiet-hours override, rate-limit class — **no** invented urgency in 2.3C |

Do not assign arbitrary severity values in this phase.

---

## 10. Deduplication

### EVENT DEDUP

Same `(source, source_event_id, event_type[, revision])` must not be double-normalized into conflicting decisions.

### NOTIFICATION DEDUP

Same delivery intent must not send twice.

**Outage lifecycle — not duplicates of each other:**

| Event | Notification identity (today) |
|---|---|
| `outage.started` | `(outage_id, declared)` via `push_declared_at` claim |
| `outage.material_update` | `(outage_id, updated, …)` — **no** cycle claim; multiple material OK |
| `outage.resolved` | `(outage_id, resolved)` via `push_resolved_at` claim |

Re-reading an active outage must **not** re-emit `outage.started`.  
**Do not replace or auto-generalize** these claims in 2.3C.

Duplicate notify → `DUPLICATE`.

---

## 11. Cooldown

**Cooldown:** this *class* / subject was already communicated recently; wait until a **condition** or time window (values **not** chosen here).

| Signal | Cooldown applicable? | Why / required state |
|---|---|---|
| `outage.started` | Covered by claim (once per outage) | Claim is stronger than soft cooldown |
| `outage.material_update` | Soft cooldown **optional future** | Material updates intentionally re-notify; any cooldown must not contradict materiality |
| `outage.resolved` | Covered by claim | Once per outage |
| Billing STATE (`debt_detected`) | **Would require** explicit cooldown if ever enabled | STATE spam risk |
| Connectivity flapping | **Would require** hysteresis + cooldown | Pull probes |
| Ticket updates | Optional future | Avoid chatter |

Active cooldown → `COOLDOWN_ACTIVE`. No timers implemented.

---

## 12. Suppression Reasons (normalized)

| Code | When |
|---|---|
| `OWNERSHIP_UNRESOLVED` | No safe destinatario |
| `EVENT_STALE` | Freshness fail / UNKNOWN required ts |
| `EVENT_INVALID` | Malformed / missing required ids |
| `SOURCE_NOT_AUTHORIZED` | UNKNOWN / LLM / non-allowlisted TRUSTED_READ |
| `CUSTOMER_NOT_AFFECTED` | Relevance fail |
| `CHANNEL_UNAVAILABLE` | No usable channel |
| `DUPLICATE` | Notification dedup hit |
| `COOLDOWN_ACTIVE` | Cooldown |
| `CUSTOMER_SUPPRESSED` | Prefs / opt-out (future) |
| `CONTENT_NOT_SAFE` | Payload fail |
| `SIGNAL_NOT_SUPPORTED` | UNAVAILABLE / not enabled signal |
| `QUIET_HOURS` | Future quiet window (optional distinct) |
| `RATE_LIMITED` | Future rate limit |

---

## 13. Channel Eligibility

| Channel | Status | Ownership / destination | Opt-in | Proactive today | Limits |
|---|---|---|---|---|---|
| **App Push** | ACTIVE | PortalDevice token + DNI/abonado | App register `/portal/devices` | **Yes** (outages + inbox) | Expo; claim ≠ receipt |
| **WhatsApp** | ACTIVE **reactive** | E.164 after inbound/session rules | Channel trust / Meta | No proactive product path evidenced | Templates/campaigns not contracted here |
| **Telegram** | ACTIVE **reactive** | `chat_id` after webhook | Bot start | No proactive product path | Same |
| **Email** | Internal ops (handoff/SLA/CSAT) | Agent emails | N/A customer | Not customer proactive product | — |
| **SMS** | N/A (2.3A) | — | — | — | — |

No new channels activated in 2.3C.  
Proactive **ALLOW** for customer product today implies **App Push** unless a future phase explicitly enables another channel with its own auth/opt-in contract.

Missing channel → `CHANNEL_UNAVAILABLE`.

---

## 14. Device Eligibility (App Push)

Inspected: `POST/DELETE /portal/devices`, `PortalDevice`, `token_push_valido`, `activo`.

| Situation | Policy / current behavior |
|---|---|
| No device | No tokens → send 0; treat as `CHANNEL_UNAVAILABLE` for that customer |
| `activo=No` (deleted) | Excluded from queries |
| Invalid token shape | Excluded by `token_push_valido` |
| Multiple devices | All active tokens for affected DNI (dedup by token string) |
| Stale/invalid Expo token | Provider may fail; no estate “stale” detector documented — GAP |
| No DNI on device | Skipped in NAS fan-out |

Do not modify registration.

---

## 15. Multi-Account

- One user may have multiple accounts, services, devices.  
- Unit of ownership must be **explicit** (CN / ticket / outage-affected abonado).  
- Never notify from phone alone.  
- Unsafe mapping → `OWNERSHIP_UNRESOLVED`.

---

## 16. Quiet Hours

**Evaluation slot (future):** after relevance, before delivery — alongside severity override.

| Item | 2.3C stance |
|---|---|
| Default schedule | **Not invented** |
| Customer preferences | **Not implemented / not modified** |
| Emergency override | Only if severity/source rule exists later |

Possible suppress: `QUIET_HOURS` or `CUSTOMER_SUPPRESSED`.

---

## 17. Rate Limiting

| | Cooldown | Rate limit |
|---|---|---|
| Scope | Class / subject / event family | Count in a time window |
| Values | Not chosen here | Not chosen here |

Future hit → `RATE_LIMITED`. Distinct from event/notification dedup.

---

## 18. Current Outage Policy (conceptual wrap)

### 18.1 `outage.started`

ALLOW path (logical) when:

- Authority AUTHORITATIVE  
- Customer affected (NAS match)  
- Ownership → devices  
- Fresh enough for create-time notify (implicit: notify at create)  
- Customer-safe body (`mensaje_cliente`)  
- Channel App Push available  
- Not duplicate (`push_declared_at` claim)

### 18.2 `outage.material_update`

- Must use **existing** `outage_update_es_material` — **no second materiality definition**  
- Same ownership/fan-out/safe payload  
- Multiple updates allowed by design (no declared-style claim)

### 18.3 `outage.resolved`

- Resolution AUTHORITATIVE (`resolve` path)  
- Affected customer resolvable  
- Safe fixed body  
- Not duplicate (`push_resolved_at`)

**These checks are today embedded in CRUD + `app_push`, not a separate `ProactiveDecision` object.**

---

## 19. Future Billing Policy

| Signal | Policy stance |
|---|---|
| `billing.invoice_available` | PARTIAL — needs transition + allowlist TRUSTED_READ; no auto STATE spam |
| `billing.invoice_status_changed` | PARTIAL — needs prior snapshot |
| `billing.debt_detected` | PARTIAL — STATE; requires explicit cooldown/rate rule before ALLOW |
| `billing.payment_confirmed` | `SIGNAL_NOT_SUPPORTED` / UNAVAILABLE |
| `billing.due_date_approaching` | `SIGNAL_NOT_SUPPORTED` / UNAVAILABLE |
| `billing.payment_failed` | `SIGNAL_NOT_SUPPORTED` / UNAVAILABLE |

Do not convert BillTrack snapshots into notify without an authorized transition detector.

---

## 20. Future Ticket Policy

Events `ticket.created|updated|claimed|resolved|closed|reopened`: estate AUTHORITATIVE, ownership bind required, `visible_cliente` for customer-facing updates.

**No proactive ticket push today** → document only; `SIGNAL_NOT_SUPPORTED` until channel+policy enabled.  
`ticket.claimed` often INTERNAL unless product explicitly allows.

---

## 21. Future Connectivity Policy

`connectivity.down|degraded|recovered`: probes are PULL/STATE.

Require future: transition detection + persistence + threshold + hysteresis + cooldown.  
Until then: `SIGNAL_NOT_SUPPORTED` for proactive notify (on-demand diagnosis remains separate).

---

## 22. Future Service Policy

`service.activated|deactivated|changed`: UNAVAILABLE as EVENT while no transition source (2.2I writer UNKNOWN).  
Snapshot ≠ notify. → `SIGNAL_NOT_SUPPORTED`.

---

## 23. `ProactiveDecision` Contract (conceptual)

Not implemented. Conceptual fields:

| Field | Meaning |
|---|---|
| `decision` | `ALLOW` \| `SUPPRESS` \| `NOT_ELIGIBLE` \| `INVALID` |
| `reason` / `suppression_reason` | Normalized code (§12) |
| `event_id` | Canonical event id (future) |
| `event_type` | e.g. `outage.started` |
| `customer_scope` | account / service / ticket / outage_fanout |
| `channel` | e.g. `app_push` if ALLOW |
| `policy_version` | See §24 |

`NOT_ELIGIBLE`: structurally OK but no destinatario/channel.  
`INVALID`: malformed event.  
`SUPPRESS`: explicit suppression reason.

---

## 24. Policy Versioning

| Field | Rule |
|---|---|
| `policy_version` | e.g. `eko-proactive-policy-1` (proposed; not live) |
| Compatibility | Additive suppress reasons OK; changing ALLOW semantics = major bump |
| Audit | Every future delivery should answer: which `policy_version` allowed it? |

Not implemented.

---

## 25. Audit (future)

```text
EVENT DETECTED
  → POLICY EVALUATED (decision + reason + policy_version)
  → ALLOWED | SUPPRESSED
  → DELIVERY ATTEMPTED
  → DELIVERY RESULT
```

Today: outage push logs + claim timestamps. No general policy audit store — do not modify observability in 2.3C.

---

## 26. Compatibility with Existing Outage Push

**Critical rule:** current outage pipeline **must not be replaced** by 2.3C.

| Aspect | Legacy (live) | Canonical policy (doc) | Gap |
|---|---|---|---|
| Trigger | Ops HTTP CRUD | ProactiveEvent normalize | No normalizer |
| Materiality | `outage_update_es_material` | Same function | Keep single definition |
| Dedup | `push_*_at` claims | Notification dedup | Claims = attempt not Expo ACK |
| Decision object | Implicit in code | `ProactiveDecision` | Not wired |
| Channels | App Push only | Channel eligibility table | WA/TG not in outage path |
| Event type strings | `declared/updated/resolved` | `outage.started/…` | Alias only (2.3B) |

Future wrap (not implemented):

```text
EXISTING OUTAGE EVENT
  → (optional) Policy evaluation
  → Existing delivery (`notificar_incidente_*`)
```

**Do not change** `app_push.py` / outages API in this phase.

---

## 27. Current Implementation Matrix

| Event | Source | Authority | Ownership | Policy Ready | Channel Ready | Current Status |
|---|---|---|---|---|---|---|
| `outage.started` | Estate outages | AUTHORITATIVE | NAS fan-out | Embedded (legacy) | App Push | **READY** |
| `outage.material_update` | Estate + materiality | AUTHORITATIVE | Same | Embedded | App Push | **READY** |
| `outage.resolved` | Estate resolve | AUTHORITATIVE | Same | Embedded | App Push | **READY** |
| `billing.invoice_available` | BillTrack | TRUSTED_READ | CN | No transition/policy | No | **PARTIAL** |
| `billing.debt_detected` | BillTrack balance | TRUSTED_READ | CN | STATE risk | No | **PARTIAL** |
| `billing.payment_confirmed` | — | — | — | — | — | **UNAVAILABLE** |
| `billing.due_date_approaching` | — | — | — | — | — | **UNAVAILABLE** |
| `ticket.updated` | TicketEvent | AUTHORITATIVE | Ticket bind | Doc only | No ticket push | **PARTIAL** |
| `connectivity.down` | Probes | DERIVED/TRUSTED | service | Needs hysteresis | No | **PARTIAL** |
| `connectivity.degraded` | Probes | DERIVED | service | Needs hysteresis | No | **PARTIAL** |
| `connectivity.recovered` | Probes | DERIVED | service | Needs hysteresis | No | **PARTIAL** |
| `service.changed` | api_service STATE | Writer UNKNOWN | CN+service | No transition | No | **UNAVAILABLE** |

READY = live path that already decides+delivers (even without `ProactiveDecision` type).  
PARTIAL = source/partial rules exist; policy+channel not enabled.  
UNAVAILABLE = no authorized signal per 2.3A.

---

## 28. Gaps for 2.3D

1. Optional **adapter** that records `ProactiveDecision` around existing outage push **without** changing send behavior.  
2. Define (with product) freshness windows / quiet hours / rate limits — values still TBD.  
3. Stale Expo token hygiene.  
4. Ticket/billing enablement only after transition detectors + channel contract.  
5. Do **not** implement notification engine / scheduler / WA proactive campaigns in 2.3D unless brief says so.  
6. Compatibility: map `declared`↔`outage.started` in audit only.

---

## Explicit Non-Goals (2.3C)

No code, DB, push changes, schedulers, workers, queues, engines, capabilities, Runtime Actions.  
No invented durations, severities, or default quiet hours.  
No second materiality. No LLM authorization.

---

## Document control

| Field | Value |
|---|---|
| Document id | `eko-2.3c-proactive-notification-policy` |
| Proposed `policy_version` | `eko-proactive-policy-1` (not live) |
| Active policy gate in runtime | **NO** |
| Prior | 2.3A PASS, 2.3B PASS |
