# EKO 2.6B — Ticket SLA Breach Production Readiness & Controlled Smoke Audit

**Status:** PRODUCTION READY / SMOKE PENDING  
**Date:** 2026-09-23  
**Scope:** Audit only. No code changes. 2.6A remains closed.  
**Preserves:** 2.5 FROZEN, CASI, Billing, SM, Commercial, SLA engine semantics, proactive architecture  

---

## 1. Deployment audit

| Surface | Required? | Detail |
|---|---|---|
| **Backend deploy** | YES | `eko_ticket_proactive.py`, `eko_proactive_contract.py`, `repository.py` (emit hook), `app_push.py` (allowlist) |
| **Backend restart** | YES | Reload FastAPI process (`systemctl restart operations-hub-api` per `DEPLOY.md`) |
| **Config / env** | NO | No new env vars or feature flags. Reuses existing Expo / PortalDevice stack |
| **Mobile build** | YES | `sla_breached` must be in the installed APK allowlist (`pushIncidente.ts`). Devices without this build strip/ignore the event |
| **Migration** | NO | Reuses `Ticket.sla_breached_at`, `TicketEvent.tipo`, `TicketEvent.push_claimed_at` — already in schema |
| **Backfill** | NO — forbidden | Do **not** mass-run `refresh_tickets_sla` as activation. Historical tickets with `sla_breached_at` already set will **not** emit (transition gate `was_breached`) |

```text
backend_deploy = YES
mobile_build   = YES
migration      = NO
config_change  = NO
```

---

## 2. Production event chain

| Stage | File / function |
|---|---|
| SLA transition | `app/estate/sla_engine.py` → `apply_sla_to_ticket` (`NULL → due` into `sla_breached_at`) |
| Detection hook | `app/estate/repository.py` → `refresh_tickets_sla` / `ensure_ticket_sla` |
| Persist breach | same → `db.commit()` when SLA fields dirty |
| Customer event | `app/services/eko_ticket_proactive.py` → `emit_customer_sla_breach_event` |
| Persist event | `repository.add_ticket_event` (`tipo=sla_breach`, `visible_cliente=Sí`) |
| Detector | `maybe_deliver_ticket_event_push` (post-commit of event) |
| Gate + map | `is_ticket_event_customer_visible` / `map_ticket_event_type` → `ticket.sla_breached` |
| Policy | `eko_proactive_policy.evaluate_proactive_notification` |
| Adapter | `eko_proactive_push.deliver_proactive_push` |
| Ownership + claim + Expo | `app_push.notificar_ticket_app` → `listar_tokens_duenos_ticket` → `claim_ticket_event_push` → `enviar_push_expo` |
| Mobile intent | `mobile/src/pushIncidente.ts` (`tipo=ticket`, `event=sla_breached`) → Activity via `pushFocusTicketId` |
| Authority read | `GET /api/v1/portal/tickets/{id}` |

Triggers that call refresh/ensure (existing product paths, not new workers):

- `list_tickets` / `list_tickets_all` → `refresh_tickets_sla`
- Agent ticket get (`tickets.py`) → `ensure_ticket_sla`

---

## 3. Transaction boundary (L-02)

Exact sequence in `refresh_tickets_sla` / `ensure_ticket_sla`:

1. In-memory: `apply_sla_to_ticket` sets `sla_breached_at`.
2. **Commit A:** `db.commit()` persists SLA fields (including `sla_breached_at`).
3. **After Commit A:** `notify_sla_breach` (ops email) then `emit_customer_sla_breach_event`.
4. Emit → `add_ticket_event` → **Commit B** (TicketEvent) → then `maybe_deliver_ticket_event_push` (post-commit B).

```text
same transaction?     NO — SLA commit precedes event emit
post-commit emit?     YES — emit runs after Commit A
exception possible?   YES — emit wrapped in try/except; failure is logged only
```

**L-02 explained:** If the process dies or emit raises after Commit A, the ticket remains breached (`sla_breached_at` set) with **no** `TicketEvent(tipo=sla_breach)`. On the next refresh, `was_breached=True`, so the ticket is **not** in `newly_breached` and emit is **not** retried automatically. Ops email may have succeeded independently. Remediation would be manual (out of scope for 2.6B). This is a known accepted gap, same structural pattern as ops notify after commit.

Push claim (`push_claimed_at`) is a further separate commit inside `notificar_ticket_app` after ownership resolves.

---

## 4. Observability (existing only)

