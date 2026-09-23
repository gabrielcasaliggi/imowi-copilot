# EKO — Production smoke test identity (Blocker A)

**Date:** 2026-09-23  
**Source:** designación operativa en sesión (operador del proyecto)  
**Mode:** registro documental — **no** se consultó producción, BillTrack ni estate remoto  

---

## Designation

| Field | Value |
|---|---|
| Identifier type | DNI |
| Identifier | `24914867` |
| Role | Smoke N1 `create_ticket` Runtime (máx. 1 ticket + 1 TicketEvent `creacion` en la ventana de 2.6P) |
| PIN / secrets | **not stored** — el operador los usa solo en el cliente (portal); nunca en chat ni en git |
| Admin access | not required |
| Abonado data changes | not required / not authorized by this note |

---

## Authorization scope (as stated for smoke)

- Controlled Eko Runtime smoke only  
- May create **one** real ticket and its `creacion` event  
- No administrative console use implied  
- No modification of abonado master data  

**Operator confirmation outstanding (recommended before 2.6P):**  
explicit check that this DNI is a **test-destined** line/account (not an arbitrary live customer). If it is a live residential account, reconfirm written acceptance of one real ticket.

---

## Operator confirmation (2026-09-23)

```text
test / smoke use authorized by project operator = YES
("si podes hacerlo" — proceed with controlled smoke using this DNI)
```

PIN remains offline with the operator. Agent does **not** perform portal login.

---

## Not verified in this note

| Item | Status |
|---|---|
| Exists in production BillTrack / estate | **NOT_VERIFIED** (no remote lookup) |
| MSISDN / portal login path | **NOT_DOCUMENTED** here — operator supplies at smoke time |
| Channel (portal `soporte` vs WA) | Operator chooses; prefer path that hits `_ticket_via_runtime_o_legacy` + confirmation |
| Name / plan / address | **not recorded** (minimize PII in repo) |

---

## Blocker A status

```text
SAFE_PRODUCTION_TEST_IDENTITY = AVAILABLE_AND_AUTHORIZED
```

Authorization basis: project operator designation of DNI `24914867` for controlled smoke (this document), confirmed 2026-09-23.

Remaining before **activation** 2.6P (separate phase):

1. Deploy/restart with 2.6Q startup log if not already live (code may need deploy)  
2. Set env `ACTION_RUNTIME_ENABLED=true` + `ACTION_RUNTIME_ACTIONS=create_ticket`  
3. Confirm boot log `action_runtime.enabled=true action_runtime.actions=create_ticket`  
4. Operator logs in with this DNI (PIN kept offline) and runs XOR confirmation smoke  
5. Rollback plan from 2.6O ready  

**Do not activate from this document alone.**

---

## Safety

```text
production modified = NO
production queried = NO
PIN stored = NO
```
