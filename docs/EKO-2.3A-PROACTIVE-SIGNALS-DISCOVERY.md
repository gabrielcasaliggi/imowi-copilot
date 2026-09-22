# EKO 2.3A — PROACTIVE SIGNALS DISCOVERY

**Status:** READ-ONLY discovery  
**Runtime impact:** NONE — documentation only  
**Notifications sent:** NONE  
**Jobs / cron / capabilities / Runtime Actions created:** NONE  

Principio: **LLM ≠ fuente de eventos**. Cadena conceptual:

```text
SOURCE OF TRUTH → SIGNAL DETECTION → PROACTIVE POLICY → DEDUP/COOLDOWN → NOTIFICATION → AUDIT
```

---

## 1. Purpose

Mapear hechos verificables que Eko puede detectar hoy para una futura comunicación proactiva al cliente — sin implementar motor, push nuevos, ni schedulers.

Pregunta central:

> ¿Qué hechos reales puede detectar Eko hoy, con fuentes verificables, para iniciar una comunicación proactiva al cliente?

---

## 2. Sources Inspected

| Area | Paths |
|---|---|
| Billing | `billtrack.py`, `eko_invoice_reader.py`, `eko_journeys` billing, `eko_context`, `eko_action_runtime` `show_balance`/`show_invoice` |
| Services | `api_service` SELECT, `portal_services.py`, `eko_service_selection.py` |
| Connectivity | `portal_connectivity.py`, Radius/BCM/UISP clients, `connectivity_*` |
| Outages | `outages.py`, `api/v1/outages.py`, push callers |
| Tickets | `portal.py` tickets, `Ticket`/`TicketEvent`, `abonado_tickets.py` |
| Push | `app_push.py`, `PortalDevice`, `/portal/devices` |
| Channels | `whatsapp_client.py`, `telegram_client.py`, inbox push |
| Ownership | TrustedContext, BillTrack CN, devices by DNI, NAS matching |

---

## 3. Source Authority Matrix

| Source | Role | Authority class | Customer write? |
|---|---|---|---|
| BillTrack `api_person` / `billing_balance` | Debt/balance snapshot | TRUSTED READ | No (Eko RO) |
| BillTrack `api_invoice` | FC headers | TRUSTED READ | No |
| BillTrack `api_service` | Service catalog/state | TRUSTED READ | Writer UNKNOWN (2.2I) |
| Estate `NetworkOutage` | Declared mass incident | AUTHORITATIVE (ops declare) | Estate WRITE by agents |
| Estate `Ticket` / `TicketEvent` | Support case lifecycle | AUTHORITATIVE (estate) | Estate WRITE |
| Radius session | Live PPPoE/NAS | TRUSTED READ (tech) | No |
| BCM / UISP | Access probe | TRUSTED READ (tech) | No |
| Portal connectivity TSS | Derived diagnosis | DERIVED | No |
| `selected_service_ref` | Conversation selection | DERIVED from catalog | State only |
| Estate `Abonado.deuda_monto` | Cache from BillTrack hit | DERIVED / stale risk | Estate cache WRITE |
| Expo push | Delivery pipe | Delivery only | External |
| WhatsApp / Telegram send | Reply pipe | Delivery; typically reactive | Yes (text) |
| LLM / KB | Content | NOT event authority | — |

---

## 4. Signal Inventory (minimum set)

Legend support: **SUPPORTED** | **PARTIAL** | **UNAVAILABLE**

### Billing

| # | Signal | Support | Kind | Notes |
|---|---|---|---|---|
| 1 | `invoice_available` | **PARTIAL** | STATE | Headers readable now; **new** invoice = needs change detection (no event bus / snapshot store) |
| 2 | `invoice_status_changed` | **PARTIAL** | TRANSITION | `status` field exists; no stored previous status → transition not detectable without new infra |
| 3 | `debt_detected` | **PARTIAL** | STATE | `billing_balance` / `deuda_monto` readable; repeating STATE without policy = spam risk |
| 4 | `payment_history_changed` | **UNAVAILABLE** | — | Billing 2.1 honest unavailable; no payment history authority |
| 5 | `due_date_approaching` | **UNAVAILABLE** | — | `due_date` not in `api_invoice` reader (explicitly null) |
| 6 | `payment_failed` | **UNAVAILABLE** | — | No payment failure source found |

### Connectivity / outages

