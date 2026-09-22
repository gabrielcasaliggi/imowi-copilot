# EKO 2.3H — PROACTIVE END-TO-END AUDIT & CLOSURE GATE

**Status:** PASS WITH FINDING  
**Phase type:** AUDIT ONLY — no runtime changes  
**Date:** 2026-09-22  

Closed predecessors: 2.3A → 2.3G-B (incl. 2.3G-M).

---

## 1. Scope

Auditar la coherencia real de Eko Proactive tras outage + ticket:

```text
SOURCE → EVENT → POLICY → DEDUP → DELIVERY
```

Sin implementar detectores nuevos. Sin habilitar billing/payment/connectivity/service/commercial. Sin refactor.

---

## 2. Architecture trace

### Outage (production)

```text
API /outages CRUD
  → authorize_outage_push (policy)
  → deliver_proactive_push
  → notificar_incidente_* (claim outage)
  → listar_tokens_afectados_por_nas
  → enviar_push_expo { tipo:incidente, outage_id, event }
```

### Ticket (production)

```text
repository.add_ticket_event (commit)
  → maybe_deliver_ticket_event_push
  → gate + map → ProactiveEvent(ticket.*)
  → evaluate_proactive_notification
  → deliver_proactive_push
  → notificar_ticket_app
  → claim_ticket_event_push(TicketEvent.id)
  → listar_tokens_duenos_ticket
  → enviar_push_expo { tipo:ticket, ticket_id, event }
```

### Reactive (not proactive domain)

```text
inbox agent → app canal
  → notificar_conversacion_app
  → { conversacion_id / tipo:mensaje_agente }
```

**LLM:** no crea eventos, no ownership, no claims, no delivery.  
Outage `usar_ia` solo puede influir el **mensaje de presentación** del incidente; el hecho sigue siendo CRUD AUTHORITATIVE.

---

## 3. Event inventory

| Canonical | Source | Identity | occurred_at | Authority | Ownership | Gate | Dedup | Payload | Mobile | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| outage.started | NetworkOutage CRUD | outage_id | started_at | AUTHORITATIVE | NAS→abonado→device | ops declare | push_declared_at | incidente/declared | Home+refresh | **READY** |
| outage.material_update | NetworkOutage PATCH | outage_id + body fp | updated path | AUTHORITATIVE | NAS→… | material msg | push_material_fingerprint | incidente/updated | Home+refresh | **READY** |
| outage.resolved | resolve CRUD | outage_id | resolved_at | AUTHORITATIVE | NAS→… | resolve | push_resolved_at | incidente/resolved | Home+refresh | **READY** |
| ticket.created | TicketEvent tipo=creacion | TicketEvent.id | created_at | AUTHORITATIVE | portal ticket↔abonado→device | visible+allowlist | push_claimed_at | ticket/created | Activity+focus | **READY** |
| ticket.updated | actualizacion≠Cerrado \| nota | TicketEvent.id | created_at | AUTHORITATIVE | idem | visible+allowlist | push_claimed_at | ticket/updated | Activity+focus | **READY** |
| ticket.closed | actualizacion+Cerrado | TicketEvent.id | created_at | AUTHORITATIVE | idem | visible+allowlist | push_claimed_at | ticket/closed | Activity+focus | **READY** |
| ticket.resolved | — | — | — | — | — | — | — | — | (vocab only) | **UNSUPPORTED** |

---

## 4. Outage audit

| Check | Result |
|---|---|
| Authority = estate outage CRUD | PASS |
| Material fingerprint separate from declared/resolved | PASS |
| NAS ownership + multi-device | PASS |
| Token hygiene (DeviceNotRegistered → deactivate; logs = fingerprints) | PASS |
| API XOR via `deliver_proactive_push` | PASS |
| 2.3G-B did not alter outage claim fields / payload | PASS |
| AT-MOST-ONCE attempt / BEST-EFFORT receipt | PASS (documented) |

Regression suites 2.3D/E + e2/e3 + segmentación: green.

---

## 5. Ticket audit

| Check | Result |
|---|---|
| TicketEvent authoritative | PASS |
| Identity = TicketEvent.id | PASS |
| occurred_at = created_at | PASS (append time limitation documented) |
| visible_cliente + internal denylist | PASS |
| Deterministic map (no LLM / no title authority) | PASS |
| ticket.resolved unsupported | PASS |
| Ownership = portal helper (not phone-alone invent) | PASS* |
| Post-commit hook on `add_ticket_event` | PASS |
| push_claimed_at only (no outage fields) | PASS |
| same id → no second attempt | PASS (tests) |
| different ids → independent | PASS (tests) |
| Payload sin detalle interno | PASS |

