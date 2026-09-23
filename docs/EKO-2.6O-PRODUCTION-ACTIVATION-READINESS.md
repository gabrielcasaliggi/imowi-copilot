# EKO 2.6O RESULT

**Date:** 2026-09-23  
**Mode:** READ ONLY — no code, env, services, tickets, events, or remote hosts modified  
**Deliverable:** this document only  
**Future target (NOT applied):** `ACTION_RUNTIME_ENABLED=true` + `ACTION_RUNTIME_ACTIONS=create_ticket`  
**Precedents:** 2.6K AGENTIC_READY · 2.6L/M isolation · 2.6N no staging · 2.6N-B PATH C · 2.6N-C isolation PROVEN in harness  

---

## Production target

* **service:** Operations Hub API (FastAPI / uvicorn) — unit `operations-hub-api` (`deploy/systemd/operations-hub-api.service`)
* **deployment:** Same process serves both public hosts documented in `DEPLOY.md` / `README.md`:
  * `ibot.ecolan.com` — agentes / admin
  * `soporte.ecolan.com` — portal abonado (N1)
  * Stack: Nginx → Next.js :3000 + FastAPI :8000 → PostgreSQL  
  * **Native VPS** is the documented production path (`DEPLOY.md`); Docker (`deploy/docker-compose.yml`) is an alternate template — **which mode is live on the server = NOT_DOCUMENTED** beyond “systemd + nginx” as the primary checklist
* **configuration source:** `EnvironmentFile=__APP_ROOT__/.env` on the API systemd unit; values read once at process boot via `os.getenv` in `app/config.py`
* **restart:** `sudo systemctl restart operations-hub-api` (`DEPLOY.md`; installers echo the same). Frontend restart only if UI changed — **not required** for ACTION_RUNTIME env-only flip
* **health check:**
  * Liveness: `GET https://ibot.ecolan.com/health` (also `/ready` for DB readiness) — `scripts/fase1-smoke-batan.sh`, `scripts/fase1-cerrar-checklist.sh`, `DEPLOY.md` checklist
  * Local loopback during install: `http://127.0.0.1:8000/health` (`scripts/install-server.sh`)
* **rollback mechanism (env):** restore previous `ACTION_RUNTIME_*` in server `.env` + same restart (see Rollback procedure). Code/git rollback and DB restore scripts exist but are **out of scope** for a flag-only activation

**Remote production current values of ACTION_RUNTIME_***:** **NOT_PROVEN** (no SSH/API probe in this phase; local workspace `.env` historically ABSENT for these keys per 2.6L/N-B).

---

## Runtime configuration

* **ACTION_RUNTIME_ENABLED:**
  * Default code: `false` (truthy only for `1|true|yes|on`, case-insensitive)
  * Source: env at API boot; systemd `EnvironmentFile` → process env
  * Persistence: line in `__APP_ROOT__/.env` on the production host
  * Restart required: **YES** (module-level constants; no hot reload documented)
  * Effective-value check via public HTTP: **NOT_DOCUMENTED** (`/health` and `/ready` do **not** expose ACTION_RUNTIME_*). Operator verification documented only as inspecting EnvironmentFile / process env on the host after restart, or inferring from first `eko_action` / `eko_action_bridge` log after a known smoke

* **ACTION_RUNTIME_ACTIONS:**
  * Default code: frozenset of **13** names including `create_ticket` (2.6K) plus reads/diag/OV/`ticket_customer_note` (see 2.6M inventory)
  * Override: non-empty CSV **replaces** the entire default set (does **not** merge)
  * Empty / unset → default 13
  * `.env.server.example` comments are **STALE** vs 2.6K defaults (still describe manual listing of create) — ops must follow **code** + this brief, not the stale comment alone

* **future target (NOT applied in 2.6O):**

```text
ACTION_RUNTIME_ENABLED=true
ACTION_RUNTIME_ACTIONS=create_ticket
```

**Why ACTIONS CSV is mandatory:**  
`ENABLED=true` **without** a restrictive `ACTION_RUNTIME_ACTIONS` leaves the **default 13** covered (create + note + show_* + diagnostics + OV + …). That is **not** the isolated rollout.  
**Do not recommend** `ACTION_RUNTIME_ENABLED=true` alone.

