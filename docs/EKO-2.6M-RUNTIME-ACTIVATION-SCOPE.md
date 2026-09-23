# EKO 2.6M — Runtime Activation Scope Hardening

**Date:** 2026-09-23  
**Mode:** READ ONLY — code/config/tests/defaults: **NONE modified**  
**Does not activate** `ACTION_RUNTIME_ENABLED`  
**Primary question:** Can `create_ticket` be rolled out via an **explicit ACTIONS CSV** without enabling the full default Runtime blast radius?

---

## 1. Executive Summary

```text
covers(action) = ACTION_RUNTIME_ENABLED ∧ (action ∈ ACTION_RUNTIME_ACTIONS)
```

Default `ACTION_RUNTIME_ACTIONS` = **13** actions (includes `create_ticket` + reads/diag/OV/`ticket_customer_note`).

**CSV semantics (proven in code):** if env `ACTION_RUNTIME_ACTIONS` is non-empty after strip, it **replaces** the entire default set (does not merge).

**Isolation (proven by covers simulation):**

```text
ACTION_RUNTIME_ENABLED=true
ACTION_RUNTIME_ACTIONS=create_ticket
→ covers(create_ticket)=True
→ covers(ticket_customer_note|show_ticket|show_balance|…)=False
```

`create_ticket` has **no code dependency** on other actions being listed in ACTIONS (confirmation is Policy/TrustedContext; writer is `_crear_ticket_n2` via executor).

**Final answer:**

```text
YES — ISOLATED ACTIONS SUPPORTED
```

Trade-off (documented, not a blocker for isolation): isolating to `create_ticket` alone **drops** Runtime for note/show/billing/diagnostics (they fall back to Legacy / note XOR unavailable). That is the intended blast-radius control.

Legacy direct creates (~9 N1 sites outside XOR helper) remain; same-conversation second create is guarded by `if conv.ticket_id: return` → duplicate risk **PROVEN SAFE** for dual ticket on one conv.

---

## 2. Current Runtime Activation Model

```text
os.getenv ACTION_RUNTIME_ENABLED  → bool (default false)
os.getenv ACTION_RUNTIME_ACTIONS  → if strip nonempty: frozenset(CSV)
                                  → else: hardcoded default frozenset (13)

action_runtime_covers(name):
  if not ENABLED: return False
  return name in ACTIONS

dispatch_runtime / XOR helper only when covers
```

Sources of truth:

| Source | Role |
|---|---|
| `app/config.py` | defaults + parse |
| `eko_action_bridge` | covers / dispatch |
| `.env.server.example` | **stale** ops comments (pre-2.6K) |
| `DEPLOY.md` | points to `.env.server.example` + restart |
| Tests | monkeypatch covers |

No canary %, no per-tenant Runtime master (Journeys have CHANNELS/ORG_IDS separately).

---

## 3. ACTION_RUNTIME_ACTIONS Inventory

**Default set (exact, sorted):**

1. `create_ticket`  
2. `installation_status`  
3. `open_OV`  
4. `request_account_selection`  
5. `run_diagnostic_bcm`  
6. `run_diagnostic_pppoe`  
7. `run_diagnostic_uisp`  
8. `send_message`  
9. `service_list`  
10. `show_balance`  
11. `show_invoice`  
12. `show_ticket`  
13. `ticket_customer_note`  

**Not in default:** `update_ticket`, `escalate_human`, `close_conversation` (and all unregistered names).