\* Ownership reuses portal `ticket_pertenece_abonado` (conv.ticket_id and/or linea keys). Not LLM; not DNI-as-push-target alone — devices keyed by owner DNI after ticket ownership proven.

---

## 6. Mobile contract audit

| Backend `data` | Mobile intent |
|---|---|
| `tipo=incidente` + `outage_id` + event | Home + refreshConnectivity |
| `tipo=ticket` + `ticket_id` + event | Activity + focusTicketId → GET `/portal/tickets/{id}` |
| `mensaje_agente` / `conversacion_id` | Eko |

| Scenario | Behavior |
|---|---|
| Foreground receipt | No auto-nav (incidente may refresh connectivity only) |
| Background / cold-start tap | Same `intentFromPushData` |
| missing/malformed ticket_id | Activity list |
| foreign ticket | Portal 404; no fabricated detail |
| title/body | Presentation only; not authority |

Literal contract match: **PASS** (no BLOCKED mismatch).

---

## 7. Policy audit

Implemented stages (minimal 2.3D/G-B):

1. event_type nonempty  
2. SUPPORTED whitelist  
3. source_authority (outage/ticket require AUTHORITATIVE)  
4. channel = app_push  
5. required ids (outage_id/org or ticket_id+source_event_id+org)  
6. customer_message present (outage.resolved exempt; tickets require templates)  
7. ALLOW → adapter  

**Not separately implemented as named stages:** freshness window, cooldown beyond claims, relevance scoring.

**Bypasses found (see §18):**

| Path | Kind | Risk |
|---|---|---|
| `notificar_incidente_*` callable without policy | Residual transport API | MEDIUM |
| `notificar_ticket_app` callable without policy | Residual transport API | MEDIUM |
| `notificar_conversacion_app` from inbox | **Reactive** agent chat | LOW (by design) |
| ActionProposal / conversation_motor | N1 actions, not Expo proactive | N/A |
| telemetry `proactive` naming | Unrelated autonomy flag | N/A |

Production outage CRUD: **no** direct `notificar_incidente_*`. Ticket: only via detector → policy → adapter.

---

## 8. Dedup audit

| Domain | Mechanism | Atomic? | Semantics |
|---|---|---|---|
| outage.started | `push_declared_at IS NULL` UPDATE | Yes | AT-MOST-ONCE **attempt** |
| outage.resolved | `push_resolved_at IS NULL` | Yes | idem |
| outage.material_update | fingerprint ≠ stored | Yes | per material body |
| ticket.* | `push_claimed_at IS NULL` on TicketEvent | Yes | per TicketEvent.id |

**Not** exactly-once delivery. Crash after claim / before Expo ⇒ lost attempt (accepted).

Replay / duplicate / concurrent: winner = rowcount==1.

Provider failure after claim: no automatic retry (2.3E).

---

## 9. Failure semantics

| Condition | Expo called? |
|---|---|
| Policy deny / NOT_ELIGIBLE / INVALID | No |
| Ticket ownership unresolved (0 owners) | No (no claim) |
| Foreign device (other DNI) | Not in token list |
| Duplicate claim | No |
| Invalid token mixed with valid | Valid still sent; dead deactivated |
| Transient/timeout/unknown provider | `ok=False`; not promoted to success |

claim ≠ provider acknowledgement: **confirmed**.

---

## 10. Ownership / multi-account

| Scenario | Behavior |
|---|---|
| Multi-device same owner | All eligible tokens |
| Ticket other abonado | Not in owner set → 0 Expo to foreign |
| No resolvable owner | OWNERSHIP_UNRESOLVED |
| Phone alone as push resolver | **Not used** as sole authority; portal ticket rule may use linea keys **after** ticket association |
| LLM ownership | **None** |
| ticket_id in push as authz | **No** — mobile re-fetches with portal JWT |

---

## 11. Event / state / message findings

| Finding | Severity | Notes |
|---|---|---|
| Outage IA may draft customer_message | LOW | Presentation; event = CRUD |
| Ticket title/detalle never in Expo data | — | OK |
| `nota` → ticket.updated spam potential | MEDIUM | Product volume risk |
| invoice.date / probes not treated as events | — | Still UNAVAILABLE (2.3F) |
| Policy freshness not time-bounded | MEDIUM | Debt vs ideal 2.3C |

No CRITICAL state/event conflation in enabled paths.

---

## 12. Availability matrix