**Isolation goal:**

```text
Runtime coverage = create_ticket únicamente
```

Proven in harness (2.6N-C); architecture proven (2.6M).

---

## Blast radius

### What changes with the future target

| Surface | Effect |
|---|---|
| `_ticket_via_runtime_o_legacy` (escape agente, confirmation resume, journeys connectivity create) | `covers(create_ticket)=True` → **Runtime** + confirmation; Legacy branch of helper **off** |
| Direct `_crear_ticket_n2` sites (9 N1; see below) | **Unchanged** — still Legacy-only creates (no Policy Runtime confirmation) |
| Other default ACTIONS (`ticket_customer_note`, `show_*`, diagnostics, …) | `covers=False` → remain **Legacy / unavailable** for Runtime dispatch |
| Portal `POST /portal/tickets`, helpdesk admin APIs | **Unchanged** (not Action Runtime) |
| Mobile app binary | **Unchanged** (same estate ticket contracts) |
| Writer `_crear_ticket_n2` / TicketEvent `creacion` | Same writer; Runtime executor still calls it once when Policy allows |

### Runtime create paths (XOR-governed)

| Path | Classification |
|---|---|
| `_ticket_via_runtime_o_legacy` → `dispatch_runtime` → `_exec_create_ticket` → `_crear_ticket_n2` | **Runtime-covered** when ENABLED∧ACTIONS |
| Helper Legacy branch `if not covers: _crear_ticket_n2` | **Legacy-only** when gate off; unused for create when isolated ON |
| Journey connectivity create (`eko_journeys` → same helper) | **Runtime-covered** when gate ON (also gated by `EKO_JOURNEYS_*` if journeys master off — journeys independent of ACTION_RUNTIME) |

### Legacy create paths (bypass XOR) — from 2.6M, not modified

| Call site (approx) | Caller theme | Classification for smoke “Legacy=0” |
|---|---|---|
| `canal_abonado` ~1616 | UISP señal / visita | **Legacy-only** |
| `canal_abonado` ~2627 | sin internet fijo + humano | **Legacy-only** |
| `canal_abonado` ~5412 | frustración/reiteración | **Legacy-only** |
| `canal_abonado` ~5839 | baja con deuda | **Legacy-only** |
| `canal_abonado` ~7204 | falla óptica | **Legacy-only** |
| `canal_abonado` ~7471 | escalamiento genérico | **Legacy-only** |
| `canal_diagnostico_ia` ~190 / ~255 / ~732 | diag IA escalate | **Legacy-only** |

**Meaning of `Legacy = 0` in a future 2.6P smoke:**  
Applies to the **wired XOR conversation** under test (Runtime dispatch once, helper Legacy branch zero) — **not** a claim that every N1 create in production becomes Runtime. Residual Legacy creates remain reachable via other intents.

### Unaffected actions (under isolated CSV)

All non-`create_ticket` members of the default set stay **not Runtime-covered**, including:  
`installation_status`, `open_OV`, `request_account_selection`, `run_diagnostic_*`, `send_message`, `service_list`, `show_balance`, `show_invoice`, `show_ticket`, `ticket_customer_note`.  
Also never covered by default: `update_ticket`, `escalate_human`, `close_conversation`.

---

## Observability

| Signal | Evidence in repo | Sufficient for 2.6P? |
|---|---|---|
| **Runtime evidence** | `logger.info` `eko_action {… execution_path, action_name, result_status, correlation_id, conversation_id, decision_name, policy …}`; `eko_action_bridge … path=runtime …` (`eko_action_runtime.py`, `eko_action_bridge.py`) | YES for wired path |
| **Legacy evidence** | Direct `_crear_ticket_n2` has **no** `execution_path=legacy` bridge stamp; weaker log story (2.6L) | **OBSERVABILITY_GAP** for proving “all creates = Runtime” |
| **ticket evidence** | Estate Ticket id returned in ActionResult `data.ticket_id`; linked on `ConversacionCanal.ticket_id` | YES (DB / consola) |
| **event evidence** | TicketEvent `tipo=creacion`, `visible_cliente=Sí` via repository after writer | YES (DB) |
| **correlation** | `correlation_id` on Runtime ActionResult / bridge logs | YES for Runtime |
| **Metrics / counters** | No dedicated Runtime vs Legacy counters documented | GAP (non-blocking if logs+DB used) |