| Action | Default | Runtime executor | Effect | Existing Legacy | User-facing | Risk |
|---|---|---|---|---|---|---|
| `show_balance` | YES | YES | READ | canal saldo | YES | LOW |
| `show_invoice` | YES | YES | READ | journey billing | YES | LOW |
| `service_list` | YES | YES | READ | journey catalog | YES | LOW |
| `show_ticket` | YES | YES | READ | journey reader | YES | LOW |
| `send_message` | YES | YES | PRESENTATION | `_enviar_respuesta` | YES | LOW |
| `request_account_selection` | YES | YES | STATE ask | multi_cuenta | YES | LOW |
| `open_OV` | YES | YES | NAV URL | ov_handoff | YES | LOW–MED |
| `run_diagnostic_pppoe` | YES | YES | TECH READ | canal_pppoe | YES | MED (RISK idemp) |
| `run_diagnostic_bcm` | YES | YES | TECH READ | PARTIAL Legacy N1 | YES | MED |
| `run_diagnostic_uisp` | YES | YES | TECH READ | PARTIAL Legacy N1 | YES | MED |
| `installation_status` | YES | YES | READ unavailable | honest message | YES | LOW |
| `ticket_customer_note` | YES | YES | EFFECT Event | none customer-visible | YES | MED |
| `create_ticket` | YES | YES | EFFECT Ticket | `_crear_ticket_n2` | YES | HIGH |

---

## 4. Action Classification

| Class | Actions |
|---|---|
| READ | `show_balance`, `show_invoice`, `service_list`, `show_ticket`, `installation_status` |
| NAVIGATION | `open_OV` |
| PRESENTATION / STATE | `send_message`, `request_account_selection` |
| TECHNICAL (probe READ) | `run_diagnostic_pppoe`, `run_diagnostic_bcm`, `run_diagnostic_uisp` |
| EFFECT (mutating) | `create_ticket`, `ticket_customer_note` |
| COMMERCIAL EFFECT | none in ACTIONS |
| PROACTIVE EFFECT | none as ActionSpec (proactive is Event post-commit) |

---

## 5. Blast Radius

When `ENABLED` flips false→true **with default ACTIONS (13)**:

| Action | OFF | ON | Behavioral change? | Production impact |
|---|---|---|---|---|
| `create_ticket` (XOR helper) | Legacy write | Runtime+confirm | **YES** | HIGH (desired) |
| `ticket_customer_note` | unavailable / gate off | Runtime note | **YES** | MED (2.6I already designed) |
| `show_ticket` | Legacy reader (journey) | Runtime READ | YES (path) | LOW if semantics equal |
| `show_balance` / invoice / service_list | Legacy | Runtime | YES (path) | LOW–MED |
| `open_OV` | Legacy handoff | Runtime allowlist URL | YES (path) | LOW |
| diagnostics | mostly Legacy/PARTIAL | PPPoE Runtime if wired | YES | MED |
| Direct `_crear_ticket_n2` | Legacy | **still Legacy** | **NO** | HIGH residual |
| `update_ticket` | Legacy evidence | still not covered | NO | — |

**Unwanted blast:** enabling Runtime **without** a restrictive CSV also Runtime-enables note, show, billing reads, OV, diagnostics — even if ops only wanted create.

**Controlled blast:** `ACTIONS=create_ticket` → only create covers True; others OFF-path.

---

## 6. create_ticket Isolation Analysis

| Question | Evidence |
|---|---|
| Can ENABLED=true + ACTIONS=`create_ticket` cover only create? | YES — `covers` membership check |
| Does executor need other ACTIONS members? | NO — `_exec_create_ticket` → `_crear_ticket_n2` |
| Does Policy/confirmation need another action name listed? | NO — confirmation is TrustedContext + ActionSpec flag |
| Does registry require ACTIONS membership to register? | NO — `is_registered` independent; unknown CSV names sit in set but dispatch DENY if not registered |
| Side effect of isolation on note? | `covers(note)=False` → N1 note path **unavailable** (no Legacy Sí) — intentional if omitted |
| Side effect on show/billing? | Fall back to Legacy call sites when present |

**Isolation:** supported by existing architecture — **no new flag required**.

---

## 7. CSV Semantics

Code (`app/config.py`):

```text
_raw = os.getenv("ACTION_RUNTIME_ACTIONS", "").strip()
if _raw:
    frozenset(strip tokens split by comma, drop empty)
else:
    default frozenset(13)
```

