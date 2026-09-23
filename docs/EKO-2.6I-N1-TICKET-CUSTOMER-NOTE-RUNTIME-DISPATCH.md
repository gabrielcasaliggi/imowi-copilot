# EKO 2.6I — N1 Ticket Customer Note Runtime Dispatch

**Date:** 2026-09-23  
**Mode:** IMPLEMENTATION (wire only — no new capability / executor / push pipeline)

---

## 1. Status

```text
EKO 2.6I — PASS
```

---

## 2. Previous State

After **2.6H** (Agentic Ops discovery):

| Piece | State |
|---|---|
| Capability `ticket_customer_note` | Registered + executor (`_exec_ticket_customer_note`) |
| Default `ACTION_RUNTIME_ACTIONS` | Includes `ticket_customer_note` (2.6G) |
| Agent API | Shared `emit_ticket_customer_note` |
| Coverage | `RUNTIME_EXECUTOR_ONLY` — **no N1 call site** |
| N1 journeys / canal | Only `show_ticket` (and evidence via `_append_evidencia_ticket` / `update_ticket`) |

**Gap:** N1 could not dispatch the existing Runtime ACT. Missing wire only.

---

## 3. Implemented Wire

```text
mensaje N1 (frase nota)
  → detect journey ticket_consulta / canal phrase gate
  → ActionRequest(ticket_customer_note, {ticket_id, mensaje})
  → Policy (evaluate_policy → ALLOW | NEEDS_INPUT | DENY)
  → Conversation Motor / Journey turn
  → Runtime dispatch_runtime → _exec_ticket_customer_note
  → emit_ticket_customer_note
  → TicketEvent(tipo=nota, visible_cliente=Sí)
  → detector 2.3G-B (maybe_deliver_ticket_event_push)
  → proactive policy / claim / Expo (suppressed if actor=abonado*)
  → mobile (unchanged)
```

**Call sites:**

1. `eko_journeys._advance_ticket` → `_advance_ticket_customer_note` when `_wants_ticket_customer_note`
2. `canal_abonado` phrase gate (when journeys off / fall-through) — same Runtime path

**Forbidden path (not implemented):**

```text
N1 → repository.add_ticket_event → push   # bypass Policy/Runtime
```

---

## 4. Authority

| Step | Authority |
|---|---|
| Intent / phrase / LLM proposal | Content only (non-authoritative) |
| Ticket id | TrustedContext (`conv.ticket_id`), UUID in text, or single visible ticket |
| Ownership | `ticket_pertenece_abonado` inside Runtime executor |
| Visibility | Hardcoded `Sí` in `emit_ticket_customer_note` (ACT name) |
| Notify / push | Detector + self-note suppress (`abonado*`) |
| Actor | Runtime: `abonado:{id}` from TrustedContext |
| Policy / Runtime | Sole execution authority |

LLM-injected keys stripped: `visible_cliente`, `notify`, `push`, `actor`, `ownership`, `agent_authorized`, `tipo`, `event_type`, …

---

## 5. Ownership

- Own ticket → Policy ALLOW → Runtime success  
- Foreign ticket_id (no conv ownership link) → DENY `foreign_ticket`  
- No ticket / zero visibles → NEEDS_INPUT `missing_ticket`  
- Multiple visibles without selection → NEEDS_INPUT `ambiguous_ticket`  
- LLM cannot set `abonado_id` / `ownership` / `actor`

---

## 6. Separation

| Capability | Effect |
|---|---|
| `ticket_customer_note` | Customer-visible `TicketEvent(nota, Sí)` + proactive path |
| `update_ticket` | `_append_evidencia_ticket` only — **no** customer `nota`, **no** push |

Not merged. Coverage: note = `EXECUTED_BY_RUNTIME`; update = `RUNTIME_EXECUTOR_ONLY`.

---

## 7. CASI

| Claim | Result |
|---|---|
| LLM may propose `ticket_customer_note` | PASS |
| LLM cannot force `visible_cliente` | PASS (sanitized; emit always Sí) |
| LLM cannot force `notify` | PASS |
| LLM cannot override ownership | PASS |
| LLM cannot write TicketEvent / call push | PASS (proposal-only) |
| Policy/Runtime remain authority | PASS |

---

## 8. XOR

When `action_runtime_covers("ticket_customer_note")`:

- Exactly one `dispatch_runtime` per N1 intent  
- Exactly one customer `nota` Event (idempotent by detalle hash)  
- At most one push attempt (N1 abonado → 0 via SELF_NOTE_NO_PUSH)

When gate **off**:

- Status `unavailable` / honest message  
- **No** Legacy `add_ticket_event` with `visible_cliente=Sí`

---

## 9. Tests

| Suite | Result |
|---|---|
| `tests/test_eko_n1_ticket_customer_note_2_6i.py` | PASS (20) |
| 2.6E (`test_eko_ticket_customer_note_2_6e`) | PASS |
| 2.3G-B | PASS |
| 2.3D / 2.3E | PASS |
| 2.6A | PASS |
| CASI (`test_final_authority_audit`, `test_resolved_authority`, 2.5C CASI cases) | PASS |
| portal tickets | PASS |
| helpdesk | PASS |
| 4E | PASS |
| 2.5C / 2.5D-1..4 | PASS |
| Billing 2.1 | PASS |
| Ruff (touched) | PASS |
| `npm run test:push` (mobile) | PASS |
| Known unrelated: `test_4b_explicit_diagnostic_invokes_reader_when_selected` | FAIL (unchanged; not fixed) |

---

## 10. Mobile

**No changes.** Push payload / Activity navigation untouched. `test:push` OK.

---

## 11. Deferred

| Item | Status |
|---|---|
| Event commit → push failure transaction window | DEFERRED (2.6F) |
| Production smoke | UNAVAILABLE / not required for PASS |
| Activity real device | NOT VERIFIED |
| Confirmation for note | NOT_REQUIRED (reused; no new confirm UX) |

**Idempotency:** existing detalle-hash on `emit_ticket_customer_note` — no new system.

---

## 12. Final Gate

```text
EKO 2.6I — PASS
```