| Domain | Event | Authority | Detector | Identity | Ownership | Delivery | Status |
|---|---|---|---|---|---|---|---|
| Outage | started/material/resolved | AUTHORITATIVE | CRUD API | outage_id (+fp) | NAS | App Push | **READY** |
| Ticket | created/updated/closed | AUTHORITATIVE | add_ticket_event | TicketEvent.id | portal | App Push | **READY** |
| Ticket | resolved | — | — | — | — | — | **UNSUPPORTED** |
| Billing | due_date / payment_* / debt | — | — | — | — | — | **UNAVAILABLE** |
| Connectivity | lost/restored | STATE_ONLY | no | — | — | — | **UNAVAILABLE** |
| Service | activated/… | no writer SoT | no | — | — | — | **UNAVAILABLE** |
| Installation | * | — | — | — | — | — | **UNAVAILABLE** |
| Commercial | * | external | — | — | — | — | **EXTERNAL_DEPENDENCY** |

---

## 13. Channel matrix

| Channel | Proactive outage/ticket | Reactive |
|---|---|---|
| App Push | **Yes** (only) | Agent inbox (`mensaje_agente`) |
| WhatsApp | No proactive 2.3 | Inbox agent reply |
| Telegram | No | Inbox agent reply |
| Email | No (SLA ops email ≠ customer proactive) | — |
| SMS | No | — |

Disabled domains remain disabled in `SUPPORTED_PROACTIVE_EVENTS`.

---

## 14. Security findings

| Item | Severity |
|---|---|
| Tokens in logs as fingerprints only (caller returns fps) | OK |
| Ticket detail / DNI / account in Expo data | **Not present** |
| Foreign ticket content via push | Prevented (portal GET) |
| LLM-controlled recipient/event | **Not found** |
| Transport functions callable without policy | MEDIUM residual |

No CRITICAL/HIGH security defect found in enabled paths.

---

## 15. Database / migration audit

| Field | Table | Nature |
|---|---|---|
| push_declared_at / push_resolved_at / push_material_fingerprint | network_outages | additive (2.3D/E) |
| push_claimed_at | ticket_events | additive (2.3G-B) |

Model ↔ migrate_schema consistent. Non-destructive. Tests use create_all + columns on model.

---

## 16. Bulk edge case: `cierre_masivo`

| Question | Answer |
|---|---|
| Generates TicketEvent? | Yes (bulk `TicketEvent(...)`) |
| Via `add_ticket_event`? | **No** |
| Detector runs? | **No** |
| visible_cliente? | `"No"` |
| Customer push risk? | **None** under current gate |
| Classification | **KNOWN GAP** (safe) |

---

## 17. Test results

Executed (all green):

- `test_eko_proactive_push_2_3d`
- `test_eko_proactive_push_2_3e`
- `test_eko_ticket_proactive_2_3gb`
- `test_outage_push_e2_dedup`
- `test_outage_push_e3_updated`
- `test_outage_push_segmentacion`
- `test_portal_tickets`
- `test_helpdesk_features`
- `test_eko_billing_self_service_2_1`
- `test_eko_service_management_2_2a/b/c`
- `test_eko_conversational_hardening_6`
- `test_eko_agentic_capabilities_4e`
- mobile `npm run test:push`

**Ruff:** pass on proactive/outage/ticket touchpoints.

No new production tests added (audit-only).

---

## 18. Findings summary

### Critical / High

**None.**

### Medium

1. **Transport bypass residual:** `notificar_incidente_*` / `notificar_ticket_app` remain public; production API uses policy XOR, but a future caller could skip policy.  
2. **Policy minimal vs 2.3C ideal:** no explicit freshness/cooldown stages beyond claims.  
3. **`nota` → ticket.updated** volume / spam product risk.

### Low

1. `cierre_masivo` detector bypass (safe: not customer-visible).  
2. AT-MOST-ONCE attempt ≠ exactly-once.  
3. Mobile vocabulary includes `resolved` unused by backend.  
4. Outage message may be IA-assisted presentation only.

---

## 19. Known limitations

- No billing/connectivity/service/installation/commercial proactive.  
- ticket.resolved unsupported.  
- Bulk ticket inserts outside `add_ticket_event` not hooked.  
- No outbox / scheduler / queue / event bus (by design).

---

## 20. Final gate

**STATUS: PASS WITH FINDING**

Architecture is operationally coherent for outage.* + ticket.{created,updated,closed}.  
No critical/high unresolved issues on authority, ownership, contract, dedup integrity, or outage/ticket security.

Code modified this phase: **none**.  
Doc created: this file.

### Explicit confirmation

- Billing unchanged  
- CASI unchanged  
- SM 2.2A–C unchanged  
- Outage semantics unchanged  
- Ticket mobile contract unchanged  
- No scheduler / queue / event bus  
- No new proactive domain enabled  

**STOP.** Do not implement 2.3I or other proactive domains from this audit.
