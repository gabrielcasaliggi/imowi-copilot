# EKO 2.3G-B — TICKET PROACTIVE EVENT DETECTOR & PUSH RUNTIME

**Status:** PASS  
**Depends on:** 2.3G-M PASS (mobile `tipo=ticket` contract)  
**Enables:** customer-visible ticket proactive push only  

---

## 1. Architecture

```text
add_ticket_event (commit)
  → maybe_deliver_ticket_event_push
  → is_ticket_event_customer_visible + map_ticket_event_type
  → ProactiveEvent(ticket.*)
  → evaluate_proactive_notification
  → deliver_proactive_push
  → notificar_ticket_app
  → claim_ticket_event_push(TicketEvent.id)
  → listar_tokens_duenos_ticket (portal ownership)
  → enviar_push_expo { tipo:ticket, ticket_id, event }
```

No scheduler / queue / event bus. Same delivery boundary as outages.

---

## 2. TicketEvent source

`estate.ticket_events` via `repository.add_ticket_event` (unique ORM writer for normal paths).

Bulk `cierre_masivo` inserts bypass the hook (`visible_cliente=No`) — documented limitation.

---

## 3. Canonical events enabled

| Canonical | Mapping | Mobile `event` |
|---|---|---|
| `ticket.created` | `tipo=creacion` | `created` |
| `ticket.updated` | `tipo=actualizacion` (estado ≠ Cerrado) or `tipo=nota` | `updated` |
| `ticket.closed` | `tipo=actualizacion` + `estado=Cerrado` | `closed` |
| `ticket.resolved` | **UNSUPPORTED** | — |

`ESTADOS_TICKET_VALIDOS` = Abierto | En Revisión | Cerrado — no Resuelto.

---

## 4. Customer-visible gate

1. `visible_cliente` ∈ {Sí, si, yes, true, 1}
2. `tipo` ∉ internal set:  
   `nota_interna`, `reasignacion`, `paso_operativo`, `resumen_noc`,  
   `kb_*`, `aprendizaje`, `csat_bajo`, `contexto_sms`, `cierre_masivo`
3. `map_ticket_event_type` must return an enabled canonical type

No LLM. No inference from titulo/detalle.

---

## 5. Ownership

Reuses `ticket_pertenece_abonado` / conversación.ticket_id / Ticket.linea.

Devices: `PortalDevice` by `dni_normalized` of owner abonados.

Unresolved owners → `OWNERSHIP_UNRESOLVED`, **zero Expo**, no claim burned.

Foreign abonado devices never targeted.

---

## 6. Detector hook

Post-`db.commit()` / `refresh` inside `add_ticket_event`.  
Push failures do not roll back the TicketEvent.

---

## 7. Dedup

Column: `ticket_events.push_claimed_at`  
`claim_ticket_event_push(event_id)` — conditional UPDATE.

**Does not** use `push_declared_at` / `push_resolved_at` / material fingerprint.

Same `TicketEvent.id` → at most one attempt.  
Different ids on same ticket → independent.

---

## 8. Push payload (2.3G-M)

```json
{ "tipo": "ticket", "ticket_id": "<id>", "event": "created|updated|closed" }
```

Title/body = deterministic Spanish presentation only.  
No TicketEvent.detalle / notas / datos internos en `data`.

---

## 9. Outage

Unchanged path: NAS fanout + outage claims + `tipo=incidente`.

---

## 10. Files

| Path | Role |
|---|---|
| `app/services/eko_ticket_proactive.py` | gate + map + detector |
| `app/services/eko_proactive_contract.py` | ticket.* in SUPPORTED |
| `app/services/eko_proactive_policy.py` | ticket ownership fields |
| `app/services/eko_proactive_push.py` | ticket branch |
| `app/services/app_push.py` | `notificar_ticket_app` + tokens |
| `app/estate/models.py` | `push_claimed_at` |
| `app/estate/migrate.py` | additive column |
| `app/estate/repository.py` | hook + claim |
| `tests/test_eko_ticket_proactive_2_3gb.py` | matrix |
| `docs/EKO-2.3G-B-TICKET-PROACTIVE-EVENT-DETECTOR.md` | this doc |

---

## 11. Limitations

1. `ticket.resolved` not enabled (no Resuelto state).
2. Bulk `TicketEvent(...)` inserts (cierre masivo) skip detector.
3. Claim before successful Expo receipt = AT-MOST-ONCE attempt / BEST-EFFORT receipt (same as 2.3E).
4. `occurred_at` = `TicketEvent.created_at` (append time).

---

## 12. Explicit confirmations

Billing / CASI / SM 2.2 / outage semantics unchanged.  
No scheduler/queue/event bus.  
Mobile unchanged in this phase (2.3G-M already PASS).
