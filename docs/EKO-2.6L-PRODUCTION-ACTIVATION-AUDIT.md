# EKO 2.6L — Production Activation Audit / Rollout Gate

**Date:** 2026-09-23  
**Mode:** READ ONLY — code/config/tests: **NONE modified**  
**Deliverable:** this document only  
**Question:** Is the system technically ready for an **external** operator to set `ACTION_RUNTIME_ENABLED=true` in production?

---

## 1. Executive Summary

```text
ACTION_RUNTIME_ENABLED default = false   (process load)
create_ticket ∈ default ACTION_RUNTIME_ACTIONS   (2.6K)
covers(create_ticket) = ENABLED ∧ ACTIONS
```

**Wired Runtime path** (`_ticket_via_runtime_o_legacy` + journeys connectivity create):

- Confirmation REQUIRED  
- XOR: covers True → **never** Legacy writer on deny/fail/unavailable/None  
- CASI: PASS (sanitize + TrustedContext)  
- Event `creacion` Sí → 2.3G-B `ticket.created`  
- Tests 2.6K / 4C / 4D XOR: PASS  

**However**, N1 still has **multiple direct** `_crear_ticket_n2(...)` call sites (canal_abonado ≈7, canal_diagnostico_ia ≈3) that **bypass** the XOR helper entirely. With Runtime “ON”, those paths remain **Legacy-only creates** (no Policy Runtime confirmation). That is **not** Runtime+Legacy dual on the same helper, but it means enabling the master flag does **not** make every ticket creation Agentic.

**Production env values:** **NOT PROVEN** for remote production. Local `.env`: `ACTION_RUNTIME_*` keys **ABSENT** → code defaults.

**Decision:**

```text
READY_WITH_DOCUMENTED_LIMITATIONS
```

No evidence of BLOCKER-class dual write / confirmation bypass / CASI break on the **wired** path. Rollout is an **operational** change + acceptance of listed limitations — **this phase does not activate**.

---

## 2. Current Activation Model

```text
ACTION_RUNTIME_ENABLED  (master, default false)
        ∧
action ∈ ACTION_RUNTIME_ACTIONS
        ⇒
action_runtime_covers(action) = True
        ⇒
dispatch_runtime / XOR helpers use Runtime only
```

Independent (Fase 7):

```text
EKO_JOURNEYS_ENABLED (+ optional CHANNELS / ORG_IDS)
```

Journeys OFF does not disable canal phrase gates that call `dispatch_runtime` when covers.

Config load: **process start** (`app/config.py` reads `os.getenv` once). Change requires **restart** of API process (`DEPLOY.md`: `systemctl restart operations-hub-api`).

---

## 3. Configuration Audit

| Setting | Default | Production source | Validated | Risk |
|---|---|---|---|---|
| `ACTION_RUNTIME_ENABLED` | `false` (only `1/true/yes/on` → True) | Env at process boot; local `.env` **ABSENT**; remote prod **NOT_PROVEN** | Boolean parse in config | Invalid/absent → False (safe) |
| `ACTION_RUNTIME_ACTIONS` | Default frozenset incl. reads/diag/OV/`ticket_customer_note`/`create_ticket` | Env CSV override if non-empty; local **ABSENT**; remote **NOT_PROVEN** | Split/strip | Empty env string → default set; explicit CSV **replaces** entire set |
| `EKO_JOURNEYS_ENABLED` | `false` | Env; local ABSENT; prod **NOT_PROVEN** | same bool parse | Journey orchestration off by default |
| `EKO_JOURNEYS_CHANNELS` / `ORG_IDS` | empty = all when master ON | Env CSV | — | Accidental global journeys if ENABLED without allowlists |

**Parsing:** no startup validator beyond getenv. Non-boolean ENABLED values → False.  

**Partial activation:**

