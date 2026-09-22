# EKO 2.3E — PROACTIVE ANTI-SPAM, DEDUP, COOLDOWN & TOKEN HYGIENE

**Status:** Hardening of outage proactive path only  
**Depends on:** 2.3D PASS  
**Runtime domains enabled:** `outage.started` | `outage.material_update` | `outage.resolved` only  

---

## 1. Current architecture

```text
Outage CRUD
  → authorize_outage_push (policy)
  → deliver_proactive_push (adapter)     ← sole API path (XOR)
  → app_push.notificar_incidente_*
       ├─ claim (declared / material fp / resolved)
       ├─ listar_tokens_afectados_por_nas
       ├─ enviar_push_expo (channelId=eko)
       └─ deactivate DeviceNotRegistered only
  → Expo tickets
```

No scheduler, queue, event bus, or general proactive engine.

---

## 2. Event identity

| Event | Identity used |
|---|---|
| `outage.started` | `outage_id` + type (claim `push_declared_at`) |
| `outage.resolved` | `outage_id` + type (claim `push_resolved_at`) |
| `outage.material_update` | `outage_id` + **sha256(normalized customer_message)** stored in `push_material_fingerprint` |

Canonical conceptual key (when ledger exists later):  
`source + source_event_id(outage_id) + event_type + event_version`  
plus material fingerprint for updates.

**Limitation:** material identity is content-based (customer-safe body), not an external revision ID from ops. Two legitimate updates with identical customer text would collide → documented residual GAP if product needs distinct notifies for identical copy.

No invented external event IDs.

---

## 3. Event dedup vs delivery dedup vs retry

| Concern | Mechanism |
|---|---|
| **EVENT DEDUP** | Same `outage_id` + lifecycle type; material = same fingerprint |
| **DELIVERY DEDUP** | Conditional DB UPDATE claims before Expo; tokens deduped by string |
| **RETRY** | **No automatic retry engine**. Classifications only (`retryable` flag) |

---

## 4. Delivery dedup

- Devices: unique tokens per send batch.  
- Claims prevent second Expo attempt for same logical event/fingerprint.  
- Multi-device: each eligible token in the batch once.

---

## 5. Material update semantics

| Case | Result |
|---|---|
| material #1 (body A) | claim fp(A) → deliver |
| duplicate body A | claim fails → `already_material_fp` |
| material #2 (body B ≠ A) | claim fp(B) → deliver |
| duplicate body B | suppress |

**Not** a boolean `material_claimed` that blocks all future updates.

---

## 6. Claim atomicity

| Claim | Mechanism |
|---|---|
| `push_declared_at` | `UPDATE … WHERE push_declared_at IS NULL` → rowcount==1 wins |
| `push_resolved_at` | same |
| `push_material_fingerprint` | `UPDATE … WHERE fingerprint != :fp` → same fp loses |

**Guarantee:** at-most-one **attempt claim** under concurrent workers sharing the same DB (conditional UPDATE).  
**Not proven:** exactly-once delivery to Expo (see failure windows).

`IDEMPOTENCY GUARANTEE = PARTIAL` (strong for claim; best-effort for provider ack).

---

## 7. Provider result semantics

| Outcome | `ok` | `error_category` | `retryable` |
|---|---|---|---|
| tickets with ≥1 `status=ok` | True if sent>0 | `ok` / `partial` | False |
| all tickets error DeviceNotRegistered | False | `invalid_token` | False |
| HTTP 5xx | False | `transient` | True |
| HTTP 4xx | False | `permanent` | False |
| Timeout | False | `timeout` | True |
| HTTP 200 without parseable tickets | False | `unknown` | True |
| empty token list | True | `no_tokens` | False |

Never: local code path ⇒ delivered.  
Provider message IDs preserved when Expo returns ticket `id`.

---

## 8. Retry behavior

No bounded automatic retry in this path.  
`retryable=True` is informational for operators / future bounded retry (not implemented).

---

## 9. Token hygiene

| Condition | Action |
|---|---|
| Expo `DeviceNotRegistered` | `PortalDevice.activo = No` (no delete) |
| Transient / timeout / 5xx | **no** deactivate |
| Malformed local token | skipped; not sent |

Logs use `token_fingerprint` (sha256 prefix), never full token.

`GAP: STALE-TOKEN-CLEANUP-NOT-SAFE` for ambiguous Expo errors other than DeviceNotRegistered.

---

## 10. Multi-device

0 / 1 / N eligible devices supported.  
Invalid token in batch does not suppress sibling ok tickets (`partial`).

---

## 11. Multi-account isolation

Ownership remains: NAS → `abonado_afectado_por_nas` → devices by DNI.  
No phone→account inference. Unresolved org/outage → policy suppress, no Expo.

---

## 12. Observability

Distinct log moments:

1. `proactive_push skipped` (policy)  
2. `proactive_push attempt`  
3. `outage_push` / `proactive_push result` (provider)

Fields: event_type, event_id, source_event_id, policy_version, customer_scope, sent, provider_ok, skipped, error_category, retryable, provider_msg_ids count, device_tokens, invalid_token_fps.

---

## 13. Metrics

No project-wide metrics platform reused here.  
**GAP: METRICS-INFRA-NOT-PRESENT** — structured logs only.

---

## 14. Failure windows

| Case | Behavior |
|---|---|
| A: claim → crash → no Expo | Declared/resolved **cannot** retry (claim sticky). Material same fp cannot retry. **AT-MOST-ONCE attempt** after claim. |
| B: Expo accept → crash before log | Claim already set → no duplicate send. Possible silent success. |
| C: Expo reject after claim | No auto-retry; declared/resolved stuck without re-notify. **GAP** for operator re-drive. |
| D: unknown result | `ok=False`, not success |

**Exact delivery semantics: AT-MOST-ONCE (claimed attempt) / BEST-EFFORT (Expo receipt).**  
Not exactly-once.

---

## 15. Product cooldown / quiet hours / rate limit

**NOT_IMPLEMENTED** (by design in 2.3E).

Technical loops from double CRUD are mitigated by claims/fingerprints, not by “1 push / N minutes”.

---

## 16. Known gaps

1. Material identity = body hash, not external revision id.  
2. Claim-before-send ⇒ failed Expo cannot auto-retry declared/resolved.  
3. No metrics counters.  
4. No product quiet hours / frequency.  
5. Token hygiene only for DeviceNotRegistered.  
6. Concurrent workers on **different** material fingerprints can both send (intended).

---

## 17. Tests

`tests/test_eko_proactive_push_2_3e.py` + regression 2.3D / e2 / e3 / segmentacion.

Notifications during tests: **NO** (mocks).

---

## 18. Files

| Action | Path |
|---|---|
| Modified | `app/services/app_push.py`, `eko_proactive_push.py`, `estate/models.py`, `estate/migrate.py`, `estate/repository.py` |
| Created | `tests/test_eko_proactive_push_2_3e.py`, this doc |
| Untouched | Billing, CASI, Service Management, outages materiality function, mobile payload shape |