| Case | Input | Result |
|---|---|---|
| A absent | unset / not in env | **default 13** |
| B | `create_ticket` | **only** create |
| C | `create_ticket,ticket_customer_note` | those two only |
| D empty | `""` after strip | **default 13** (falsy → else branch) |
| E spaces | `  create_ticket , show_ticket  ` | both (strip works) |
| F unknown | `create_ticket,not_a_real_action` | both in set; unknown never succeeds via registry |
| G empties | `create_ticket,, ,foo` | `{create_ticket, foo}` |

**Replace-all:** confirmed. Omitting `ticket_customer_note` from CSV **disables** Runtime note even if it is in the codebase default.

---

## 8. create_ticket Dependencies

```text
create_ticket
→ required runtime actions listed in ACTIONS:
   []   # none
→ standalone
```

Implicit non-ACTIONS dependencies (always present in process):

- Registry ActionSpec  
- Policy / confirmation helpers  
- TrustedContext / abonado  
- `_crear_ticket_n2` writer  
- Estate Ticket + Event `creacion`  

Optional product choice (not a code dependency): keep `ticket_customer_note` in CSV if ops want note Runtime in same wave.

---

## 9. Legacy Create Call Sites

### XOR / Runtime-governed

| Call site | Caller | Runtime? |
|---|---|---|
| `_ticket_via_runtime_o_legacy` | escape agente; confirmation resume; journeys connectivity | YES when covers |
| `_exec_create_ticket` → `_crear_ticket_n2` | Runtime executor | YES (writer) |
| Helper internal `if not covers: _crear_ticket_n2` | XOR Legacy branch | Legacy when OFF |

### Direct Legacy (bypass XOR helper) — abonado-reachable N1

| Call site | Caller (approx) | Channel | Runtime? | Legacy? | User-facing? |
|---|---|---|---|---|---|
| `canal_abonado:1616` | UISP señal / visita | N1 canal | NO | YES | YES |
| `canal_abonado:2627` | sin internet fijo + humano | N1 | NO | YES | YES |
| `canal_abonado:5412` | frustración/reiteración | N1 | NO | YES | YES |
| `canal_abonado:5839` | baja con deuda | N1 | NO | YES | YES |
| `canal_abonado:7204` | falla óptica | N1 | NO | YES | YES |
| `canal_abonado:7471` | escalamiento genérico | N1 | NO | YES | YES |
| `canal_diagnostico_ia:190` | diag IA escalate | N1 | NO | YES | YES |
| `canal_diagnostico_ia:255` | diag IA escalate | N1 | NO | YES | YES |
| `canal_diagnostico_ia:732` | diag IA escalate | N1 | NO | YES | YES |

**Count:** **9** direct N1 Legacy creates (excluding def, XOR branch, executor).

Portal `POST /portal/tickets` and helpdesk APIs: separate authorities (not Action Runtime).

---

## 10. Duplication Analysis

| Scenario | Guard | Classification |
|---|---|---|
| Same request: XOR Runtime + Legacy dual | Helper forbids Legacy when covers | **PROVEN SAFE** |
| Runtime success then Legacy same conv | `if conv.ticket_id: return` in `_crear_ticket_n2` | **PROVEN SAFE** |
| Legacy first then Runtime confirm | `already_done` / early return | **PROVEN SAFE** |
| Two different Legacy sites same turn | Same `conv.ticket_id` guard | **PROVEN SAFE** (second returns existing id) |
| Exhaustive all intent overlaps | Not fully enumerated | residual **NOT_PROVEN** for product UX (two messages → one ticket ok) |

**Duplicate ticket risk (same conversación):** **PROVEN SAFE**

---

## 11. Runtime Action Safety (default set if ENABLED without CSV)

| Action | Policy | Confirm | Ownership | XOR | Audited enough for silent ON? |
|---|---|---|---|---|---|
| create | YES | REQUIRED | Trusted | YES (wired) | YES (2.6K) — but prefer isolate |
| note | YES | NO | YES | YES | YES (2.6I) |
| show_* / service / invoice | YES | NO | YES | path swap | mostly YES |
| open_OV | allowlist | NO | n/a | path swap | YES |
| diagnostics | YES | NO | selected_ref | PARTIAL bcm/uisp | **MED** — known PPPoE test FAIL noise |
| installation_status | YES | NO | n/a | honest unavailable | YES |

