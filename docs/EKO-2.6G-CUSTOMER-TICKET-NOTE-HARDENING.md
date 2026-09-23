# EKO 2.6G — Customer Ticket Note Hardening

**Status:** PASS  
**Date:** 2026-09-23  
**Upstream:** 2.6E PASS · 2.6F PASS WITH FINDINGS  
**Scope:** Hardenings only — no new capability, no Outbox, no smoke  

---

## 1. Status

```text
PASS
```

---

## 2. Findings addressed

| Finding (2.6F) | Resolution |
|---|---|
| MEDIUM — ACT fuera de default `ACTION_RUNTIME_ACTIONS` | `ticket_customer_note` añadido al **set default** (no CSV bypass; no se agregaron otros mutadores) |
| LOW — emit confía en caller ownership | Ownership defensivo: `abonado` → `ticket_pertenece_abonado` **o** `agent_authorized=True`; si no → DENY |
| LOW — default `add_ticket_event` = Sí | Default global → **`No`**; callers customer-visible pasan `Sí` explícito; internos pasan `No` explícito |

---

## 3. Changes

| File | Change |
|---|---|
| `app/config.py` | default `ACTION_RUNTIME_ACTIONS` includes `ticket_customer_note` |
| `app/services/eko_ticket_proactive.py` | defensive ownership on emit |
| `app/services/eko_action_runtime.py` | pass `abonado=` to emit |
| `app/api/v1/tickets.py` | `agent_authorized=True` on agent note |
| `app/estate/repository.py` | default `visible_cliente="No"`; `creacion` explícito `Sí` |
| `app/services/seguimiento_ticket.py` | `visible_cliente="No"` explícito |
| `app/services/ticket_contexto.py` | idem |
| `app/estate/learning_loop.py` | idem |
| `app/services/encuesta_satisfaccion.py` | idem |
| `app/services/eko_action_coverage.py` | notes / feature_gate |
| `app/services/eko_capability_contract.py` | notes |
| `tests/test_eko_ticket_customer_note_2_6e.py` | ownership args + 2.6G tests |

**Mobile:** NONE  

---

## 4. Action Runtime Enforcement

```text
ACTION_RUNTIME_ENABLED (master)
  AND ticket_customer_note ∈ ACTION_RUNTIME_ACTIONS (default set)
  → action_runtime_covers("ticket_customer_note") == True
```

- Sin bypass especial ni `if` exclusivo fuera del frozenset.
- `update_ticket` / `create_ticket` **siguen fuera** del default.
- Cadena: Policy → Runtime → emit (sin cambio de contrato).

---

## 5. Ownership

```text
emit_ticket_customer_note(..., abonado=TrustedAbonado)
  → ticket_pertenece_abonado  (N1 Runtime)

emit_ticket_customer_note(..., agent_authorized=True)
  → ticket exists in org     (API agente post-RBAC)

else → None (0 Event, 0 push)
```

Misma autoridad canónica; no segunda lógica paralela.

---

## 6. TicketEvent Visibility

| Caller | visible |
|---|---|
| Default `add_ticket_event` | **No** |
| `creacion` / ACT nota / SLA / cierre | **Sí** explícito |
| Admin actualizacion / reasignacion / internas | **No** explícito |

---

## 7. CASI

Sin cambios de sanitize. LLM sigue sin autoridad sobre `visible_cliente` / `notify` / identity.  
`LLM content != authority` — **PASS**.

---

## 8. Tests

Ver sesión: suite 2.6E/G ampliada + regresiones listadas en §9.

---

## 9. Deferred Findings (from 2.6F — unchanged)

```text
2.6F MEDIUM — EVENT/PUSH TRANSACTION WINDOW: DEFERRED
SMOKE NOT AVAILABLE
Activity real device: NOT VERIFIED
```

---

## 10. Regression

2.5 / CASI / Billing / proactive created-closed-SLA / outage — suites ejecutadas en verde (ver informe final).  
PRE-EXISTING: `test_4b_explicit_diagnostic_invokes_reader_when_selected` — no tocado.

---

## 11. Final Gate

```text
EKO 2.6G — PASS
```
