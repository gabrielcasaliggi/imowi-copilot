# EKO 2.6F — Production Readiness & Controlled Smoke Audit

**Date:** 2026-09-23  
**Scope:** EKO 2.6E Customer-Visible Ticket Note only  
**Mode:** AUDIT ONLY — zero production code changes  

---

## 1. Executive Status

```text
PASS WITH FINDINGS
```

Implementación 2.6E **técnicamente verificada** (código + tests): autoridad CASI, separación `update_ticket` / `ticket_customer_note`, hardening de visibilidad admin, self-note sin push, pipeline 2.3G-B reutilizado, mobile sin cambios.

**No** hay smoke productivo seguro disponible. Activación N1 Runtime requiere listar `ticket_customer_note` en `ACTION_RUNTIME_ACTIONS` (no está en el set default). Evidencia operacional en producción: **NOT VERIFIED**.

---

## 2. Scope

Auditado:

- Acto `ticket_customer_note` y helper `emit_ticket_customer_note`
- Separación N1 `update_ticket` → evidencia interna
- Hardening `repo.update_ticket` / reasignación / cierre
- Detector 2.3G-B / push `ticket.updated`
- Ownership / dedup / transacciones / portal
- CASI sanitize
- Regresiones 2.3 / 2.5 / 2.6A / Billing 2.1 / mobile push verify
- Smoke availability (sin ejecutar)

No auditado operacionalmente: staging/prod live, Expo real, Activity cold-start en dispositivo físico.

---

## 3. Expected Architecture

```text
LLM / proposal (content only)
  → Policy
  → Conversation Motor / Runtime
  → ticket_customer_note (_exec_ticket_customer_note)
  → emit_ticket_customer_note
  → TicketEvent(tipo=nota, visible_cliente=Sí)
  → add_ticket_event COMMIT
  → maybe_deliver_ticket_event_push (post-commit)
  → map → ticket.updated
  → [self-note? SUPPRESS]
  → evaluate_proactive_notification
  → deliver_proactive_push
  → ownership → claim → Expo
  → mobile {tipo:ticket, event:updated}
  → Activity → GET /portal/tickets/{id}
```

Agente paralelo (autorizado, no LLM):

```text
POST /tickets/{id}/events interno=false
  → emit_ticket_customer_note(actor=email agente)
  → misma cadena (push ALLOW si ownership)
```

---

## 4. Authority Audit

| Area | Expected authority | Result | Evidence |
|---|---|---|---|
| Act explícito | `ticket_customer_note` registered | **PASS / VERIFIED** | `eko_action_runtime.py` ActionSpec + `_exec_ticket_customer_note` |
| Customer-visible write | Runtime/agent → `emit_ticket_customer_note` only (for ACT) | **PASS / VERIFIED** | emit hardcodes `tipo=nota`, `visible_cliente=Sí`; no param de visibilidad |
| N1 `update_ticket` | Evidence only | **PASS / VERIFIED** | `_exec_update_ticket` → `_append_evidencia_ticket`; tests 2.6E |
| LLM visibility/notify | Sanitized out | **PASS / VERIFIED** | `_UNTRUSTED_PARAM_KEYS` includes `visible_cliente`, `notify`, identity keys |
| LLM → Event/push direct | Forbidden | **PASS / VERIFIED** | `parse_llm_action_proposal` + `execute_action` policy gate; no repo from LLM |
| Ownership | Trusted abonado + `ticket_pertenece_abonado` | **PASS / VERIFIED** | executor; foreign DENY |
| CASI chain | Policy → Runtime → adapter | **PASS / VERIFIED** | `execute_action` único entry |

**AUTHORITY: PASS**

Finding (Low): `emit_ticket_customer_note` no revalida ownership internamente; confía en el caller (Runtime / API agente). Defensa en profundidad no duplicada — aceptable si callers permanecen gated.

Finding (Medium — activation): `ticket_customer_note` **no** está en `ACTION_RUNTIME_ACTIONS` default (`app/config.py`). Igual que otros mutadores. N1 dispatch productivo requiere env explícito. **DOCUMENTED**; no es bypass.

---

## 5. Customer-Visible Semantics

| Regla | Result | Evidence class |
|---|---|---|
| ACT → `nota` + `Sí` | VERIFIED | emit + tests |
| Mensaje = input sanitizado (max 800), no campos Ticket | VERIFIED | `sanitize_customer_note_message` |
| Admin `actualizacion` no-cierre → `No` | VERIFIED | `repository.update_ticket` |
| `reasignacion` → `No` | VERIFIED | same |
| Cierre → `Sí` + `ticket.closed` | VERIFIED | update_ticket + test_26e_closed |
| Derivación → `nota_interna` + `No` | VERIFIED | `tickets.py` reassign |
| Portal allowlist | VERIFIED | `is_portal_customer_event` |
| Históricos `actualizacion` Sí no-Cerrado | DOCUMENTED mitigation | filtro de lectura portal; sin migration |