- ENABLED false + ACTIONS has create → covers False → Legacy (for XOR helper)  
- ENABLED true + ACTIONS omit create (custom CSV) → covers False → Legacy  
- ENABLED true + default ACTIONS → create/note/show covered  

**Stale docs:** `.env.server.example` still comments create_ticket as “list manually”; code default **includes** it (2.6K). Example is outdated — **GAP (docs/ops)**.

**Secrets:** no ACTION_RUNTIME secrets. Other env credentials: not inspected (PRESENT/ABSENT of runtime keys only).

---

## 4. Activation Matrix

| ACTION_RUNTIME_ENABLED | create_ticket in ACTIONS | Resultado (XOR helper / dispatch) |
|---|---|---|
| false | false | covers False → Legacy `_crear_ticket_n2` (helper) |
| false | true | covers False → Legacy (ENABLED wins) |
| true | false | covers False → Legacy |
| true | true | covers True → Runtime + confirmation; **no** Legacy on fail |

**Also with ENABLED=true + default ACTIONS:**

| Action | covers? | Behavior |
|---|---|---|
| `show_ticket` | YES | Runtime READ (canal/journey) |
| `ticket_customer_note` | YES | Runtime EFFECT (2.6I) |
| `create_ticket` | YES | Runtime EFFECT iff call site uses XOR helper |
| `update_ticket` | NO (not in default) | Legacy evidence / no N1 Runtime |
| Direct `_crear_ticket_n2` sites | N/A | **Always Legacy writer**, ignore covers |

---

## 5. Runtime / Legacy XOR Audit

### Wired path (PASS)

Evidence: `canal_abonado._ticket_via_runtime_o_legacy`:

```text
if not covers: Legacy write; return
ar = dispatch_runtime(...)
# covers was True: NUNCA Legacy mutante
if ar is None → message, no write
needs_confirmation → pending, no write
denied/failed/unavailable → message, no write
success/already_done → tid only
```

Tests: 2.6K XOR, 4D `test_4d_xor_create_ticket_*`.  

Journeys connectivity create uses same helper (`eko_journeys` → `_ticket_via_runtime_o_legacy`).

Escape agente / confirmation resume: XOR helper.

**No** `try Runtime except Legacy` on this helper.

### Unwired Legacy create paths (LIMITATION — HIGH)

Direct `_crear_ticket_n2` remains for e.g.:

- UISP señal / visita campo  
- padrón sin internet fijo + insistencia humano  
- frustración/reiteración  
- baja con deuda  
- falla óptica N1  
- escalamiento genérico post-diagnóstico  
- `canal_diagnostico_ia` escalations  

These **do not** enter Policy Runtime confirmation when ENABLED=true.

**XOR verdict (wired):** **PASS**  
**XOR verdict (all N1 creates):** **PARTIAL / NOT full coverage** — document as limitation, not dual-write BLOCKER.

---

## 6. Failure Semantics

| Runtime outcome | Wired helper effect | Legacy? |
|---|---|---|
| DENY | user message, no write | **No** |
| NEEDS_CONFIRMATION | pending prompt, no write | **No** |
| NEEDS_INPUT | (executor/policy) no write | **No** |
| UNAVAILABLE / failed / executor_exception | failed ActionResult → message | **No** |
| ar is None while covers | honest message | **No** |
| success after write | tid | **No** |
| already_done | existing tid | **No** |
| Exception inside `_crear_ticket_n2` after partial? | executor → failed; DB depends on writer | **No** second Legacy |

**Critical:** wired path cannot accidentally dual-create via Legacy on Runtime failure. **PASS** for that BLOCKER criterion.

Unwired paths: independent Legacy creates — not “fallback after Runtime fail”.

---

## 7. Confirmation Audit

Spec: `confirmation_required=True` on `create_ticket`.

Flow:

```text
Proposal/intent → Policy NEEDS_CONFIRMATION → pending in eko_action STATE
→ user «sí» (trusted resolve_user_confirmation) → Runtime create
```

