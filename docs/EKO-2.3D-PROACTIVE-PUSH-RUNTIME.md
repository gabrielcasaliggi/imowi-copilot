# EKO 2.3D — PROACTIVE PUSH RUNTIME

**Status:** Implemented (minimal)  
**Scope:** `ProactiveDecision(ALLOW)` → App Push for outage lifecycle only.

## Architecture

```text
Outage CRUD (ops)
  → authorize_outage_push (policy)
  → deliver_proactive_push (adapter)   ← único camino API
  → app_push.notificar_incidente_*
  → Expo (channelId=eko)
```

**XOR:** `app/api/v1/outages.py` no llama `notificar_incidente_*` directamente.  
Dedup legado (`push_declared_at` / `push_resolved_at`) permanece dentro de `app_push`.

## Modules

| Module | Role |
|---|---|
| `eko_proactive_contract.py` | Types + `SUPPORTED_PROACTIVE_EVENTS` |
| `eko_proactive_policy.py` | ALLOW/SUPPRESS/NOT_ELIGIBLE/INVALID |
| `eko_proactive_push.py` | Adapter → existing push |

## Enabled events

- `outage.started` → legacy payload `event=declared`
- `outage.material_update` → `updated` (only after `outage_update_es_material`)
- `outage.resolved` → `resolved`

All other domains → `SIGNAL_NOT_SUPPORTED` / no push.

## Mobile

Payload unchanged (`tipo=incidente`, `outage_id`, `event`). No mobile change.  
Deep-link URL: not present historically — GAP only if product wants URL scheme later.

## Explicit non-goals

No scheduler, billing/ticket/connectivity/service proactive, WA/TG proactive, general ledger.
