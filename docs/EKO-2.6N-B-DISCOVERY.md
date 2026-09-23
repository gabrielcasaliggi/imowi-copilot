# EKO 2.6N-B RESULT

**Date:** 2026-09-23  
**Mode:** READ ONLY — no env, services, tickets, or hosts modified  
**Prior:** 2.6N `BLOCKED` / `STAGING_NOT_IDENTIFIED`  

---

## Environment candidates

| Candidate | Evidence | Real/Example | Usable |
|---|---|---|---|
| Production `ibot.ecolan.com` / `soporte.ecolan.com` | `README.md`, `DEPLOY.md` | **IDENTIFICADO** as production audience | Deployment target only — **not** safe isolated rollout without ops approval |
| Staging remote app | No hostname/URL/unit/compose profile in repo | **SOLO_DOCUMENTACIÓN** / aspirational in 2.6L/M/F/B | **NO** |
| DB name `ops_hub_staging` | `restore-estate.sh`, `FASE-1-BATAN.md`, `SECURITY-HARDENING.md` comments | **SOLO_DOCUMENTACIÓN** (restore drill example) | **NO** as full Eko API stack |
| Local development (`APP_ENV=development`, `.env`, `./run.sh`) | `README.md`, `.env.example` | **IDENTIFICADO** as local dev | Dev only — **not** staging substitute (2.6N rule) |
| Pytest / CI harness | `tests/conftest.py` SQLite memory; `.github/workflows/ci.yml` `APP_ENV=development` | **IDENTIFICADO** / **ACTUAL** in CI | **YES** for deterministic Runtime path proof (no real customers) |
| Docker compose `deploy/` | `APP_ENV: production` | Template for **prod-like** stack | **NO** dedicated staging overlay |
| JSC sandbox | `docs/JSC_INTEGRACION.md` | External write mode docs | **NO_VERIFICABLE** as Eko Runtime staging |
| QA Botmaker corpus | `qa_bot/` | Eval/replay artifacts | **NOT** Action Runtime activation environment |

**Situation match (repo evidence):** primarily **C + D + E** from the brief’s taxonomy:

- Remote live service documented = **production only**  
- Safe proof path = **local/CI test harness**  
- Restore/drill = **documented, not a deployed staging app**

---

## ACTION_RUNTIME configuration

| Field | Value |
|---|---|
| source | `app/config.py` via `os.getenv` at process boot |
| default ENABLED | `false` |
| default ACTIONS | frozenset of **13** names including `create_ticket` + `ticket_customer_note` + reads/diag/OV (see 2.6M) |
| override mechanism | Env vars in process environment / `EnvironmentFile=__APP_ROOT__/.env` (`deploy/systemd/operations-hub-api.service`); CSV **replaces** entire ACTIONS set when non-empty |
| isolation by action | **YES** — `ACTION_RUNTIME_ACTIONS=create_ticket` → only that name `covers()` (proven 2.6M) |
| production mechanism | Edit server `.env` + `systemctl restart operations-hub-api` (`DEPLOY.md`) — **same host as production** per docs |
| separate env files for staging | **NOT FOUND** in workspace |
| Correct isolated rollout config (when approved) | `ACTION_RUNTIME_ENABLED=true` + `ACTION_RUNTIME_ACTIONS=create_ticket` — **confirmed**; **not applied** |

---

## Test identity

| Field | Value |
|---|---|
| available | **SAFE_TEST_IDENTITY = NOT_AVAILABLE** for remote/staging |
| evidence | No documented staging abonado/MSISDN/tenant. Local console demos (`admin`/`batan`/…) are **agent** logins (`README.md`), not N1 abonado Runtime create smoke identities. Pytest builds **synthetic** Abonado/Conversacion in-memory (`tests/test_eko_create_ticket_runtime_2_6k.py`, `conftest`) |
| safe for create_ticket (remote) | **NO** without ops-provided identity |
| safe for create_ticket (harness) | **YES** — synthetic fixtures in pytest only |

---

## Deployment

| Field | Evidence |
|---|---|
| deployment mechanism | Native VPS: git pull + venv + systemd (`DEPLOY.md`); optional Docker `deploy/docker-compose.yml`; installers `scripts/install-server.sh`, `deploy-hardening-prod.sh` |
| restart mechanism | `sudo systemctl restart operations-hub-api` (+ frontend/nginx as needed) |
| rollback mechanism | Revert env vars + restart; git rollback for code; DB restore via `backup-estate.sh` / `restore-estate.sh` (drill docs) |
| environment separation | **Not evidenced** beyond local vs production |
| canary / % rollout | **None** for Action Runtime |

---

## Observability

| Signal | Evidence |
|---|---|
| Runtime | Logs `eko_action` / `eko_action_bridge … path=runtime` (`eko_action_bridge.py`, `eko_action_runtime.py`) |
| Legacy create | Weaker — direct `_crear_ticket_n2` without bridge path tag (2.6L/M) |
| Ticket | Estate DB / ticket id in ActionResult data |
| TicketEvent | `tipo=creacion` via repository after create |

Smoke on production would rely on log shipping + DB inspection — **not executed** here.

---

## Recommended path

```text
PATH C — TEST_HARNESS_AVAILABLE
```

**Meaning:** There is **no** evidenced remote staging/QA app. The **safe, deterministic** way to prove

```text
ENABLED=true + ACTIONS=create_ticket
→ Policy → Confirmation → Runtime → Ticket → Event(creacion)
→ XOR Legacy=0
```

is the **existing pytest harness** (already covered in 2.6K / 4C / 4D), not inventing staging or flipping production env.

**Remote note (PATH D reality):** Activating those env vars on the only documented live hosts **is a production change** and requires an **explicit operational approval procedure** — out of scope to execute; document only.

---

## Missing prerequisites

To run a future **2.6N-style remote** rollout (PATH A/B), ops must supply:

1. Staging (or QA) **base URL** distinct from `ibot`/`soporte` production  
2. Staging **env file / secrets** location and ownership  
3. Staging **restart** procedure (unit/compose) proven non-prod  
4. Approved **test abonado** / tenant (not a real customer)  
5. Updated ops docs (`.env.server.example` still stale vs 2.6K defaults)  
6. Optional: dedicated `ops_hub_staging` **API stack**, not only a restore DB name  

To use **PATH C** as formal gate (already largely done in 2.6K):

1. Treat 2.6K pytest + isolation matrix (2.6M) as the technical proof  
2. Record ops decision: “Runtime create proven in harness; remote activation deferred until staging or approved production procedure”  

---

## Safety

```text
production modified = NO
configuration modified = NO
ticket created = NO
event created = NO
```

No remote hosts contacted. No services restarted. No `.env` written.

---

## Situation mapping (brief §2)

| Option | Verdict |
|---|---|
| A staging real, only need to find it | **NO** — not in workspace as operable environment |
| B test env under another name | **Local/CI only** — not remote QA |
| C only production (remote) | **YES** for live audience hosts |
| D local/integration, no remote safe env | **YES** |
| E restore/drill base for staging | **DOCUMENTED**, not deployed as full staging app |
| F other controlled path missed in 2.6N | **NO** additional Runtime staging path found |

---

## Conclusion

```text
2.6N-B PASS
```

(discovery only: operational path identified with evidence; nothing activated)

**Next step (human/ops):** either (1) accept PATH C harness as technical gate and keep Runtime OFF remotely, or (2) provision real staging prerequisites above, then re-attempt 2.6N.