- LLM cannot set confirmation (TrustedContext / sanitize).  
- Reject «no» → denied path.  
- Replay with `conv.ticket_id` → `already_done`.  

**Stale confirmation / context switch:** pending is keyed by action name in STATE; ticket B after A: if ticket already exists → already_done. Cross-service stale confirm: **NOT PROVEN** exhaustive matrix; mitigated by `conv.ticket_id` idempotency and pending action match.

**Verdict:** Confirmation on wired path **PASS**.

---

## 8. CASI Audit

Evidence: sanitize (`client_number`, `abonado_id`, `actor`, `visible_cliente`, `notify`, …); TrustedContext rebuilt in bridge; Policy before executor; 2.6K + 4B/4C/4E/final_authority suites.

Enabling ENABLED does not change authority model — only which call sites reach Runtime.

```text
CASI = PASS
```

---

## 9. Ownership / Security Audit

| Case | Wired Runtime | Evidence |
|---|---|---|
| Abonado presente | ALLOW after confirm | Policy `requires_abonado` |
| Missing abonado | DENY `missing_abonado` | 2.6K / Policy |
| LLM forged client_number | stripped | sanitize |
| Foreign ticket (note, not create) | DENY | 2.6I |
| Create ownership | línea/conv TrustedContext in `_crear_ticket_n2` | code |
| Multi-account arbitrary pick for create | create does not require service selection | low risk for ticket line; diagnostics separate |

Portal `POST /portal/tickets`: **separate** JWT authority — not Action Runtime. Unaffected by ENABLED except shared Event/proactive after write.

---

## 10. Event / Proactive Audit

```text
_crear_ticket_n2 → ticket_bridge/repo create
  → TicketEvent tipo=creacion visible=Sí
  → add_ticket_event → maybe_deliver_ticket_event_push
  → map ticket.created → policy → claim → Expo
```

- One creacion Event per successful create (writer).  
- Retry same conv: `already_done` / early return if `conv.ticket_id`.  
- Push dedup: `push_claimed_at` (**notification** idempotency ≠ write).  
- Self-note N/A for creacion actor `bot:…`.  

`creacion` **is** enabled for proactive push (2.3G-B).

---

## 11. Transaction Window

| Case | Observed guarantee |
|---|---|
| A Ticket commit / Event fail | **NOT PROVEN** atomic single TX across all writers; best effort |
| B Event commit / push claim fail | Event remains; push may miss — **best effort / at-most-once claim** |
| C Claim / provider fail | Event kept; no automatic outbox retry — **DEFERRED** (2.6F) |
| D Provider success / receipt missing | **NOT PROVEN** deep receipt pipeline |

Classification: Effect write **at-least-once risk low** on wired retry thanks to `conv.ticket_id`; push **at-most-once** per Event id; overall Event↔push window **best effort**.

---

## 12. Observability

**Exists:**

- `logger.info` `eko_action {...}` with action, status, reason, `execution_path`, correlation_id, decision_name  
- `eko_action_bridge decision=… path=runtime …`  
- Journey metrics API `/metrics/eko-journeys`  
- LLM metrics  

**Distinguish Runtime vs Legacy create:**

- Runtime: logs `path=runtime` / `eko_action`  
- Legacy direct `_crear_ticket_n2`: **no** bridge log — weaker signal (**GAP**)

No dedicated “create_ticket_runtime_count” metric.

---

## 13. Metrics

| Observable today | Not observable |
|---|---|
| Journey turn metrics | Create Runtime vs Legacy counters |
| LLM call metrics | Duplicate ticket rate alert |
| Structured action logs (if log ship) | Push failure rate by event type (partial logs only) |
| Proactive suppress logs | Automated alert on XOR violation |

---

## 14. Rollout Scope

