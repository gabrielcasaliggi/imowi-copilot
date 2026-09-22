# EKO 2.2I — FINAL COMMERCIAL AUTHORITY TRACE

**Status:** READ-ONLY discovery complete  
**Runtime impact:** NONE — documentation only  
**External calls:** NONE  
**Writes:** NONE  
**Depends on:** 2.2A–2.2H PASS

---

## 1. Purpose

Última traza interna del workspace para responder:

> ¿Existe evidencia concreta del sistema comercial autoritativo y del writer de `public.api_service`?

Sin implementar integración, adapters, EFFECT ni llamadas externas.

---

## 2. Method

| Constraint | Applied |
|---|---|
| Workspace-only | Yes |
| No INSERT/UPDATE/DELETE/ALTER | Yes |
| No commercial API WRITE calls | Yes |
| No interactive login to external systems | Yes |
| No secret values reproduced | Yes |
| Inference without evidence rejected | Yes |

Searches covered: `api_service` / `api_invoice` / writers / CRM·BSS·ERP / provisioning / jobs·ETL / OV·JSAT / JSC / installation·agenda / config URL clients / estate models / docs.

---

## 3. `api_service` Writer Trace

### 3.1 Direct WRITE evidence

| Search | Result |
|---|---|
| `INSERT INTO … api_service` | **NOT_FOUND** in workspace |
| `UPDATE … api_service` | **NOT_FOUND** |
| UPSERT / COPY / stored procedures writing `api_service` | **NOT_FOUND** |
| Migrations / Alembic targeting BillTrack `api_service` | **NOT_FOUND** |
| ETL / cron / Celery / RQ sync → `api_service` | **NOT_FOUND** |
| Webhook / importer writing services padrón | **NOT_FOUND** |

### 3.2 Observed uses of `api_service` (all READ)

| File | Symbol / usage | Operation |
|---|---|---|
| `app/services/billtrack.py` | SQL `FROM public.api_service` / joins | **SELECT only** |
| `app/services/portal_services.py` | Catalog via BillTrack lookups | READ |
| `app/services/conexion_pppoe.py` | Resolve service for PPPoE | READ |
| `app/radius/contract.py` | Docstring / types | DOCUMENTATION |
| `tools/billtrack_ro_probe.py` | Schema probe | READ-ONLY tool |
| `app/services/eko_invoice_reader.py` | Related `api_invoice` READ | READ |

### 3.3 Client-side WRITE prohibition (Eko → BillTrack)

| Evidence | Classification |
|---|---|
| Module docstring: BillTrack = Postgres externo **solo lectura** | AUTHORITATIVE for Eko access posture |
| Lookup SQL must start with `SELECT` / `WITH` (`billtrack.py` lookup paths) | Hard reject non-SELECT on configurable SQL |
| Hardcoded service queries are SELECT | READ-ONLY |
| `DEPLOY.md` / `docs/CONFIG-PLATAFORMA.md`: usuario `billtrack_reader`, sin writes | DOCUMENTATION + ops policy |
| `tools/billtrack_ro_probe.py`: asserts no INSERT/UPDATE/DELETE grants for probe role | READ-ONLY tooling |

**Conclusion — who writes `api_service`?**

| Classification | Value |
|---|---|
| Answer | **UNKNOWN / NOT_FOUND** inside this workspace |
| Standard | Not FOUND (no concrete writer identity) |
| Note | Eko is a **consumer** of `api_service`, not its maintainer |

Naming alone (e.g. BCM “número ERP” = BillTrack `client_number`) is **not** evidence of who inserts/updates `api_service`.

---

## 4. Commercial Authority Candidates