**Smoke must not accept HTTP 200 alone.** Required chain:

```text
1 conversation
1 Runtime execution (eko_action / bridge path=runtime, action=create_ticket)
1 create_ticket success
1 ticket id
1 TicketEvent(creacion)
Duplicate = 0 (same conv)
```

---

## Test identity

* **available:** `SAFE_PRODUCTION_TEST_IDENTITY = NOT_AVAILABLE`
* **authorized:** **NO** documented ops-authorized abonado/MSISDN/tenant for production `create_ticket` Runtime smoke
* **evidence:**
  * 2.6N / 2.6N-B: no staging identity; console demos (`admin` / `batan` / …) are **agent** logins, not N1 abonado create identities
  * `docs/PORTAL-ABONADO.md` “Demo abonado” (tel/DNI table) is a **local/demo** fixture description — **not** an authorization to create real tickets in production; prod checklist expects `DISABLE_DEMO_USERS=true` (`DEPLOY.md`)
  * Pytest synthetic Abonado/Conversacion (2.6K / 2.6N-C) — **harness only**, not mappable to production without ops provision

**Rule for 2.6P:** do not invent an abonado; do not use administrator MSISDN; wait for an explicitly authorized test identity.

---

## Activation procedure

*(Documentary design for future **2.6P**. **Do not execute in 2.6O.**)*

### Pre-check

1. Confirm operator window + change approval for production `ibot`/`soporte` API only.
2. Health: `curl -fsS https://ibot.ecolan.com/health` and `/ready` → OK / ready.
3. Record **current** lines (or absence) of `ACTION_RUNTIME_ENABLED` and `ACTION_RUNTIME_ACTIONS` from `__APP_ROOT__/.env` on the API host (backup/copy values). Expect historically OFF / ABSENT → code defaults (**NOT_PROVEN** remotely in this audit).
4. Confirm authorized smoke identity is in hand (**currently blocks** — see Missing prerequisites).
5. Confirm log access can filter `eko_action` / `eko_action_bridge` / `path=runtime` for the smoke window.
6. Optional: `sudo bash scripts/backup-estate.sh` before any env change (`DEPLOY.md`).

### Activation

7. Edit **only** the API host `__APP_ROOT__/.env` (systemd `EnvironmentFile`) to set **exactly**:

```text
ACTION_RUNTIME_ENABLED=true
ACTION_RUNTIME_ACTIONS=create_ticket
```

   Do **not** omit `ACTION_RUNTIME_ACTIONS` (would activate default 13).  
   Do **not** set Docker/CI/other hosts unless that is proven to be the live API (native systemd is the documented primary path).

### Restart

8. `sudo systemctl restart operations-hub-api`  
9. Wait for process up; re-check `/health` and `/ready` (install scripts retry `/health` — allow short settle).

### Post-check

10. Confirm `.env` still contains the two target lines (persistence).  
11. Effective in-process: **no public endpoint documented** — verify via host process env / first Runtime log after smoke. If ops cannot verify effective values → **FAIL** activation.

### Smoke (authorized identity only)

12. Single N1 conversation (portal `soporte` or WA mapped to same motor — channel must be the one under test):

```text
N1 → Proposal → Policy → Confirmation → Runtime → create_ticket → Ticket → TicketEvent(creacion)
```

13. Prefer intents that hit `_ticket_via_runtime_o_legacy` (e.g. escape/agente with confirmation), **not** known Legacy-only escalation phrases from § Blast radius, so the smoke measures Runtime XOR rather than residual Legacy.

### Validation

14. Expect for that conversation:

```text
Runtime = 1
Legacy (XOR helper branch) = 0
Ticket = 1
Event(creacion) = 1
Duplicate = 0
path = runtime
action = create_ticket
```

15. Confirm other default actions remain uncovered (no accidental `eko_action` Runtime for `ticket_customer_note` / show_* unless separately intended).

### Rollback

16. See next section — execute immediately on any Failure condition.

---