| Step | How an operator verifies |
|---|---|
| A. `sla_breached_at` | DB / agent ticket API fields `sla_breached_at`, `estado_sla` |
| B. TicketEvent | `ticket_events` row `tipo=sla_breach` / portal event list (customer-visible) |
| C. Policy ALLOW | Logs `ticket_proactive policy ... decision=` or proceed to result log without suppress |
| D. Ownership | `ticket_push ... skipped=ownership_unresolved` **or** `owner_abonados=N` |
| E. Claim | DB `ticket_events.push_claimed_at` set; log `skipped=already_claimed` on retry |
| F. Expo attempt | Logs `proactive_push attempt` + `ticket_push event=sla_breached ...` |
| G. Expo result | `ticket_push ... push_sent= push_ok= error_category=` |
| H. Mobile receipt | **Device-side only** — no server Expo receipt poll in this path |
| I. Ticket opened | App Activity focus via existing `pushFocusTicketId` |
| J. Auth read | `GET /api/v1/portal/tickets/{id}` with portal session |

Logger namespace: `operations_hub`.

---

## 5. Dedup audit

| Layer | Behavior on repeat |
|---|---|
| `sla_breached_at` write-once | `apply_sla_to_ticket` only sets when falsy |
| Emit idempotency | `emit_customer_sla_breach_event` returns if any `tipo=sla_breach` exists |
| Transition gate | `newly_breached` only when `not was_breached and t.sla_breached_at` |
| Claim | `claim_ticket_event_push` requires `push_claimed_at IS NULL` |

| Scenario | Result |
|---|---|
| `refresh_tickets_sla` repeated | No second transition → no second emit |
| `ensure_ticket_sla` repeated | Same |
| Event processing / detector repeated | Claim → `already_claimed` → 0 second Expo attempt |
| Retry after successful claim | SUPPRESS duplicate |

---

## 6. Device / token

Unchanged policy from 2.3G-B / `app_push.py`:

- `PortalDevice.activo == "Sí"`
- Valid Expo token list for ticket owners
- Payload `channelId=eko`
- `DeviceNotRegistered` → deactivate token
- Transient / 5xx / timeout → **no** deactivate
- Permanent invalid → deactivate; claim already taken (attempt counted, not false success for business)

---

## 7. Mobile

Verified (read-only):

- Payload: `{ tipo: "ticket", ticket_id, event: "sla_breached" }`
- `CanonicalTicketEvent` includes `sla_breached`
- Deep-link: existing Activity (`pushFocusTicketId` / `focusTicketId`)
- Ticket body: authenticated GET portal — push is not SoT
- No new screen / navigation route for SLA

---

## 8. Safe production smoke

```text
SAFE_SMOKE = NOT_AVAILABLE
```

**Why:** There is no existing controlled harness that can create an authoritative SLA breach **without** either:

- waiting a full SLA window (minimum policy hours: 4h crítico / 8h N2 / 24h N1), or
- forbidden interventions (manual UPDATE of `sla_breached_at`, INSERT of `TicketEvent`, manual push/claim, mass refresh/backfill).

No dedicated staging smoke script covers customer SLA-breach push. Phase-1 smoke scripts do not exercise this path.

**Ops path (future, not executed in 2.6B):** staging + internal abonado + PortalDevice + create ticket via product API + wait past `sla_due_at` + single ticket GET/list to trigger ensure/refresh + observe device. Must not run against real customer tickets in prod as “activation”.

```text
Smoke this audit: NOT EXECUTED
```

---

## 9. Production safety (this audit)

Confirmed for this 2.6B session:

- [x] No real SLA breaches generated
- [x] No customer tickets modified
- [x] No real Expo pushes sent
- [x] No backfill / mass refresh
- [x] No ownership / billing / commercial / 2.5 changes
- [x] Code changes: **NONE** (documentation only)

---

## 10. Risk review

| ID | Classification | Note |
|---|---|---|
| L-01 | ACCEPTED | Detection on refresh/ensure; same as ops email path; no new scheduler |
| L-02 | ACCEPTED | Persist before emit; no auto-retry; documented; not mitigated in 2.6B |
| L-03 | ACCEPTED | Factual copy; product choice |
| L-04 | ACCEPTED | Write-once breach; one customer event by design |

No BLOCKER found.

---

## 11. Activation checklist (when ops chooses)

1. Deploy backend → restart API.
2. Ship mobile build with `sla_breached` allowlist; ensure devices update.
3. Do **not** mass-refresh open tickets.
4. Prefer staging controlled natural breach before prod exposure.
5. Monitor `operations_hub` logs for `ticket_proactive` / `ticket_push` / `Fallo emit SLA breach customer push`.

---

## 12. Tests run (regression only)

See session evidence: 2.6A, 2.3D, 2.3E, 2.3G-B, portal tickets, CASI, 2.5C, 2.5D-1..4, `npm run test:push`. Ruff on relevant Python (read-only — no modified app code in 2.6B).

---

**FINAL:** `EKO 2.6B — PRODUCTION READY / SMOKE PENDING`
