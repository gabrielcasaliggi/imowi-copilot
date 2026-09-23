# EKO 2.6A — Ticket SLA Breach Proactive Push

**Status:** PASS  
**Date:** 2026-09-23  
**Depends on:** 2.3G-B, 2.3G-M, 2.3H, 2.6 Discovery  
**Preserves:** 2.5 FROZEN, CASI, Billing 2.1, SM 2.2, Commercial 2.4  

---

## 1. Authority source

| Item | Evidence |
|---|---|
| Field | `Ticket.sla_breached_at` |
| Writer | `apply_sla_to_ticket` (`app/estate/sla_engine.py`) |
| Transition | `NULL → due` when `now > sla_due_at` and ticket not `Cerrado` |
| Detection hook | `refresh_tickets_sla` / `ensure_ticket_sla` (`repository.py`) — same path as ops email |
| Actor | Sistema (deterministic SLA engine); **no LLM** |
| TicketEvent | Emitted as `tipo=sla_breach`, `visible_cliente=Sí`, `actor=sistema` |

**Classification:** `SLA_BREACH_AUTHORITY = READY`  
(transition is authoritative; detection runs when tickets are refreshed/ensured — not a new scheduler/poller).

---

## 2. SLA breach semantics

| Concept | Meaning |
|---|---|
| `sla_due_at` | Deadline derived from policy + `created_at` |
| `sla_breached_at` | Set to the **deadline** (`due`) on first breach — not wall-clock “now” |
| `occurred_at` (facts) | Prefer `sla_breached_at` (deadline crossed) |
| `detected_at` | Approx. `TicketEvent.created_at` when event is emitted |
| `delivered_at` | Expo attempt time (claim ≠ exact delivery) |

Does **not** invent breach from `updated_at` alone.

---

## 3. Event identity

```text
TicketEvent.id  (tipo=sla_breach)
```

Canonical proactive type: `ticket.sla_breached`  
Mobile payload `event`: `sla_breached`  
Dedup claim: `ticket_events.push_claimed_at` (existing `claim_ticket_event_push`)

Idempotent emit: at most one `sla_breach` TicketEvent per ticket.

---

## 4. Customer visibility policy

Deterministic gates (reuse 2.3G-B + SLA extras):

1. `visible_cliente` affirmative on TicketEvent  
2. `tipo` not in internal denylist  
3. `tipo=sla_breach` → `ticket.sla_breached`  
4. Event `estado ≠ Cerrado`  
5. Ticket not closed at refresh time (engine skips `Cerrado`)  
6. Ownership resolvable via existing portal rules  

No LLM / free-text classification.

---

## 5. Ownership

Unchanged path:

```text
Ticket → ticket_pertenece_abonado → conv / linea → DNI → PortalDevice → Expo
```

Unresolved owner → **0 pushes**, no claim burned when ownership gate fails before claim (same as 2.3G-B).

---

## 6. Dedup

1. Engine sets `sla_breached_at` once (no re-transition).  
2. Emit skips if `sla_breach` event already exists.  
3. `claim_ticket_event_push(TicketEvent.id)` → at most one Expo attempt per event.

---

## 7. Push adapter

Reuses `deliver_proactive_push` → `notificar_ticket_app`.  
No new provider, no campaign engine, no scheduler.

---

## 8. Mobile contract

```json
{ "tipo": "ticket", "ticket_id": "<id>", "event": "sla_breached" }
```

Navigation: Activity + `ticket_id` (unchanged).  
Authority of ticket content: `GET /portal/tickets/{id}`.

Minimal TS allowlist update: `CanonicalTicketEvent` includes `sla_breached`.

---

## 9. Temporal semantics

Documented in §2.

---

## 10. Error semantics

Same as 2.3G-B/E: provider success ≠ business success; claim ≠ exactly-once delivery; DeviceNotRegistered → deactivate; transient → no deactivate.

---

## 11. Tests

`tests/test_eko_ticket_sla_breach_2_6a.py` — valid send, no owner, duplicate, claim, multi-device, policy, mapping, payload, regression of created/updated/closed.

---

## 12. Known limitations

| ID | Limitation |
|---|---|
| L-01 | Breach is detected when SLA refresh/ensure runs (list/get paths), not via a dedicated timer. Same as ops email today. |
| L-02 | If emit fails after `sla_breached_at` is persisted, ops email may exist without customer event until manual remediation. |
| L-03 | Message does not promise resolution time or agent assignment. |
| L-04 | No second SLA breach push if deadline later changes (field is write-once). |

---

## 13. Production activation

**Implementation-ready** when:

- App deploy includes mobile `sla_breached` allowlist  
- Backend deploy includes emit hook  
- Expo credentials unchanged  

No feature flag required beyond existing proactive paths.  
Do **not** force mass `refresh_tickets_sla` in prod as a “backfill” without ops plan (would notify all already-breached open tickets that lack a `sla_breach` event).

---

## 14. Files

| Path | Role |
|---|---|
| `app/services/eko_ticket_proactive.py` | map + copy + `emit_customer_sla_breach_event` |
| `app/services/eko_proactive_contract.py` | `ticket.sla_breached` supported |
| `app/estate/repository.py` | emit on newly_breached |
| `app/services/app_push.py` | payload allowlist |
| `mobile/src/pushIncidente.ts` | event normalize |
| `mobile/scripts/verify-push-incidente.mjs` | mirror test |
| `tests/test_eko_ticket_sla_breach_2_6a.py` | suite |

---

**FINAL:** `EKO 2.6A — TICKET SLA BREACH PROACTIVE PUSH — PASS`