| # | Signal | Support | Kind | Notes |
|---|---|---|---|---|
| 7 | `outage_started` | **SUPPORTED** | EVENT | Ops POST create → push `declared` already |
| 8 | `outage_material_update` | **SUPPORTED** | EVENT | `outage_update_es_material` gates push `updated` |
| 9 | `outage_resolved` | **SUPPORTED** | EVENT | Resolve → push `resolved` + claim dedup |
| 10 | `service_access_down` | **PARTIAL** | STATE/DERIVED | Probe on-demand; no proactive watcher; customer-safe only with care |
| 11 | `no_pppoe_session` | **PARTIAL** | STATE | Radius READ; often INTERNAL / triage; not auto-notify |
| 12 | `quality_degraded` | **PARTIAL** | DERIVED | BCM/UISP thresholds; INTERNAL_ONLY until policy |

### Tickets

| # | Signal | Support | Kind | Notes |
|---|---|---|---|---|
| 13 | `ticket_created` | **PARTIAL** | EVENT | Estate event exists; **no** customer push today |
| 14 | `ticket_updated` | **PARTIAL** | EVENT | Events with `visible_cliente`; no push |
| 15 | `ticket_claimed` | **PARTIAL** | EVENT/STATE | `asignado_a` / events; INTERNAL unless filtered |
| 16 | `ticket_resolved` | **PARTIAL** | TRANSITION | `estado` + `updated_at`; no push |
| 17 | `ticket_closed` | **PARTIAL** | TRANSITION | Same |
| 18 | `ticket_reopened` | **PARTIAL** | TRANSITION | Detectable if estado transitions logged; no dedicated signal infra |

### Services

| # | Signal | Support | Kind | Notes |
|---|---|---|---|---|
| 19 | `service_activated` | **UNAVAILABLE** as EVENT | — | State `Habilitado` readable; no writer/event stream in Eko; SoT writer UNKNOWN |
| 20 | `service_deactivated` | **UNAVAILABLE** as EVENT | — | Same (`Baja` etc. as STATE only) |
| 21 | `service_state_changed` | **PARTIAL** | TRANSITION* | `state` + `last_state_date` exist; **no** poll/snapshot → transition not operationally detectable today |

\*Would require stored prior snapshot — **NOT_FOUND**.

---

## 5. Supported Signals (detectable + path exists)

| Signal | Source | Authority | Evidence | Customer-safe | Detectable now | Change detection |
|---|---|---|---|---|---|---|
| `outage_started` | `NetworkOutage` + POST `/outages` | AUTHORITATIVE | `outages.py` create + `notificar_incidente_app` | Yes (mensaje_cliente; NAS stripped from payload) | Yes | EVENT on create |
| `outage_material_update` | PATCH outage + materiality fn | AUTHORITATIVE + policy | `outage_update_es_material` | Yes if body = mensaje_cliente | Yes | EVENT when material |
| `outage_resolved` | resolve endpoint | AUTHORITATIVE | `notificar_incidente_resuelto_app` | Yes (fixed BODY_RESOLVED) | Yes | EVENT + claim |

These are already **notification-backed** (App Push), not merely theoretical.

---

## 6. Partial Signals

| Signal | Why partial |
|---|---|
| Invoice / debt STATE | Data READ OK; no proactive detector, no prior snapshot, no notification path |
| Ticket lifecycle | Estate AUTHORITATIVE events; portal READ; **no** Expo push for tickets |
| Connectivity probes | On-demand in journeys; DERIVED diagnosis; no watcher; often not customer-safe raw |
| Service state | READ `api_service.state`; no transition store; writer outside Eko |

---

## 7. Unavailable Signals

| Signal | Gap |
|---|---|
| `due_date_approaching` | No due_date in invoice contract |
| `payment_history_changed` | Capability false / honest unavailable |
| `payment_failed` | No source |
| `service_activated` / `deactivated` as EVENT | No commercial writer / event feed in workspace |

---

## 8. Event vs State vs Transition

| Kind | Definition | Examples in Eko today |
|---|---|---|
| **EVENT** | Something happened once | Outage declared/updated/resolved; ticket event row created |
| **STATE** | Condition is true now | `deuda > 0`; `state=Habilitado`; `no_session` on probe |
| **TRANSITION** | STATE A → B | Invoice status change; ticket Abierto→Resuelto; service Baja |

**Policy implication:** Prefer EVENT/TRANSITION for proactive notify. STATE alone requires eligibility + cooldown or it becomes repetitive.

Existing outage pipeline already prefers EVENT + materiality (not “outage still active” spam).

---

## 9. Ownership / Customer Mapping