## Rollback procedure

*(Real mechanism from docs — env + restart. **Not executed now.**)*

1. **What:** set `ACTION_RUNTIME_ENABLED=false` (or restore exact pre-change values of both ACTION_RUNTIME_* vars). Leaving `ACTION_RUNTIME_ACTIONS=create_ticket` while ENABLED=false is safe (covers False).
2. **Where:** `__APP_ROOT__/.env` on the API host (`EnvironmentFile` of `operations-hub-api`).
3. **Restart:** `sudo systemctl restart operations-hub-api`.
4. **Time to effect:** after successful restart / workers up — config is boot-time; no documented hot reload. Exact seconds **NOT_DOCUMENTED**; use `/health`+`/ready` as readiness signals.
5. **Verify Runtime OFF:** no new `eko_action_bridge … path=runtime … action=create_ticket` on subsequent XOR-style turns; helper uses Legacy writer when create is needed. Host `.env` shows ENABLED false/absent.
6. **API healthy:** `GET /health` and `GET /ready` OK.

If host access or EnvironmentFile path cannot be confirmed at activation time → treat as **ROLLBACK_NOT_DOCUMENTED** for that environment and **do not activate**.

---

## Failure conditions

Future 2.6P activation is **FAIL** if any of:

* Runtime + Legacy (XOR helper) on the same create turn  
* Runtime calls > 1 or executor/writer > 1 for the smoke conversation  
* More than one new Ticket or more than one `creacion` Event for that conversation  
* `execution_path` ≠ `runtime` on the expected create  
* Policy deny / confirmation broken / unexpected `needs_confirmation` after trusted «sí»  
* Effective config ≠ `ENABLED=true` + `ACTIONS=create_ticket` (e.g. default 13 covered)  
* Any other default action accidentally Runtime-covered  
* `/health` degraded or `/ready` 503 after restart  
* Rollback cannot be performed or verified  
* Ticket created on unauthorized / wrong identity  
* Observability insufficient to show Runtime path for the smoke  
* Smoke uses a Legacy-only call site and is misread as Runtime success  

---

## Missing prerequisites

| Prerequisite | Status | Blocks 2.6P? |
|---|---|---|
| Production hosts / API unit identified | YES (`DEPLOY.md`, systemd unit) | No |
| Config location (`.env` + EnvironmentFile) | YES | No |
| Restart command | YES | No |
| Rollback (ENABLED=false + restart) | YES | No |
| Isolation config proven (harness) | YES (2.6N-C) | No |
| Authorized production smoke identity | **NOT_AVAILABLE** | **YES** |
| Public/API proof of effective ACTION_RUNTIME after restart | **NOT_DOCUMENTED** | **YES** (ops must accept SSH/host env inspection + log inference, or add a later RO probe — not in 2.6O) |
| Absolute Legacy=0 for all N1 creates | False claim — 9 Legacy-only sites remain | Limitation (document; not dual-write on XOR) |
| Staging remote | NOT_IDENTIFIED (2.6N) | Accepted; activation is production-only |
| Stale `.env.server.example` | STALE vs code | Ops hygiene (non-blocking if procedure uses this doc) |

---

## Final status

```text
BLOCKED
```

**Reason (blocking):** no **authorized** production test identity; without it a 2.6P smoke cannot be executed safely. Secondary gap: no documented **public** post-restart proof of effective `ACTION_RUNTIME_*` (host file/process inspection only).

**What is ready for when prerequisites land:**

* Where to change (API `__APP_ROOT__/.env`)  
* What to set (`ENABLED=true` + `ACTIONS=create_ticket` — never ENABLED alone)  
* How to restart (`systemctl restart operations-hub-api`)  
* How to health-check (`/health`, `/ready`)  
* How to observe Runtime (`eko_action` / `path=runtime`)  
* How to roll back (`ENABLED=false` + restart)  
* Exact meaning of XOR `Legacy=0` vs residual Legacy-only creates  

```text
2.6O does NOT activate production.
production modified = NO
remote ticket = NO
remote event = NO
```

**Do not proceed to 2.6P until** `SAFE_PRODUCTION_TEST_IDENTITY` is ops-provided and effective-config verification for the live host is agreed.