| Mechanism | Exists? |
|---|---|
| Global ENABLED | YES |
| Per-action ACTIONS CSV | YES (replace-all set) |
| % canary | **NO** |
| Per-tenant Runtime | **NO** (Journeys have ORG_IDS; Runtime master does not) |
| Per-channel Runtime | **NO** (Journeys CHANNELS only) |

Practical gradual options without new flags:

1. ENABLED=true on staging first  
2. ENABLED=true + custom ACTIONS CSV listing subset (must include desired actions; **omitting** default members drops them)  
3. Keep Journeys off or channel-scoped while canal Runtime paths activate  

---

## 15. Channel Audit

| Channel / entry | create path |
|---|---|
| WhatsApp / app canal N1 | Mixed: XOR helper (escape) + many Legacy direct |
| Journeys (if enabled) | Connectivity create → XOR helper |
| Portal / App JWT | `portal_create_ticket` → ticket_bridge (**not** Runtime) |
| Helpdesk | Admin APIs (**not** Runtime) |
| Telegram | **NOT PROVEN** as distinct from canal if mapped |

Not all channels share Policy→Motor→Runtime for create.

---

## 16. Mobile Impact

No mobile code change required for ENABLED flip.

Expected contracts already in place:

- Ticket list/detail from estate  
- Push `ticket` / `created` via existing Expo path (2.3G-M)  

**Impact:** more Runtime-governed N1 creates + note/show when ENABLED; portal create unchanged. **Compatible** if push/ticket UI already ship.

---

## 17. Production Configuration Gap

| Item | Status |
|---|---|
| Local `.env` ACTION_RUNTIME_* | **ABSENT** (defaults) |
| Remote production values | **NOT_PROVEN** |
| Deploy templates with ACTION_RUNTIME | **ABSENT** in `deploy/` |
| `.env.server.example` accuracy | **STALE** vs 2.6K defaults |
| Secrets in chat | not printed |

Operator must set ENABLED in the **real** production env store and restart — not done in this phase.

---

## 18. Rollback Audit

```text
ACTION_RUNTIME_ENABLED=false  (+ restart API)
→ covers(*) = False
→ XOR helper uses Legacy _crear_ticket_n2
→ dispatch_runtime returns None
```

- No code deploy required for rollback if env-only.  
- Requires **process restart** (config imported at boot).  
- Direct Legacy paths unchanged.  
- Tickets already created remain.  

**Rollback:** demonstrated by code path; **operationally** env+restart.

---

## 19. Test Evidence (RO)

| Suite | Result |
|---|---|
| 2.6K create_ticket | PASS |
| 2.6I note | PASS |
| 2.6E/G | PASS |
| 2.3G-B / 2.3D / 2.3E | PASS |
| F7 production activation | PASS |
| Billing 2.1 | PASS |
| portal tickets | PASS |
| escalate_authority | PASS |
| final_authority (CASI) | PASS |
| Known PPPoE 4C/4D | FAIL (ajeno; not BLOCKER for this gate) |

Ruff (spot, unchanged code): PASS.

---

## 20. Production Readiness Matrix

| Gate | Status | Evidence | Severity |
|---|---|---|---|
| Configuration | PASS (defaults safe) | config.py; local ABSENT | INFO |
| Runtime/Legacy XOR (wired) | PASS | helper + 2.6K/4D | — |
| XOR (all N1 creates) | PARTIAL | direct `_crear_ticket_n2` | **HIGH** |
| Confirmation (wired) | PASS | Policy + tests | — |
| CASI | PASS | sanitize + suites | — |
| Ownership | PASS (wired/portal separate) | Policy + writer | — |
| Event | PASS | creacion Sí | — |
| Proactive | PASS | 2.3G-B map | — |
| Idempotency | PASS (conv.ticket_id) | executor | LOW gap LLM-key |
| Transaction window | BEST EFFORT | 2.6F deferred | **MEDIUM** |
| Observability | PARTIAL | eko_action logs; weak Legacy | **MEDIUM** |
| Metrics / alerting | GAP | no Runtime counters | **MEDIUM** |
| Rollback | PASS | ENABLED false + restart | — |
| Channel consistency | PARTIAL | portal ≠ Runtime; mixed N1 | **HIGH** |
| Mobile compatibility | PASS | contract reuse | INFO |
| Regression | PASS (excl. PPPoE known) | suites above | INFO |
| Prod config verified | NOT_PROVEN | remote | **HIGH** (ops) |
| Blast radius ENABLED | ALL default ACTIONS | config set | **MEDIUM** |