```text
EVENT (outage NAS)
  → abonado_afectado_por_nas(abonado, nas)
      ← BillTrack services (CN/DNI) + Radius session.nas
  → PortalDevice(dni_normalized) tokens
  → Expo push
```

| Link | Safe? | Notes |
|---|---|---|
| DNI → Abonado (estate) | Trusted if from auth/sync | |
| Abonado.`client_number` | TrustedContext / BillTrack | Never LLM |
| Multi-account same phone | Ambiguous for WA | Disambiguation exists for inbound; proactive WA must not invent mapping |
| Device → conversation | Optional filter | Inbox push uses `conversacion_id` |
| Service ↔ outage | Via NAS of live session | False-negative preferred if no NAS evidence |
| Ticket ↔ customer | Ticket ownership / portal list | Must enforce before notify |

**LLM must never choose recipient.**

---

## 10. Temporal Authority

| Source | Timestamps | Temporal authority |
|---|---|---|
| `NetworkOutage` | `started_at`, `resolved_at`, `created_at`, `updated_at`, `push_*_at` | AUTHORITATIVE for incident lifecycle |
| `api_invoice.date` | Issue/document date | TRUSTED READ for invoice **data** date ≠ “detected at” |
| `api_service.last_state_date` | Present in SELECT | TRUSTED READ if populated; change event still UNKNOWN without snapshot |
| `Ticket` / `TicketEvent` | `created_at`, ticket `updated_at` | AUTHORITATIVE estate |
| Connectivity probe | Request time only | DERIVED; no historical series store |
| Debt balance | Snapshot at lookup | No change timestamp from BillTrack in mapped fields |

Where no reliable event time: `TEMPORAL AUTHORITY = UNKNOWN`.

---

## 11. Signal Identity (conceptual)

| Signal family | Stable identity keys (when available) |
|---|---|
| Outage | `outage_id`, `event` ∈ {declared,updated,resolved}, `organizacion_id`, `source=estate` |
| Invoice | `invoice_id`, `account_number`(=CN), `status` — **no** due_date |
| Debt | `client_number` + balance snapshot hash — needs policy |
| Ticket | `ticket_id`, `event_id`/`created_at`, `visible_cliente` |
| Service | `service_id` + `client_number` + `state` — transition needs prior |
| Connectivity | `service_id`/`login` + `reason_code` + probe_ts — weak for proactive |

Do not invent IDs the source lacks.

---

## 12. Existing Dedup / Cooldown

| Mechanism | Scope | Exists? |
|---|---|---|
| `claim_outage_push_declared` / `push_declared_at` | One declared push attempt per outage | **Yes** |
| `claim_outage_push_resolved` / `push_resolved_at` | One resolved push attempt | **Yes** |
| Outage `updated` cycle dedup | — | **No** (by design: multiple material updates OK) |
| General notification history table | Cross-domain proactive | **NOT_FOUND** |
| Quiet hours | — | **NOT_FOUND** |
| WhatsApp inbound wamid idempotency | Webhook duplicates | Yes (inbound only) |
| WiFi BCM ephemeral cooldown | Tech action | Unrelated to customer proactive |
| Ticket push dedup | — | **NOT_FOUND** (no ticket push) |

Claim timestamps = **attempt claimed**, not Expo delivery confirmation.

---

## 13. Existing Push Mechanisms

| Function | Trigger | Channel | Payload notes |
|---|---|---|---|
| `notificar_incidente_app` | Outage create | Expo `channelId=eko` | `tipo=incidente`, `outage_id`, `event=declared`; forbids NAS/infra keys |
| `notificar_incidente_actualizado_app` | Material PATCH | Expo | `event=updated` |
| `notificar_incidente_resuelto_app` | Resolve | Expo | `event=resolved`; fixed body |
| `notificar_conversacion_app` | Inbox agent → app | Expo | `conversacion_id` |
| Ticket lifecycle push | — | — | **NOT_FOUND** |
| Billing push | — | — | **NOT_FOUND** |

Deep link / screen target: payload carries `tipo`/`outage_id`/`event`/`conversacion_id`; no universal proactive schema beyond incident.

Devices: `PortalDevice` via `/portal/devices` registration.

---

## 14. Outbound Channels

| Channel | Classification | Proactive today? |
|---|---|---|
| App Push (Expo) | **ACTIVE** | Yes for outages (+ inbox reactive) |
| WhatsApp Cloud API | **ACTIVE** (send text/audio/CSAT) | Typically **reactive** to inbound; no proactive billing/outage WA found |
| Telegram Bot | **ACTIVE** (send/edit/CSAT) | Reactive webhook replies |
| Email (`handoff_notify`, `sla_notify`, CSAT bajo) | ACTIVE internal | Agent/ops — not customer proactive product |
| SMS | **NOT_AVAILABLE** / UNKNOWN | Not found as proactive product path |

