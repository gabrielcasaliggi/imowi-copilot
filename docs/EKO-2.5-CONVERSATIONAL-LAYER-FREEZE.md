# EKO 2.5 — Conversational Layer Freeze

**STATUS: CLOSED / FROZEN**  
**Gate: 2.5E — Conversational Layer Closure Audit**  
**Date: 2026-09-23**

---

## 1. STATUS

```text
EKO 2.5 = CLOSED / FROZEN
```

Subphases closed:

| Phase | Title | Status |
|---|---|---|
| 2.5A | Conversational Quality & Context Continuity Discovery | DONE |
| 2.5B | Context Continuity Contract | DONE |
| 2.5C | Conversational Regression Matrix | DONE (0 xfail) |
| 2.5D-1 | Canonical Service Context Read Path | PASS |
| 2.5D-2 | Reference Resolution | PASS |
| 2.5D-3 | Domain Stack / Natural-Language Resume | PASS |
| 2.5D-4 | Playbook + Handoff Continuity | PASS |
| 2.5E | Closure Audit & Freeze | PASS |

This document is the **baseline freeze**. Subsequent product phases must treat the contracts below as architectural invariants, not incidental feature details.

---

## 2. Canonical service context

| Role | Field / API |
|---|---|
| **READ SoT** | `eko_journey.selected_service_ref` via `get_selected_ref()` / `get_selected_service_ref()` |
| **WRITE path** | `apply_service_ref()` |
| **Projection** | `eko_journey.selected_service` (compat key: login or service_id) |
| **Technical shadow** | `ctx.login_seleccionado` |

**Invariant:** `get_selected_ref()` reads **only** `selected_service_ref`. It does **not** fall back to `selected_service` or `login_seleccionado`.

---

## 3. Canonical domain continuity

| Role | Location |
|---|---|
| **Stack** | `ConversationState.domain_stack` |
| **Max depth** | `MAX_STACK = 3` |
| **Entries** | Domain slot IDs (`tec-1`, `adm-1`, `com-1`) |
| **Kinds** | `tecnico`, `administrativo`, `comercial` |
| **Update** | `push_domain_stack()` on create / activate / resume |

**Invariant:** Single stack. No ServiceRef, login, client_number, transcript, or free text. Move-to-front, no duplicates. Handoff is **not** a domain.

---

## 4. Reference resolution

| API | Module |
|---|---|
| `resolve_service_reference` | alias → `resolve_service_selection` |
| `resolve_fijo_reference` | `el fijo` / `la fija` |
| `resolve_otro_reference` | `el otro` (requires canonical `current_ref`) |

**Rules (frozen):**

- Unique telefonia XOR unique internet → RESOLVED; both → NEEDS_INPUT; none → NEEDS_INPUT.
- `el otro` needs current `selected_service_ref`; unique alternate → RESOLVED; else NEEDS_INPUT.
- Foreign service_id / login → DENIED.
- No SoT fallback to `login_seleccionado` / transcript / LLM.
- `ese` semantics unchanged (multi → NEEDS_INPUT).

---

## 5. Domain resume

| API | Module |
|---|---|
| `resolve_domain_resume` | `app/domain/domain_lifecycle.py` |
| `apply_domain_resume` | pause + `resume_domain` |
| Integration | `apply_turn_domain` (before create/signal) |

**Rules (frozen):**

- Phrases: `volvamos/retomemos a lo de X`, `sigamos con X`, `lo anterior` / `volviendo a lo anterior`.
- Resolve only against canonical kinds + existing `domain_stack`.
- Missing / ambiguous / not-in-stack → NEEDS_INPUT (never invent domain).
- Does **not** mutate `selected_service_ref`.
- Does **not** execute Runtime.

---

## 6. Playbook continuity

| API | Module |
|---|---|
| `playbook_selected_service` | → `get_selected_ref` |
| `should_ask_service_selection` | ask-gate (K01) |

**Rules (frozen):**

- Journeys that need a service consume `get_selected_ref()`.
- Valid owned ref → do not re-ask.
- Missing / foreign / invalid → NEEDS_INPUT / selection required.
- Dual-write incomplete may use `login_seleccionado` shadow only when **no** canonical ref exists (`LEGACY_READ_REMAINS` — not SoT).

---

## 7. Handoff continuity

| API | Role |
|---|---|
| `stamp_handoff_out` | OUT: identity snapshot + invalidate confirmation |
| `invalidate_stale_confirmation_if_handoff` | Early bot turn: clear stale «sí» |
| `prepare_return_from_handoff` | Validate + deactivate handoff flag |
| `validate_selected_ref_for_return` | Ownership (+ optional catalog) |

**Flow (frozen):**

```text
HANDOFF OUT (escalate_human / ticket N2)
  → structured eko_handoff (is_authority=False)
  → human / espera_agente|con_agente
  → estado = bot (inbox release / portal)
  → validation vs TrustedContext
  → canonical state (no transcript rebuild)
```

**Rules (frozen):**

- Metadata is transport, not authority.
- No ownership / client_number write from metadata.
- Foreign or ownership-mismatched selection → cleared.
- Confirmation across handoff → stale / cleared.
- No automatic Runtime on return.
- Handoff ≠ domain.