**Alternate paths to customer-visible `nota`:**

1. Runtime `ticket_customer_note` — intended  
2. Agent `POST .../events` `interno=false` → emit — intended  
3. Direct `repo.add_ticket_event(tipo=nota, …)` desde otros módulos — **NOT VERIFIED** como uso actual con `nota`; otros writers usan tipos denylist (`paso_operativo`, `csat_bajo`, …). Residual: default `visible_cliente="Sí"` en `add_ticket_event` sigue existiendo para callers futuros.

---

## 6. Ownership

| Case | Expected | Result |
|---|---|---|
| Own ticket | ALLOW Event (+ push si no self) | VERIFIED (tests) |
| Foreign | DENY, 0 Event, 0 push | VERIFIED |
| Missing abonado | DENY | VERIFIED |
| Unresolved devices | Event may exist; 0 push / OWNERSHIP_UNRESOLVED | VERIFIED (infra 2.3G-B) |
| LLM-supplied ownership | Stripped | VERIFIED |

Cadena push: Ticket → `ticket_pertenece_abonado` → DNI → PortalDevice → Expo — **VERIFIED** en código `app_push.listar_tokens_duenos_ticket`.

---

## 7. Dedup

| Layer | Mechanism | Result |
|---|---|---|
| ACT idempotency | Same ticket + `tipo=nota` + identical `detalle` → return existing Event | VERIFIED |
| Push | `TicketEvent.id` + `push_claimed_at` atomic claim | VERIFIED |
| Retry detector | `already_claimed` → 0 second Expo | VERIFIED (2.3G-B + 2.6E) |

**Max Expo attempts per Event.id:** AT-MOST-ONCE attempt — **VERIFIED** in tests (mocked Expo).

Limitation (DOCUMENTED): idempotency de negocio no es constraint DB UNIQUE; es query previa.

---

## 8. Transaction Boundaries

```text
emit → add_ticket_event:
  db.add(Event) → COMMIT Event
  → post-commit maybe_deliver_ticket_event_push
       → claim COMMIT (push_claimed_at)
       → Expo HTTP
```

| Failure | Outcome | Class |
|---|---|---|
| Event commit fails | No Event, no push | VERIFIED (code path) |
| Detector exception | Event persists; push skipped; logged | VERIFIED |
| Ownership fail before claim | Event persists; 0 push; claim not burned | VERIFIED (2.3G-B) |
| Claim lose race | 0 second attempt | VERIFIED |
| Expo fail / transient / invalid token | Claim already taken; hygiene per 2.3 | VERIFIED (existing) |
| Process death after Event commit before push | **persistido pero no notificado** | DOCUMENTED residual (same class as 2.6B L-02 pattern) |
| Notified without Event | **No path observed** (push after commit) | VERIFIED |

---

## 9. Mobile Contract

| Item | Result |
|---|---|
| Payload `tipo=ticket`, `event=updated` | VERIFIED (tests + `_payload_ticket_seguro`) |
| Fixed copy; no `detalle` in data/body for note path | VERIFIED (2.6E tests) |
| Mobile code change for 2.6E | **NONE** |
| `npm run test:push` | PASS |
| Physical Activity / cold-start | **NOT VERIFIED** (no device audit this phase) |

**MOBILE CONTRACT: PASS** (contract + unit verify; device UX not operationally verified)

---

## 10. Portal Projection

| Check | Result |
|---|---|
| Auth JWT + ownership on GET | VERIFIED (`portal_get_ticket`) |
| `nota` Sí in allowlist | VERIFIED |
| Admin actualizacion / reasignacion / interna excluded | VERIFIED |
| Foreign ticket 404 | VERIFIED (portal tests) |
| Nota detalle exposed to owner | VERIFIED (by design — customer-safe message) |
| Operational detalle on new admin events | Mitigated (`visible=No` + filter) |

---

## 11. CASI

| Check | Result |
|---|---|
| Sanitize strips visibility/notify/identity | VERIFIED |
| LLM cannot write Event directly | VERIFIED |
| LLM cannot call Expo | VERIFIED |
| Runtime sole effect path for N1 ACT | VERIFIED |
| `test_final_authority_audit` | PASS |

**CASI: PASS**

---

## 12. Tests