---

## 21. Limitations

1. Enabling Runtime does **not** migrate all `_crear_ticket_n2` call sites.  
2. Event→push remains best-effort (no outbox).  
3. No % canary / per-tenant Runtime master.  
4. Custom ACTIONS CSV replaces entire default set (easy to drop note/show accidentally).  
5. Observability weaker for Legacy creates.  
6. Production env state NOT_PROVEN until operator confirms.  
7. `.env.server.example` stale vs 2.6K.  
8. ENABLED activates create **and** note/show/billing reads/diagnostics in default set.  
9. Journeys allowlists independent — plan jointly.  
10. PPPoE diagnostic test FAILs unrelated but noisy in CI.

---

## 22. Final Decision

```text
READY_WITH_DOCUMENTED_LIMITATIONS
```

**Not** `READY_FOR_PRODUCTION_ACTIVATION` because channel/call-site coverage is incomplete and prod config is unverified — operators must accept limitations explicitly.

**Not** `BLOCKED`: no demonstrated dual Runtime+Legacy write on the XOR helper; CASI/confirmation/ownership hold on the wired path.

---

## 23. Exact Conditions for Activation

Operational checklist (**external**; not executed here):

1. Confirm staging/prod env: set `ACTION_RUNTIME_ENABLED=true` (value not committed in repo).  
2. Prefer leave `ACTION_RUNTIME_ACTIONS` unset (use 2.6K defaults) **or** set explicit CSV that includes at least `create_ticket`, `ticket_customer_note`, `show_ticket`, and required reads.  
3. Restart API (`systemctl restart operations-hub-api` or equivalent).  
4. Accept that plant/frustration/optical/etc. creates remain Legacy until a future call-site migration.  
5. Accept Event/push best-effort window.  
6. Ensure log shipping can filter `eko_action` / `eko_action_bridge` / `path=runtime`.  
7. Smoke: N1 escape → confirmation → one Ticket + one `creacion` Event + at most one push attempt.  
8. Smoke: Runtime deny/reject → **zero** ticket.  
9. Document rollback: `ACTION_RUNTIME_ENABLED=false` + restart.  
10. Optionally keep `EKO_JOURNEYS_*` scoped or off for first wave.  
11. Update ops example env docs (stale example) before/alongside rollout.  
12. Do **not** enable unrelated mutators (`update_ticket`, `escalate_human`, `close_conversation`) unless intentionally listed.

---

## 24. Explicit Non-Goals

- Did not set `ACTION_RUNTIME_ENABLED=true`.  
- Did not modify code, tests, or config.  
- Did not migrate remaining `_crear_ticket_n2` sites.  
- Did not implement outbox, metrics, or canary.  
- Did not touch Billing / 2.5 / note / create semantics.  
- Did not fix PPPoE FAILs.

---

## Appendix — Evidence anchors

| Topic | Location |
|---|---|
| Defaults | `app/config.py` |
| covers() | `eko_action_bridge.action_runtime_covers` |
| XOR helper | `canal_abonado._ticket_via_runtime_o_legacy` |
| Executor | `eko_action_runtime._exec_create_ticket` |
| Confirmation | ActionSpec + `resolve_user_confirmation` |
| Prior docs | `docs/EKO-2.6J-…`, `docs/EKO-2.6K-…` |

---

```text
EKO 2.6L — PRODUCTION ACTIVATION AUDIT COMPLETE
```