---

## 15. Customer-Safe Facts

| Domain | FACT (communicable) | DERIVED (needs policy) | SPECULATION / FORBIDDEN |
|---|---|---|---|
| Outage | Declared/updated/resolved; approved `mensaje_cliente`; ETA only if `eta_validada` | Affected via NAS match | Cause, duration inventada, compensación, NAS names in payload |
| Invoice | number, amount, date, status | “Tenés factura nueva” needs transition detect | due_date, period, currency inventada |
| Debt | monto from BillTrack snapshot | “Tenés deuda” as STATE | Payment failed, due approaching |
| Ticket | id, estado, visible events | “Tu reclamo fue resuelto” | Internal comments if `visible_cliente=No` |
| Connectivity | — | Aggregated customer-safe status | Raw ONU/CPE metrics to user as diagnose promise |

---

## 16. Proactive Policy Requirements (design only)

Future policy must decide (no values assumed):

- eligibility / channel availability (device token vs WA vs TG)
- ownership verification (CN / DNI / ticket bind)
- event freshness
- dedup key + cooldown
- quiet hours (if product requires)
- severity / customer relevance
- suppression (e.g. billing intent blocks outage soft-inject already in N1 — separate from push)
- escalation / handoff if delivery fails
- audit of detect → discard → send → fail

Reuse outage materiality pattern; **do not invent a parallel materiality** for outages.

---

## 17. Exact Gaps

1. No general proactive signal detector / scheduler.  
2. No snapshot store for BillTrack invoice/debt/service transitions.  
3. No `due_date` / payment history / payment_failed sources.  
4. No customer push for ticket lifecycle.  
5. No cross-domain notification ledger / cooldown.  
6. Connectivity is pull-based; no safe proactive aggregation job.  
7. Service activation EVENTs depend on external writer (2.2I UNKNOWN).  
8. WhatsApp/Telegram proactive templates/campaigns not evidenced as productized.  
9. Delivery success ≠ claim timestamps (Expo ack not modeled as SoT).

---

## 18. Objective Property Tags (no subjective ranking)

| Signal | SOURCE_AVAILABLE | SOURCE_AUTHORITATIVE | CUSTOMER_LINKED | TEMPORALLY_VERIFIABLE | CUSTOMER_SAFE | DEDUP_READY | NOTIFICATION_READY |
|---|---|---|---|---|---|---|---|
| outage_started | Y | Y | Y (NAS→abonado→device) | Y | Y | Y | Y |
| outage_material_update | Y | Y | Y | Y | Y | Partial (no update-cycle dedup) | Y |
| outage_resolved | Y | Y | Y | Y | Y | Y | Y |
| invoice_available | Y | TRUSTED READ | Y (CN) | Partial (date≠detect) | Y | N | N |
| debt_detected | Y | TRUSTED READ | Y | N (snapshot) | Y with care | N | N |
| invoice_status_changed | Y fields | TRUSTED READ | Y | N without prior | Y | N | N |
| ticket_* | Y | Y estate | Y if ownership | Y events | If visible | N | N |
| no_pppoe / quality / access_down | Y probes | TRUSTED/DERIVED | If service selected | Probe time only | Often N / INTERNAL | N | N |
| service_*_activated | STATE only | Writer UNKNOWN | Y | last_state_date? | Y state text | N | N |
| due_date / payment_* | N | NOT_FOUND | — | — | — | — | — |

---

## 19. Observability (existing)

| Signal | Existing observability |
|---|---|
| Outage push | Logs `outage_push event=… affected_subscribers=… skipped=…`; claim columns |
| Expo send | HTTP status logged; return `{ok,sent}` — not per-device receipt store |
| Inbox push | Via conversacion notify |
| Detected-but-discarded billing/ticket signals | **NOT_FOUND** (no detector) |

---

## 20. Document Control

| Field | Value |
|---|---|
| Document id | `eko-2.3a-proactive-signals-discovery` |
| Code modified | **None** |
| Next phase | **2.3B** — Event / signal contract (design), starting from SUPPORTED outage path + PARTIAL gaps |

---

## Explicit Non-Goals (2.3A)

No scheduler, cron, worker, queue, notification engine, new push events, new capabilities, Runtime Actions, Billing/CASI/Service Management changes.
