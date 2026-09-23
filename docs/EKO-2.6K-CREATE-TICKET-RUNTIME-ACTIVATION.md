# EKO 2.6K — Create Ticket Runtime Activation

**Date:** 2026-09-23  
**Mode:** MINIMAL ACTIVATION — no new executor / Event / path  

---

## 1. Estado previo (2.6J)

```text
create_ticket = AGENTIC_READY_SMALL_GAP
```

Ya existían (verificados contra código):

| Pieza | Estado |
|---|---|
| ActionSpec + `confirmation_required=True` | YES |
| Capability contract | YES |
| Coverage `EXECUTED_BY_RUNTIME` | YES (N1 wire `_ticket_via_runtime_o_legacy`) |
| Policy + TrustedContext confirmation | YES |
| Executor `_exec_create_ticket` → `_crear_ticket_n2` | YES |
| Event `creacion` Sí → 2.3G-B `ticket.created` | YES |
| XOR when covers | YES (4C/4D) |
| Default `ACTION_RUNTIME_ACTIONS` | **NO** — gap |

Master `ACTION_RUNTIME_ENABLED` default **false** (rollout oficial; no inventado).

---

## 2. Gap exacto

Único gap de activación allowlist:

```text
create_ticket ∉ default ACTION_RUNTIME_ACTIONS
```

Consecuencia: aunque `ENABLED=true`, sin listar la action en CSV/env el Runtime no cubría `create_ticket` y N1 usaba Legacy `_crear_ticket_n2` directo.

No faltaba executor, Event ni detector.

---

## 3. Cambio realizado

**`app/config.py`** — agregar `"create_ticket"` al frozenset default de `ACTION_RUNTIME_ACTIONS`.

**Comentarios / metadata:**

- `eko_action_coverage` feature_gate/notes → 2.6K default ACTIONS  
- `eko_capability_contract` notes → 2.6K  

**Tests obsoletos** que afirmaban “create_ticket no está en default” → actualizados (2.6G assert, F7-02).

**No** se cambió:

- `ACTION_RUNTIME_ENABLED` (sigue default false)  
- executor / repository / Event / 2.3G-B  
- `ticket_customer_note`, Billing, 2.5, update/close/escalate  

---

## 4. Runtime path

```text
N1 → Proposal → Policy → Confirmation → Runtime → create_ticket → TicketEvent(creacion)
```

Detalle:

```text
abonado intent / escape
  → _ticket_via_runtime_o_legacy
  → action_runtime_covers("create_ticket")  # ENABLED ∧ ACTIONS
  → dispatch_runtime
  → evaluate_policy → NEEDS_CONFIRMATION | ALLOW | DENY
  → trusted user confirm (sí / pending)
  → _exec_create_ticket
  → _crear_ticket_n2 (único writer)
  → Ticket + TicketEvent(tipo=creacion, visible=Sí)
  → maybe_deliver_ticket_event_push → ticket.created
```

---

## 5. Confirmation

Intacta:

- Sin confirmación trusted → `needs_confirmation`, **0** writes  
- Con pending + «sí» / `confirmation_received` → Runtime create  
- LLM no puede inyectar `confirmation` (sanitize + TrustedContext)

---

## 6. Ownership

- `requires_abonado` + Policy `missing_abonado`  
- Writer usa abonado/línea/conv TrustedContext  
- Params LLM `client_number` / `abonado_id` / `actor` sanitizados  

---

## 7. CASI

| | |
|---|---|
| LLM propone `create_ticket` + motivo | PASS |
| LLM no fuerza ownership/visibility/notify/actor/confirm | PASS |
| Policy + Motor + Runtime autoridad | PASS |

**CASI: PASS**

---

## 8. Runtime XOR Legacy

| Gate | Comportamiento |
|---|---|
| `ENABLED=true` + ACTIONS (default ahora incluye create) | Runtime ON → 1× `_crear_ticket_n2` vía executor; rama Legacy del helper **no** corre |
| `ENABLED=false` | Legacy only → 1× `_crear_ticket_n2`; `dispatch` no llamado |

```text
Runtime = ON  → Legacy dual = 0
```

(when covers; proven 2.6K XOR tests + prior 4D)

---

## 9. TicketEvent

Sin cambio de contrato:

- `tipo=creacion`, `visible_cliente=Sí`  
- map → `ticket.created`  
- Un Event por create (idempotency `conv.ticket_id` → `already_done` evita segundo write)

---

## 10. Proactive chain

Reutiliza 2.3G-B existente. `creacion` **sí** está mapeada a push `ticket.created` (si policy/ownership/devices permiten). Sin detector nuevo.

---

## 11. Idempotency findings

| Caso | Comportamiento |
|---|---|
| `conv.ticket_id` ya set | `already_done` — no segundo Ticket |
| Mismo detalle creacion | un Event por create del writer |
| Push | claim `push_claimed_at` (notif dedup ≠ write idempotency) |

**GAP documentado (no nuevo):** no hay idempotency key de propuesta LLM más allá de `conv.ticket_id` / Event id — suficiente para N1 conversation-bound create.

---

## 12. Tests

| Suite | Result |
|---|---|
| `tests/test_eko_create_ticket_runtime_2_6k.py` | **PASS (15)** |
| 2.6I note | PASS |
| 2.6E/G | PASS |
| 2.3G-B / 2.3D / 2.3E | PASS |
| 4C / 4D (excepto PPPoE known) | PASS |
| 4E | PASS |
| production activation F7 | PASS |
| Billing 2.1 | PASS |
| portal tickets | PASS |
| escalate_authority | PASS |

---

## 13. Ruff

PASS (módulos tocados).

---

## 14. Known unrelated failures

```text
test_4c_explicit_pppoe_exactly_one_reader
test_4d_explicit_pppoe_one_reader
```

Diagnóstico PPPoE / service selection — **ajenos**; no corregidos.

---

## 15. Limitations

- Producción sigue requiriendo `ACTION_RUNTIME_ENABLED=true` (master off por defecto).  
- Sin ENABLED, Legacy create sigue siendo el hot path (XOR correcto).  
- No se activaron `update_ticket` / `escalate_human` / `close_conversation`.  
- Smoke productivo: NOT VERIFIED (no requerido para PASS de activación).  
- Event→push tx window: DEFERRED (2.6F).

---

## 16. Final status

```text
create_ticket = AGENTIC_READY
```

```text
EKO 2.6K — CREATE_TICKET RUNTIME ACTIVATION COMPLETE
```

**Runtime trace:**

```text
N1 → Proposal → Policy → Confirmation → Runtime → create_ticket → TicketEvent(creacion)
```

**XOR:** `Runtime = ON` → `Legacy = 0` (dual)  
**CASI:** PASS  
**Note 2.6I:** sin regresión  
