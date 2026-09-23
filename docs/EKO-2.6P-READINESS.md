# EKO 2.6P-READINESS RESULT

**Date:** 2026-09-23  
**Mode:** READ ONLY — documentation/code inspection only  
**Precedents:** 2.6O `BLOCKED` · 2.6N-C isolation PROVEN in harness · production untouched  
**Code changes this phase:** none  

---

## Blocker A — Test identity

* **status:** `NOT_AVAILABLE`  
  (sub-class of candidates found: `AVAILABLE_BUT_NOT_AUTHORIZED` for demo fixture only)

* **evidence:**
  * `docs/PORTAL-ABONADO.md` — table “Demo abonado” (teléfono / DNI / nombre). Documented as **demo**, not as production smoke authorization.
  * `DEPLOY.md` — production checklist expects `DISABLE_DEMO_USERS=true` (demo users off).
  * Console logins (`admin` / `batan` / … in `README.md`) are **agent** accounts, not N1 abonado Runtime-create identities.
  * 2.6N / 2.6N-B / 2.6O: `SAFE_PRODUCTION_TEST_IDENTITY = NOT_AVAILABLE` for remote/production create smoke.
  * Pytest fixtures (2.6K / 2.6N-C): synthetic only — no documented mapping to a production abonado.
  * No doc of QA line, lab MSISDN, internal support identity, or ops-authorized smoke client for `create_ticket`.

* **authorization:** **NONE** documented for production ticket creation.

```text
SAFE_PRODUCTION_TEST_IDENTITY = NOT_AVAILABLE
```

Closing this blocker without inventing a client requires an **ops-provided** authorized identity (out of scope for code; not inventable here).

---

## Blocker B — Effective configuration

* **status:** `NO_EXISTING_MECHANISM`  
  (in-process helpers exist in code but are **not** operator-reachable without a code/ops change)

* **existing mechanism (code present, not operable for post-restart proof):**
  * `app.config` loads `ACTION_RUNTIME_ENABLED` / `ACTION_RUNTIME_ACTIONS` once at import (`os.getenv`).
  * `eko_action_coverage.rollout_snapshot()` and `eko_journeys.activation_snapshot()` expose effective `action_runtime_enabled` + `runtime_governed_now` / legacy lists — used in **tests** (`test_eko_production_activation_7`), **not** wired to HTTP, metrics, or startup logs.
  * `GET /health` / `GET /ready` — do **not** include ACTION_RUNTIME_*.
  * `GET /api/v1/metrics/llm` and `/metrics/eko-journeys` — do **not** include ACTION_RUNTIME_* / coverage.
  * `main.py` lifespan logs estate/KB/persistencia — **does not** log ACTION_RUNTIME or `rollout_snapshot`.
  * No admin/debug/config dump endpoint for these flags found under `app/api/`.

* **evidence:** grep of API routers, lifespan, metrics; 2.6O/2.6L audits; `activation_snapshot` only referenced from journeys module + F7 tests.

* **post-restart verification method (honest):**
  * **Documented today:** edit `__APP_ROOT__/.env` + `systemctl restart operations-hub-api` (`DEPLOY.md`, systemd `EnvironmentFile`). Reading the **file** proves persistence of intended lines — it does **not** by itself prove the **running process** loaded those values.
  * **Not documented as ops procedure:** `/proc/<pid>/environ`, ad-hoc Python one-liner on host, inventing `systemctl show` recipes.
  * **Indirect (insufficient for isolation):** a successful smoke log `eko_action` / `path=runtime` / `action=create_ticket` proves `ENABLED=true` ∧ `create_ticket ∈ ACTIONS`. It does **not** prove `ACTIONS={create_ticket}` vs default **13** (create would Runtime-succeed in both cases).

```text
To close Blocker B without guessing:
  CODE_CHANGE_REQUIRED
```

Examples of later phases (not this one): boot log of `rollout_snapshot()`, or admin RO endpoint returning `activation_snapshot()` / coverage — **forbidden here**.

---

## Blocker C — Smoke observability

* **status:** `OBSERVABILITY_FOR_SMOKE = SUFFICIENT`  
  (for **one deliberate XOR Runtime smoke**; global Legacy observability remains limited — accepted per brief)

* **conversation/request correlation:**
  * `eko_action` structured log includes `conversation_id`, `correlation_id`, `decision_name`, `timestamp` (`ActionResult.to_log`).
  * Bridge: `eko_action_bridge … path=runtime corr=…`.

* **action:** `action_name=create_ticket` in `eko_action` log; bridge `action=create_ticket`.