| Candidate | Type | Classification | Evidence |
|---|---|---|---|
| BillTrack Postgres | External DB padrón | **READ-ONLY** (from Eko) | `billtrack.py`, config, DEPLOY |
| Data Estate `abonados` | Local cache / channel identity | **WRITE-CAPABLE** for estate only; **not** BillTrack SoT | `estate/models.py` Abonado; sync from lookup |
| Data Estate tickets / KB | Support ops | WRITE estate; **not** commercial product SoT | ORM models |
| OV Batán API | Session + deep-links | **NAVIGATION** / limited READ (links, session) | `ov_batan.py`, INTEGRACION-OV brief |
| JSAT / `/ov/handoff` | Auth handoff | **HANDOFF** / EXTERNAL optional | `config.py` OV_HANDOFF off by default |
| JSC | Mobile line demo | **DEMO** / DOCUMENTATION_ONLY for HTTP | `jsc/connector.py` seed; `docs/JSC_INTEGRACION.md` planned |
| Radius API | PPPoE session | **READ-ONLY** tech | `radius/client.py` get/list only |
| UISP | Radio CPE | **READ-ONLY** tech | `uisp/client.py` |
| Sopnet BCM | FTTH ONU | **READ-ONLY** tech; “ERP number” = CN label | `bcm/client.py`, CONFIG-PLATAFORMA |
| Playbooks `alta_plan` / `baja_servicio` | Conversation | **HANDOFF** | `flujos_abonado.py` `[HANDOFF_HUMANO]` |
| KB / RAG comercial | Content | **DOCUMENTATION_ONLY** / informativo | rag collections |
| `domain_adapter` | Conversation lifecycle | Not commercial BSS | `app/domain/domain_adapter.py` |
| Named “OSS/BSS” in resumen | Aspirational | **DOCUMENTATION_ONLY** / PLANNED | `docs/OPERATIONS-HUB-RESUMEN.md` |

**No AUTHORITATIVE commercial WRITE system identified in-repo.**

---

## 5. APIs / Endpoints Found (commercial relevance)

| Integration | Methods observed in-repo | Commercial WRITE alta/baja/plan? |
|---|---|---|
| OV (`OV_BATAN_API_URL`) | `POST` session login; `GET` session/check; fast-link GET | **No** — auth + links (NAVIGATION/READ) |
| Radius | GET NAS / sessions | No |
| UISP | GET CPE | No |
| BCM | GET ONU (documented RO) | No |
| JSC HTTP | Suggested endpoints in contract only | **Not implemented** (DOCUMENTATION_ONLY) |
| Expo push / WhatsApp / AI / Whisper / TTS | Unrelated to commercial catalog | No |

Credential config keys exist for BillTrack, OV, Radius, UISP, BCM, Supabase, WhatsApp, AI:  
`SECRET/credential exists — value not inspected/reproduced`.  
**No CRM/BSS/commercial-API credential keys found** as a dedicated commercial transaction client.

---

## 6. Catalog / Pricebook

| Source | Role | Authoritative for transaction? |
|---|---|---|
| `api_service.product` / `product_code` | Informational labels in READ model | **No** |
| Portal catalog / `service_list` | READ projection for UX (2.2A) | **No** |
| Dedicated pricebook API / table | | **NOT_FOUND** |
| Eligibility engine | | **NOT_FOUND** |

---

## 7. Eligibility

**NOT_FOUND** as API, table, or service client. Playbook/RAG text is not an eligibility engine.

---

## 8. Installation / Work Orders

| Candidate | Classification |
|---|---|
| `installation_status` Runtime (2.2D) | Honest **UNAVAILABLE** |
| Playbook `turno_campo` | **HANDOFF** (support visit ask), not structured install order |
| Tickets N1/N2 | Support tickets ≠ commercial installation orders |
| Structured agenda / work_order / appointment tables (authoritative) | **NOT_FOUND** |
| KB `instalacion.md` | DOCUMENTATION_ONLY |

---

## 9. Jobs / Workers / ETL

| Pattern | Commercial sync to BillTrack / catalog? |
|---|---|
| Backup cron (`scripts/install-backup-cron.sh`) | Ops backup — not commercial writer |
| Celery / RQ commercial sync | **NOT_FOUND** |
| BillTrack → Estate: `ensure_local_abonado` after lookup | Cache WRITE to **estate** only; does **not** write BillTrack |
| JSC seed | Demo seed of `lineas_jsc` |

**No SOURCE → TRANSFORM → TARGET pipeline found that writes `api_service`.**

---

## 10. Schemas