---

## 8. Authority

Aligned with CASI (unchanged):

```text
LLM
  → proposal / interpretation
  → deterministic validation
  → ConversationState / Motor / Policy
  → Runtime
```

LLM **cannot** (sanitized / rejected):

- set `selected_service_ref`
- write `domain_stack` / `eko_handoff`
- set `client_number` / ownership
- confirm actions
- execute Runtime
- restore handoff as authority

---

## 9. Explicit non-goals

Do **not** add in later “small” changes without a dedicated regression phase:

- Conversational free memory / semantic memory
- Transcript reconstruction of state
- General NLP expansion
- Autonomous context inference
- New domain kinds / aliases
- New service references beyond `fijo` / `fija` / `otro` / existing natural match
- Handoff as second state machine
- Parallel domain stacks

---

## 10. Known limitations (accepted)

| ID | Limitation | Severity |
|---|---|---|
| L-01 | Return path often calls `prepare_return_from_handoff(..., catalog=None)` — catalog check only when caller supplies catalog | LOW |
| L-02 | Visitor / `marcar_cola_visitante` does not stamp `eko_handoff` | LOW |
| L-03 | No UI E2E of inbox «release → bot» button (logic + canal hook covered) | LOW |
| L-04 | Legacy N1 paths (`canal_pppoe`, `wifi_bcm`, `turno_e1`, parts of `canal_abonado`) still read `login_seleccionado` outside Eko journey SoT | INFO — LEGACY_READ_REMAINS |
| L-05 | `should_ask_service_selection` may skip ask using shadow login when canonical ref is absent (dual-write bridge) | INFO — LEGACY_READ_REMAINS |

**No CRITICAL / HIGH findings** at freeze time.

---

## 11. SoT consumer classification (audit snapshot)

| Symbol | Classification |
|---|---|
| `get_selected_ref` / `get_selected_service_ref` | **CANONICAL_READ** |
| `apply_service_ref` | **WRITE** (canonical + projections) |
| `eko_journey.selected_service` | **PROJECTION** |
| `ctx.login_seleccionado` write from `apply_service_ref` / diagnostic align | **PROJECTION** / technical shadow |
| `eko_journeys` display / dual-write gates using shadow when ref absent | **LEGACY_READ_REMAINS** |
| `should_ask_service_selection` shadow branch | **LEGACY_READ_REMAINS** |
| `canal_pppoe` / `wifi_bcm` / `turno_e1` / legacy `canal_abonado` login reads | **LEGACY_COMPATIBILITY** (outside Eko SoT) |
| Runtime diagnostic / policy selection checks | **CANONICAL_READ** via `get_selected_ref` |
| LLM params `selected_service_ref`, `login`, `service_id`, `eko_handoff`, `domain_stack` | **Blocked** (`_UNTRUSTED_PARAM_KEYS`) |

---

## 12. Change policy

Any modification to:

- `selected_service_ref` / `get_selected_ref` / `apply_service_ref`
- `resolve_service_reference` / fijo / otro
- `ConversationState.domain_stack` / `push_domain_stack`
- `resolve_domain_resume` / `apply_domain_resume`
- playbook ask-gate / handoff continuity APIs
- confirmation-across-handoff semantics

**requires** a dedicated conversational regression + audit phase (not an incidental edit inside Billing, SM, Proactive, Commercial, or mobile work).

---

## 13. Production safety (2.5 scope)

2.5 is a **conversational/contextual** layer. Freeze audit confirms it did **not** introduce:

- New external WRITE APIs
- New credentials
- New background jobs / schedulers
- Schema migrations / tables
- Customer notification campaigns
- Commercial transactional effects

Handoff continues to use existing `espera_agente` / inbox release / ticket N2 paths.

---

## 14. Regression baseline

At freeze:

- `tests/test_eko_conversational_regression_2_5c.py` — **0 xfail**
- `tests/test_eko_canonical_service_read_2_5d1.py`
- `tests/test_eko_reference_resolution_2_5d2.py`
- `tests/test_eko_domain_stack_resume_2_5d3.py`
- `tests/test_eko_playbook_handoff_continuity_2_5d4.py`
- Plus hardening_6, domain_lifecycle (+ productivo), SM 2.2b, conversation_motor, conversation_state_shadow

---

## 15. Related docs

- `docs/EKO-2.5A-CONVERSATIONAL-QUALITY-CONTEXT-CONTINUITY-DISCOVERY.md`
- `docs/EKO-2.5B-CONTEXT-CONTINUITY-CONTRACT.md`
- `docs/EKO-2.5C-CONVERSATIONAL-REGRESSION-MATRIX.md`

---

## 16. POST-2.5 BACKLOG (do not implement in freeze)

Documented only — **OUT OF FREEZE SCOPE**:

1. Pass authorized catalog into `prepare_return_from_handoff` from canal when available (L-01).
2. Optional stamp on visitor handoff path (L-02).
3. Inbox release UI E2E sensor (L-03).
4. Gradual migration of remaining LEGACY_READ_REMAINS toward canonical ref in legacy N1 surfaces (L-04/L-05) — requires its own audit.

---

**FINAL:** `EKO 2.5 — CLOSED / FROZEN`