* **path:** `execution_path=runtime` / bridge `path=runtime`. Legacy direct `_crear_ticket_n2` does **not** emit this stamp → presence of Runtime log is positive evidence for the wired path.

* **executor:** one success log + Policy `ALLOW` / `result_status=success` after confirmation; harness proved single writer. In prod smoke: expect **exactly one** Runtime success line for that `conversation_id`/`corr`.

* **ticket:**
  * Not in `to_log()` fields (no `ticket_id` key in the log dict).
  * Available via existing estate: `ConversacionCanal.ticket_id`, console ticket view, ActionResult `data.ticket_id` persisted as conversation STATE `result_reference` after success (`set_action_state`).
  * Operator chain: log (`conversation_id` + Runtime success) → console/DB ticket on that conversation.

* **event:** TicketEvent `tipo=creacion` (and `visible_cliente=Sí`) via estate repository / ticket timeline — same as 2.6K/2.6N-C harness assertions. Event **id** readable in DB/UI.

* **duplicate detection:**
  * `_crear_ticket_n2` early-return if `conv.ticket_id` set → second create same conv returns existing id (2.6M **PROVEN SAFE** for same-conversation duplicate tickets).
  * Smoke check: count new tickets / `creacion` events for that conversation = 1.

**Minimum smoke evidence pack (existing mechanisms only):**

```text
conversation/request = conversation_id (+ corr)
action               = create_ticket
path                 = runtime
executor             = 1 (one Runtime success log)
ticket_id            = Y (console/DB / STATE result_reference)
TicketEvent          = creacion (id = Z)
duplicate            = 0
```

```text
OBSERVABILITY_FOR_SMOKE = SUFFICIENT
```

Global Legacy path tagging remains `OBSERVABILITY_GAP` (2.6O) — **not** required to close smoke-specific Blocker C.

---

## Legacy limitation

Direct N1 `_crear_ticket_n2` sites (2.6M; **unchanged**):

| Theme (approx) | Class |
|---|---|
| UISP señal / visita | Legacy-only |
| sin internet fijo + humano | Legacy-only |
| frustración/reiteración | Legacy-only |
| baja con deuda | Legacy-only |
| falla óptica | Legacy-only |
| escalamiento genérico | Legacy-only |
| canal_diagnostico_ia escalations (×3) | Legacy-only |

XOR-governed (escape agente / confirmation resume / journey connectivity create when journeys allow): **Runtime-covered** when `ENABLED∧ACTIONS`.

**Smoke selection rule for a future 2.6P:** use a phrase/flow that hits `_ticket_via_runtime_o_legacy` with confirmation (`confirmation_prompt_for("create_ticket")` / pending + «sí»), **not** the Legacy-only escalation themes above.

```text
Legacy = 0  ⇒  XOR helper Legacy branch = 0 for that smoke turn
             ≠  all production creates are Runtime
```

Portal/helpdesk creates remain outside Action Runtime (unchanged).

---

## Production safety

```text
production modified = NO
production restarted = NO
ticket created = NO
event created = NO
config changed = NO
```

No remote hosts contacted. No `.env` writes. No code/deploy changes.

---

## Final classification

```text
BLOCKED
```

### Checklist vs READY_FOR_2.6P

| Criterion | Result |
|---|---|
| Identidad de smoke explícitamente autorizada | **FAIL** — `NOT_AVAILABLE` |
| Mecanismo para verificar configuración efectiva post-restart | **FAIL** — `NO_EXISTING_MECHANISM` (helpers in-code → `CODE_CHANGE_REQUIRED` to expose) |
| Evidencia suficiente Runtime en el smoke | **PASS** — `OBSERVABILITY_FOR_SMOKE = SUFFICIENT` |
| Detección de duplicación | **PASS** — `conv.ticket_id` + Event count |
| Rollback documentado | **PASS** — 2.6O: `ENABLED=false` + `systemctl restart operations-hub-api` |
| Smoke sin modificar código | **PASS** for observability path; **FAIL** overall because A+B unresolved |

### What closed vs what remains

| Blocker | Outcome |
|---|---|
| A — Test identity | Remains open — `NOT_AVAILABLE` |
| B — Effective config | Remains open — `NO_EXISTING_MECHANISM` / `CODE_CHANGE_REQUIRED` |
| C — Smoke observability | **Closed for smoke scope** — `SUFFICIENT` |

### Do not activate

2.6P production activation must **not** start until ops supplies an authorized identity **and** an agreed effective-config proof (ship a later RO probe / boot snapshot — separate phase). Harness proof (2.6N-C) remains valid and does not substitute production smoke prerequisites.
