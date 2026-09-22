# EKO 2.3G — TICKET PROACTIVE EVENT DETECTOR

**Status:** **BLOCKED** (no runtime shipped)  
**Depends on:** 2.3A–2.3F PASS  
**Runtime impact:** NONE  

Principio del brief: si el payload móvil actual **no puede representar** un evento de ticket sin modificar mobile, **STOP** — no inventar contrato móvil ni segundo mecanismo de notificación.

---

## 0. Gate result

| Check | Result |
|---|---|
| TicketEvent source exists | **Yes** (`ticket_events`, `TicketEvent.id`, `created_at`, `visible_cliente`) |
| Authoritative write path | **Yes** (`repo.add_ticket_event` — unique ORM writer) |
| Customer-visible gate feasible | **Yes** (`visible_cliente` + allowlist of `tipo`/`estado`) — *not implemented* |
| Existing proactive policy/delivery reusable for tickets | **Partial** — contract/policy can extend; **delivery payload cannot** |
| Mobile can route ticket push safely | **No** |
| Outage claim fields reusable for TicketEvent.id | **No** (outage-specific; must not force) |
| Implementation shipped | **No** |

**STATUS: BLOCKED**

**Missing dependency (exact):** mobile push contract + intent routing for tickets.

---

## 1. TicketEvent source (verified)

| Field | Role |
|---|---|
| `TicketEvent.id` | Stable UUID PK (`default=_uuid`) — canonical `source_event_id` |
| `TicketEvent.created_at` | Persistence/append time — usable as `occurred_at` (limitation: no separate transition clock) |
| `TicketEvent.tipo` | Free-string kind (`actualizacion`, etc.) — not a closed enum in model |
| `TicketEvent.estado` | Optional status snapshot on the event |
| `TicketEvent.visible_cliente` | Explicit gate (`"Sí"` / other) — **do not infer from text** |
| `TicketEvent.titulo` / `detalle` | Human text — **never** event identity; may contain internal content |

Model: `app/estate/models.py` (`Ticket`, `TicketEvent`).

---

## 2. Authoritative write path (verified)

Single ORM writer:

```text
app.estate.repository.add_ticket_event(...)
  → TicketEvent(...)
  → db.add / commit / refresh
```

Callers (all go through `repo.add_ticket_event` or the API wrapper that calls it):

| Caller | Typical content |
|---|---|
| `repository.create_ticket` | creation timeline |
| `repository` status helpers | updates |
| `api/v1/tickets.py` | agent/API timeline + patches |
| `seguimiento_ticket.py` | follow-up |
| `encuesta_satisfaccion.py` | CSAT |
| `api/v1/kb.py` | KB drafts / learning |
| `estate/learning_loop.py` | learning |
| `ticket_contexto.py` | context |

Detector boundary **would** be `add_ticket_event` **after** successful commit — **not implemented** because delivery is blocked.

**Coverage note:** no second ORM insert path found for `TicketEvent`. Completeness of “every ticket mutation emits an event” is caller-dependent (not all mutations may call `add_ticket_event`).

---

## 3. Customer-visible allowlist (design only — not enabled)

Would be deterministic, field-based:

1. `visible_cliente` must be customer-yes (existing semantics, e.g. `"Sí"`).
2. Allowlist of customer-safe lifecycle mappings from `tipo`/`estado` only when proven by portal exposure / product language.
3. Suppress: internal notes, assignment-only, SLA, staff-only, unsupported `tipo`.

**Not implemented** — no events enabled.

---

## 4. Internal-event suppression (design)

Hard rules (when unblocked):

- No push if `visible_cliente` ≠ customer-visible.
- No SLA → customer Expo (brief absolute rule 17).
- No LLM visibility.
- No visibility from message text alone.

---

## 5–6. Event identity & timestamp (design)

| Field | Value |
|---|---|
| `source` | `ticket` |
| `source_event_id` | `TicketEvent.id` |
| `event_type` | `ticket.*` (only after allowlist) |
| `occurred_at` | `TicketEvent.created_at` |
| Dedup | Must **not** use `push_declared_at` / `push_resolved_at` / `push_material_fingerprint` on `NetworkOutage` |

Outage claims are **outage-scoped**. Forcing `TicketEvent.id` into those columns would corrupt outage AT-MOST-ONCE semantics. A future minimal claim (e.g. idempotency key on delivery attempt keyed by `TicketEvent.id`) would be a **separate** small extension — **not** designed here because mobile blocks first.

---

## 7–8. Ownership & multi-account (verified gap for delivery)

`Ticket` fields today: org, `linea`, estado, etc. — **no direct `client_number` column**.

Portal visibility uses abonado binding (`abonado_tickets` / portal session DNI → tickets), not phone-as-account resolver.

Proactive delivery would need:

```text
Ticket → trusted abonado / client_number → PortalDevice (same org + dni_normalized)
```

Ambiguous ownership → SUPPRESS.  
**Not implemented.** Cross-account isolation tests deferred with runtime.