Enabling **full default** ACTIONS is wider than “create rollout”; isolation CSV is safer.

---

## 12. CASI Impact

Restricting ACTIONS to `create_ticket`:

- Does **not** change sanitize / TrustedContext / Policy code  
- Does **not** allow LLM to skip confirmation  
- Only changes which actions `covers()` admits  

```text
CASI = PASS
```

---

## 13. Production Configuration

| Item | Status |
|---|---|
| Where prod env lives | Ops: copy `.env.server.example` → `.env` (`DEPLOY.md`); systemd unit **NOT_PROVEN** in-repo |
| Inject env | Process environment at API boot | **NOT_PROVEN** unit file contents |
| Restart | `systemctl restart operations-hub-api` documented | PASS (docs) |
| Local `.env` ACTION_RUNTIME_* | ABSENT → defaults | PASS |
| Remote prod values | **NOT_PROVEN** | — |
| `.env.server.example` | **STALE** (says mutators must be listed; code default includes create+note) | GAP docs |

No secrets printed.

---

## 14. Observability

| Path | Evidence |
|---|---|
| Runtime create | `eko_action` + `eko_action_bridge … path=runtime` + correlation_id + status |
| Legacy direct create | **weak** — no bridge log |
| Ticket / Event | DB ids; Event `creacion` |

Smoke **can** demonstrate for XOR path:

```text
1 confirm → 1 Runtime log → 1 Ticket → 1 creacion Event
```

Legacy-only escalations harder to attribute without extra logging (**GAP**, not blocker for isolation).

---

## 15. Rollback

```text
ACTION_RUNTIME_ENABLED=false
+ restart API
→ covers(*)=False
→ XOR helper Legacy
→ dispatch None
```

ACTIONS CSV may remain set; irrelevant while ENABLED false.

Direct Legacy creates unchanged.

---

## 16. Final Answer

```text
YES — ISOLATED ACTIONS SUPPORTED
```

Technically safe to activate **only** `create_ticket` via:

```text
ACTION_RUNTIME_ENABLED=true
ACTION_RUNTIME_ACTIONS=create_ticket
```

(plus API restart)

without requiring global default ACTIONS. No architectural change needed.

Operators must accept:

1. Other default Runtime actions stay Legacy/unavailable until listed.  
2. Nine Legacy create sites remain outside confirmation Runtime.  
3. Prod env still NOT_PROVEN until set externally.

---

## 17. Recommended Next Step

**Configuration / ops change only** (not new architecture):

1. Staging first:  
   `ACTION_RUNTIME_ENABLED=true`  
   `ACTION_RUNTIME_ACTIONS=create_ticket`  
2. Restart API; smoke XOR escape/confirm path.  
3. Optional wave-2 CSV: `create_ticket,ticket_customer_note` if note Runtime desired.  
4. Avoid bare ENABLED=true with **absent** ACTIONS (loads all 13 defaults).  
5. Update `.env.server.example` comments in a **later** docs-only or ops PR (out of scope here).  
6. Future engineering (not this phase): migrate remaining `_crear_ticket_n2` sites to XOR helper.

**Do not** invent a new feature flag.

---

## 18. Explicit Non-Goals

- No code/config/test changes  
- No activation of ENABLED  
- No Legacy migration  
- No CASI / create / note changes  
- No PPPoE fixes  

---

## Test Evidence (RO)

| Suite | Result |
|---|---|
| 2.6K / 2.6I / 2.6E | PASS |
| 4D / 4E | PASS (excl. known PPPoE if selected elsewhere) |
| 2.3G-B | PASS |

PPPoE FAILs remain unrelated.

---

```text
EKO 2.6M — RUNTIME ACTIVATION SCOPE AUDIT COMPLETE
```
