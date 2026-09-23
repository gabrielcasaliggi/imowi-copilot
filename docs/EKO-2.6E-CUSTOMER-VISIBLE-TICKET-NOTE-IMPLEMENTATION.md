# EKO 2.6E — Customer-Visible Ticket Note Implementation

**Status:** PASS  
**Date:** 2026-09-23  
**Contract:** `docs/EKO-2.6D-CUSTOMER-VISIBLE-TICKET-UPDATE-CONTRACT.md`  
**Preserves:** 2.5 FROZEN, CASI, Billing, Commercial, SLA/2.6A, 2.6B, mobile event taxonomy  

---

## 1. Implementation summary

Implemented the sole customer-visible act `ticket_customer_note`:

```text
ticket_customer_note
  → TicketEvent(tipo=nota, visible_cliente=Sí, detalle=mensaje safe)
  → existing detector → policy → ownership → claim → Expo
  → mobile event=updated (fixed copy)
  → GET /portal/tickets/{id}
```

N1 `update_ticket` remains **internal evidence only** (no Event, no push).  
Admin auto-updates default `visible_cliente=No` (closure preserved `Sí`).  
Reassignment `visible_cliente=No`. Self-note (actor `abonado*`) → Event yes, push SUPPRESS.

---

## 2. Files changed

| Path | Change |
|---|---|
| `app/services/eko_ticket_proactive.py` | `emit_ticket_customer_note`, portal allowlist, self-note suppress |
| `app/services/eko_action_runtime.py` | `_exec_ticket_customer_note`, registry, sanitize visibility keys |
| `app/estate/repository.py` | `update_ticket` visibility hardening |
| `app/api/v1/portal.py` | projection via `is_portal_customer_event` |
| `app/api/v1/tickets.py` | agent note → emit helper; reassign note → interna |
| `app/services/eko_action_coverage.py` | coverage row |
| `app/services/eko_capability_contract.py` | capability meta |
| `app/config.py` | comment only |
| `tests/test_eko_ticket_customer_note_2_6e.py` | new suite |
| `tests/test_eko_agentic_capabilities_4e.py` | capability_count 15→16 |

**Mobile:** NONE  

---

## 3. `ticket_customer_note` flow

```text
Policy/Motor → Runtime._exec_ticket_customer_note
  → ticket_pertenece_abonado
  → emit_ticket_customer_note (idempotent by detalle)
  → add_ticket_event
  → maybe_deliver_ticket_event_push
       self-note → SELF_NOTE_NO_PUSH
       agent note → ticket.updated → Expo
```

Agent console `POST /tickets/{id}/events` with `interno=false` uses the same emit helper.

---

## 4. `update_ticket` separation

Confirmed: `_exec_update_ticket` → `_append_evidencia_ticket` only.  
No TicketEvent. No `ticket.updated`. No push.

---

## 5. Admin visibility hardening

| Auto-event | `visible_cliente` |
|---|---|
| Field `actualizacion` (non-close) | **No** |
| `reasignacion` | **No** |
| Close (`estado=Cerrado`) | **Sí** (preserves `ticket.closed`) |
| Create / SLA / ACT nota | Unchanged |

---

## 6. Reassignment

New events: `tipo=reasignacion`, `visible=No`, denylist push, portal projection excludes.  
Derivation notes: `nota_interna` + `No`.

---

## 7. Materiality

| Act | Timeline | Push |
|---|---|---|
| Agent/ops `nota` | Yes | Yes (`updated`) |
| N1 self-note (`actor=abonado…`) | Yes | **No** |
| Evidence `update_ticket` | No | No |
| Admin field update | No | No |

---

## 8. Push reuse

```json
{ "tipo": "ticket", "ticket_id": "...", "event": "updated" }
```

Fixed `_TICKET_COPY["ticket.updated"]`. Payload never includes `TicketEvent.detalle`.

---

## 9. Portal projection

`is_portal_customer_event`: allowlist `{creacion, nota, sla_breach}` + `actualizacion` only if `estado=Cerrado`.  
Excludes reasignacion / admin actualizacion / interna. No historical migration.

---

## 10. Ownership

Same `ticket_pertenece_abonado` as `update_ticket`. Foreign → DENY, no Event.

---

## 11. CASI

- LLM proposal may name the action; sanitize strips `visible_cliente` / `notify` / identity keys.
- Effect only via Runtime after Policy.
- LLM cannot create Event, set visibility, or push.

---

## 12. Tests

`tests/test_eko_ticket_customer_note_2_6e.py` — 16 cases (note, push, self-note, ownership, update separation, admin/reassign/close, portal, CASI sanitize, idempotency, claim).

---

## 13. Known unrelated failure

```text
test_4b_explicit_diagnostic_invokes_reader_when_selected
needs_input vs success
```

Out of scope 2.6E — not fixed.

---

## 14. Risks / limitations

- Idempotency of ACT = identical `detalle` on same ticket (not a DB unique constraint).
- Historical `actualizacion` with `visible=Sí` may still exist in DB; portal read-filter hides non-Cerrado.
- `ticket_customer_note` not in default `ACTION_RUNTIME_ACTIONS` (same pattern as other mutators); enable via env when N1 dispatch is desired.
- Agent note title fixed to `"Actualización"` via helper.

---

## 15. Deployment considerations

- Backend deploy + API restart.
- No migration.
- No mobile build required.
- No mass backfill.
- Optional: add `ticket_customer_note` to `ACTION_RUNTIME_ACTIONS` when enabling N1 Runtime dispatch.

---

**FINAL:** `EKO 2.6E — PASS`