---

## 9. Detector location (would-be)

```text
add_ticket_event (post-commit)
  → visibility gate
  → ProactiveEvent(ticket.*)
  → evaluate_proactive_notification
  → deliver_proactive_push
```

No scheduler / poll / queue / bus. **Not wired.**

---

## 10. Transaction semantics

`add_ticket_event` commits the event in its own `db.commit()`. Callers often mutate the ticket in a prior/separate commit. Ordering is **not** a single atomic ticket+event transaction across all callers.

Limitation (documented, not redesigned): synchronous post-commit emit can still race with later logical rollback of business intent; no outbox in this phase. **N/A while blocked.**

---

## 11–14. Proactive contract / policy / dedup / delivery

Existing stack (2.3D/E):

| Piece | Outage | Ticket (2.3G) |
|---|---|---|
| `eko_proactive_contract.SUPPORTED_PROACTIVE_EVENTS` | outage.* only | would need `ticket.*` — **not added** |
| `eko_proactive_policy` | outage chain | reusable pattern — **not extended** |
| `eko_proactive_push` | → `notificar_incidente_*` | needs ticket delivery path — **blocked** |
| Claims | `NetworkOutage.push_*` | **inappropriate** for TicketEvent.id |
| Expo | via `app_push.enviar_push_expo` | same transport OK **if** payload typed |

**Forbidden workarounds rejected:**

| Workaround | Why rejected |
|---|---|
| Reuse `tipo=incidente` + fake `outage_id=ticket_id` | Wrong domain; refreshes Connectivity; pollutes outage claims; violates outage semantics |
| Reuse `conversacion_id` / `mensaje_agente` | Opens Eko chat, not ticket Activity; not ticket ownership path; second semantics |
| Title/body-only push with empty/unknown `data` | Mobile defaults to Home; **cannot open ticket**; not a safe ticket representation |
| Direct Expo from ticket code | Violates reuse rules |
| New parallel ticket push adapter | Second notification system — forbidden |
| Silent mobile contract invent in backend only | App cannot interpret `ticket_id` / `tab=activity` from push |

---

## 15. Mobile contract dependency (BLOCKER)

### Current mobile authority

File: `mobile/src/pushIncidente.ts`

| `data` shape | Intent |
|---|---|
| `tipo=incidente` + `outage_id` + `event∈{declared,updated,resolved}` | `tab=home`, `refreshConnectivity=true` |
| `tipo=mensaje_agente` **or** any `conversacion_id` | `tab=eko` |
| else | `tab=home`, no connectivity refresh |

`PushOpenIntent` **type** includes `tab: "activity"` but **`intentFromPushData` never returns `activity`** and **never reads `ticket_id`**.

`mobile/App.tsx` applies only `intent.tab` + `refreshConnectivity` — no ticket deep-link.

### Exact dependency to unblock a future 2.3G′ (out of this phase)

Backend + mobile must agree on a **new** typed payload, for example:

```text
{
  "tipo": "ticket",
  "ticket_id": "<Ticket.id>",
  "event": "created" | "updated" | "resolved" | "closed"
}
```

Mobile must:

1. Parse `tipo=ticket` (reject inventing via incidente).
2. Return intent `{ tab: "activity", ticket_id, refreshConnectivity: false }`.
3. Wire Activity/AppShell to open that ticket (list/detail already exist via `/portal/tickets`).

Until that ships, **customer ticket proactive push is not production-safe**.

---

## 16. Customer payload/message (deferred)

Deterministic short templates would be defined only after mobile contract exists. No LLM. No internal `detalle` leakage.

---

## 17. Test matrix

**Not executed as implementation suite** — no runtime to test.  
Regression of prior phases: unchanged (this phase modified no Python/runtime).

---

## 18. Files

| Action | Path |
|---|---|
| Created | `docs/EKO-2.3G-TICKET-PROACTIVE-EVENT-DETECTOR.md` |
| Modified (code) | **None** |

---

## 19. Known limitations

1. **BLOCKER:** mobile has no ticket push type / Activity deep-link from push.
2. Outage claim columns cannot dedup TicketEvent.id.
3. Ticket ↔ abonado ownership for push is portal-derived, not a column on `Ticket`.
4. `TicketEvent.tipo` is free-form; allowlist must be evidence-based when unblocked.
5. Not every ticket mutation necessarily emits `TicketEvent`.

---

## 20. Exact delivery semantics (current production)

Unchanged from 2.3D/E:

```text
OUTAGE CRUD → ProactiveEvent(outage.*) → policy → outage claims → Expo
AT-MOST-ONCE attempt + BEST-EFFORT provider receipt
```

Ticket proactive delivery: **not enabled**.

---

## Document control

| Field | Value |
|---|---|
| Document id | `eko-2.3g-ticket-proactive-event-detector` |
| Decision | **BLOCKED** pending mobile ticket push contract |
| Next (outside this brief) | Product/mobile contract for `tipo=ticket` → then resume detector on `add_ticket_event` |
