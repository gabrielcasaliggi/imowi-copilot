# EKO 2.6Q RESULT

**Date:** 2026-09-23  
**Scope:** Blocker B only — effective ACTION_RUNTIME_* observability  
**Does not:** activate production · resolve test identity (A) · create tickets · deploy/restart prod  

---

## Change

Startup log after production config avisos in `main.py` lifespan, calling:

```text
app.services.eko_action_bridge.log_effective_action_runtime_config()
```

Helpers (same module / same globals as `action_runtime_covers`):

* `effective_action_runtime_config()` → `{enabled: bool, actions: sorted list}`
* `log_effective_action_runtime_config()` → logs and returns that snapshot

Log line (logger `operations_hub`):

```text
action_runtime.enabled=<true|false> action_runtime.actions=<csv sorted>
```

Example after isolated rollout env + restart (future ops):

```text
action_runtime.enabled=true action_runtime.actions=create_ticket
```

No new endpoint. No second config parser.

---

## Effective configuration

| Question | Answer |
|---|---|
| Source of truth | Module globals `ACTION_RUNTIME_ENABLED` / `ACTION_RUNTIME_ACTIONS` in `eko_action_bridge` (imported once from `app.config` at process load — same bindings `covers()` / `dispatch_runtime` gate use) |
| When logged | Lifespan startup, after config fatales/avisos, before estate seed — values already resolved at import |
| How operator proves process load | After API restart, journal/app log contains the `action_runtime.enabled=… actions=…` line from that boot |
| Isolation visible | CSV replace-all reflected in `actions=` list (e.g. only `create_ticket`) |

Tests assert snapshot `enabled`/`actions` match `action_runtime_master_enabled()` / `action_runtime_covers()` for the same monkeypatched globals.

---

## Security

```text
no secrets logged     = YES (only enabled + action name allowlist)
no public endpoint    = YES (startup log only)
no production access  = YES (local code/tests only this phase)
```

No passwords, tokens, DSNs, or connection strings in this log path.

---

## Tests

| Suite | Result |
|---|---|
| `tests/test_eko_effective_config_observability_2_6q.py` | PASS (4) — Cases A/B/C + source-of-truth match |
| `tests/test_eko_create_ticket_runtime_2_6k.py` | PASS |
| `tests/test_eko_runtime_isolation_2_6nc.py` | PASS |
| `ruff check` on `eko_action_bridge.py`, `main.py`, new test | PASS |

---

## Regression

```text
2.6K  = PASS
2.6N-C = PASS
```

No Runtime/Legacy/Policy/CASI behavior change — observability-only.

---

## Production

```text
production modified = NO
production restarted = NO
production ticket = NO
production event = NO
```

---

## Status

```text
PASS
```

### Blocker board (post-2.6Q)

```text
A = BLOCKED   (SAFE_PRODUCTION_TEST_IDENTITY = NOT_AVAILABLE — out of scope)
B = RESOLVED  (startup effective config log)
C = RESOLVED  (unchanged; smoke observability already SUFFICIENT)
```

**Next (external):** ops-authorized smoke identity only. Do **not** run 2.6P from this phase.