| Store | Commercial service SoT? |
|---|---|
| BillTrack `api_*` (external) | READ model for Eko; writer **UNKNOWN** outside workspace |
| Data Estate (`organizations`, `abonados`, tickets, KB, `lineas_jsc`, …) | Ops / channel / demo — **not** BillTrack writer |
| `supabase/schema.sql` | Estate/tickets oriented — no `api_service` writer |

---

## 11. Authority Matrix (final)

| Capability/Data | Source in workspace | READ | WRITE | Authoritative | Evidence |
|---|---|---:|---:|---:|---|
| customer / person | BillTrack `api_person` | Yes | No (Eko) | Unknown SoT writer | billtrack SELECT |
| `client_number` | BillTrack + TrustedContext | Yes | No invent | Trusted for ownership | CASI / billtrack |
| service row | BillTrack `api_service` | Yes | No (Eko) | **Unknown writer** | SELECT only |
| product label/code | `api_service` fields | Yes | No | Informational only | portal_services |
| plan (commercial auth) | — | — | — | **NOT_FOUND** | — |
| price | — | — | — | **NOT_FOUND** | — |
| eligibility | — | — | — | **NOT_FOUND** | — |
| service activation (alta) | Playbook handoff | — | — | **HANDOFF_ONLY** | flujos_abonado |
| service cancellation | Playbook handoff | — | — | **HANDOFF_ONLY** | flujos_abonado |
| plan change | Playbook / intent handoff | — | — | **HANDOFF_ONLY** | 2.2E/F |
| service addition | — | — | — | **UNAVAILABLE** | 2.2E |
| installation order | — | — | — | **UNAVAILABLE** | 2.2D |
| transaction status | — | — | — | **NOT_FOUND** | — |
| OV deep-links | OV API | Limited | Session login only | NAVIGATION | ov_batan |
| JSC line | Demo seed | Demo | Demo local | DEMO | jsc/connector |

---

## 12. Evidence Classification Summary

| Class | Items |
|---|---|
| AUTHORITATIVE (commercial WRITE SoT) | **None found** |
| WRITE-CAPABLE (non-SoT / estate) | Estate tickets, abonados cache, platform settings |
| READ-ONLY | BillTrack, Radius, UISP, BCM, invoice reader |
| NAVIGATION | OV public/fast links |
| HANDOFF | alta_plan, baja_servicio, turno_campo, escalate human |
| DEMO | JSC connector / lineas_jsc seed |
| DOCUMENTATION_ONLY | JSC HTTP plan, OSS/BSS aspirational mentions, 2.2G/H contracts |
| UNKNOWN / NOT_FOUND | Writer of `api_service`; commercial BSS identity |

---

## 13. Final Decision

### CASE C — NOTHING FOUND (for commercial authority)

```text
EXTERNAL DEPENDENCY — NOT AVAILABLE IN WORKSPACE
```

Refined answers:

| Question | Classification |
|---|---|
| Who writes `api_service`? | **UNKNOWN / NOT_FOUND** (not FOUND) |
| Authoritative commercial system identity? | **NOT_FOUND** |
| Commercial WRITE API in-repo? | **NOT_FOUND** |
| Confirmation vs 2.2F? | **No contradictory evidence**; no new integration missed that qualifies as AUTHORITATIVE |

**Not** CASE A (AUTHORITY IDENTIFIED).  
**Not** CASE B (no demonstrated commercial WRITE-capable integration usable as SoT).

---

## 14. Recommendation (next step — outside Cursor coding)

Stakeholder engagement with Ecolan/Batán:

1. Identify system of record for services / contracts / products.  
2. Confirm whether BillTrack `api_service` is a mirror and of what (lag, writer).  
3. Provide WRITE API / catalog / eligibility / status contracts if automation is desired.  
4. Only then reopen engineering under 2.2G/H activation gate.

**Do not** implement CommercialAdapter EFFECT until that formal identification exists.

---

## Document control

| Field | Value |
|---|---|
| Document id | `eko-2.2i-final-commercial-authority-trace` |
| Code modified | **None** |
| External commercial calls | **None** |
| Secrets inspected/printed | **None** |