| Suite | Result |
|---|---|
| 2.6E (`test_eko_ticket_customer_note_2_6e`) | PASS (16) |
| 2.3G-B | PASS |
| 2.3D | PASS |
| 2.3E | PASS |
| 2.6A | PASS |
| CASI (`test_final_authority_audit`) | PASS |
| Portal tickets | PASS |
| Helpdesk | PASS |
| 4E agentic | PASS |
| 2.5C | PASS |
| 2.5D-1 | PASS |
| 2.5D-2 | PASS |
| 2.5D-3 | PASS |
| 2.5D-4 | PASS |
| Billing 2.1 | PASS |
| Ruff (2.6E files) | PASS |
| `npm run test:push` | PASS |
| `test_4b_explicit_diagnostic_invokes_reader_when_selected` | **PRE-EXISTING UNRELATED FAILURE** (`needs_input` vs `success`) — not caused by 2.6E |

---

## 13. Production Deployment Matrix

| Surface | Required? | Notes |
|---|---|---|
| Backend deploy | **YES** | Runtime, repo, portal, tickets API, proactive |
| Backend restart | **YES** | FastAPI reload |
| Migration | **NO** | Existing `TicketEvent` model |
| New env vars (required) | **NO** for agent path |
| N1 Runtime gate | **OPTIONAL** | Add `ticket_customer_note` to `ACTION_RUNTIME_ACTIONS` when enabling N1 dispatch |
| Mobile APK | **NO** | `event=updated` already supported |
| Mobile new version | **NO** |
| Mobile contract already supported | **YES** |

---

## 14. Smoke Status

```text
SMOKE NOT AVAILABLE
```

No harness seguro/reversible encontrado que:

- use solo flujo Policy/Runtime/API sin INSERT/UPDATE manual,
- garantice abonado/dispositivo/ticket de prueba aislados,
- y evite riesgo a clientes reales,

sin preparación operativa externa (staging + cuenta interna + wait/acción controlada).

**No ejecutado.** Procedimiento futuro potencial (DOCUMENTED, not verified): staging + abonado interno + PortalDevice + agent `POST .../events` o Runtime gated + observar logs/Event/push/portal → cleanup. Requiere aprobación ops.

---

## 15. Findings

### Critical
Ninguno.

### High
Ninguno que bloquee authority.

### Medium

| ID | Finding |
|---|---|
| F-01 | `ticket_customer_note` fuera del set default `ACTION_RUNTIME_ACTIONS` — N1 no despacha el ACT hasta activación env (mismo patrón que mutadores). |
| F-02 | Smoke productivo no disponible en esta auditoría — production readiness ≠ production proven. |
| F-03 | Ventana Event commitado / push no entregado si detector o proceso falla post-commit (patrón 2.3G-B). |

### Low

| ID | Finding |
|---|---|
| F-04 | `emit_ticket_customer_note` no re-chequea ownership (caller-trusted). |
| F-05 | `add_ticket_event` default `visible_cliente=Sí` permanece para otros writers; 2.6E endureció paths admin/ACT pero no el default global. |
| F-06 | Históricos pre-2.6E con `actualizacion`+`Sí` mitigados por filtro portal, no por backfill. |
| F-07 | Activity/cold-start en dispositivo real **NOT VERIFIED**. |

---

## 16. Residual Risks

1. Activar N1 Runtime sin allowlist env → ACT no llega al canal (fail-closed; no leak).  
2. Agente puede emitir notas customer-visible vía API (intencional) — gobernanza de contenido operativa.  
3. Persistido-sin-push en fallos post-commit.  
4. Sin smoke controlado, primer uso real es el primer riesgo de delivery/Expo.

No se observó regresión en 2.5 / CASI / Billing / outage / created/closed / SLA 2.6A en las suites ejecutadas.

---

## 17. Observability

| Step | Status |
|---|---|
| A. ACT invoked | DOCUMENTED (`eko_action` logs / agent audit) |
| B. TicketEvent created | VERIFIED (DB model + tests) |
| C. Detector | VERIFIED (`ticket_proactive` logs) |
| D. Policy decision | VERIFIED (logs) |
| E. Ownership | VERIFIED (`ticket_push` / skip logs) |
| F. Claim | VERIFIED (`push_claimed_at` / already_claimed) |
| G. Expo attempt | VERIFIED (logs; mocked in tests) |
| H. Expo result | VERIFIED (logs categories) |
| I. Mobile receipt / Activity | NOT VERIFIED (device) |
| J. Portal GET | VERIFIED (code + portal tests) |

---

## 18. Final Gate

```text
EKO 2.6F — PASS WITH FINDINGS
```

**Meaning:** Ready for **backend deploy** of 2.6E with activation discipline (optional N1 Runtime allowlist; no migration; no mobile APK). **Not** proven in production; **smoke not available** in this audit. Authority and CASI **PASS**.

---

## Audit meta

| Item | Value |
|---|---|
| Code changes | **NONE** |
| Docs created | this file |
| Docs modified (2.6D/E/A/B) | NONE |
| Production side effects | NONE |
