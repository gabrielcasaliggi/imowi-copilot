# EKO 2.7 — Product Coverage & Self-Service Discovery

**Date:** 2026-09-23  
**Mode:** READ ONLY — product map after 2.6 CLOSED  
**Sources:** code + docs 2.1–2.6T, mobile README/BACKEND_CAPABILITIES, ENTRENAMIENTO-N1, CONFIG-PLATAFORMA  
**Not done:** implementation, config, Runtime activation, production, DB, mobile changes  

---

## Executive Summary

Eko hoy es una **plataforma de autoservicio ISP operativa** en el núcleo conversacional N1 + portal/app:

* Facturación **READ** (saldo / factura limitada) vía BillTrack RO + handoff OV para pagar  
* Inventario y selección de servicios + diagnósticos de **Internet fijo**  
* Tickets customer-facing: **crear** (Runtime en prod), **consultar**, **nota visible** (código READY; CSV prod aislado a create)  
* Proactivo: **outage** + **ticket** push (2.3H READY)  
* Continuidad conversacional **2.5 FROZEN**  
* App mobile con Home / chat / tickets / billing / connectivity / push / voz (voz/push condicionados a build Firebase)

**No** es aún un BSS completo: no ejecuta pagos, no efectos comerciales, no ciclo de vida de instalación como EFFECT, no close/resolve/reassign Agentic, Sensa/VoIP mayormente **triage + handoff**.

El próximo milestone debe elegirse entre **gaps de valor cliente** (billing depth, proactive billing, experience “sin internet”, note en prod CSV, paridad mobile) vs **dependencias externas** (BSS/CRM) — no reabrir Agentic Ops 2.6.

---

## 2.6 Baseline

```text
EKO 2.6 Agentic Ops = CLOSED
```

| Closed customer-facing | Composition | Honest unavailable | Out of scope / deps |
|---|---|---|---|
| show_balance, show_invoice, service_list, request_account_selection, show_ticket, diagnostics PPPoE/BCM/UISP, open_OV, create_ticket, ticket_customer_note | escalate_human → create_ticket | installation_status | update_ticket, close_*, resolved, reassign, admin mutate, payment exec, commercial effects, install order |

* CASI = PASS  
* Prod Runtime mutation scope = **`create_ticket` only** (`ACTIONS=create_ticket`)  
* Prod evidence = 2.6P / Ticket **IBOT-1066** / path=runtime / XOR PASS  

---

## Product Surface Map

| Surface | Role |
|---|---|
| A Conversational N1 | Motor + Runtime Actions + Legacy canals (WA/web/app) |
| B Billing | BillTrack RO + OV links |
| C Services | BillTrack inventory + selected_service_ref |
| D Connectivity | Portal connectivity + PPPoE/BCM/UISP + outages |
| E Tickets | Estate tickets/Events + Runtime create/note |
| F Proactive / Push | Outage + TicketEvent → Expo |
| G Mobile | Expo app same N1 API |
| H Voice | `/portal/audio` Whisper → N1 |
| I OV | Authenticated deep links (pagar, cuenta, …) |
| J Multi-account | Phone→N CNs; request_account_selection |
| K Sensa | Intent `tv_sensa` playbooks / guardrails |
| L VoIP / fija | Intent telefonia; not diagnosticable PPPoE |
| M Web / Portal | soporte.ecolan.com + ibot console |
| N Context / Continuity | 2.5 FROZEN SoT |
| O Observability | eko_action logs; health; metrics journeys |
| P Security / Authority | CASI; BillTrack RO; ownership |

---

## Billing

| Capability | State | Source | Notes |
|---|---|---|---|
| Balance / deuda | **AVAILABLE** | BillTrack `api_person` | `show_balance` Runtime |
| Plan (label) | **PARTIAL** | BillTrack / facts | Shown in context; not full commercial plan SoT |
| Factura (header FC) | **AVAILABLE** | BillTrack `api_invoice` | `show_invoice`; limited fields (2.6H) |
| Vencimiento due_date | **UNAVAILABLE** / **PARTIAL** | BillTrack FC insufficient (2.6H / 2.3) | Gap A |
| Payment slip / PDF | **EXTERNAL/HANDOFF** | OV | open_OV destinations |
| Historial de pagos | **UNAVAILABLE** | — | Gap A / C |
| Payment execution | **EXTERNAL/HANDOFF** | OV / PSP | Out of 2.6 scope |
| Links OV | **AVAILABLE** | OV handoff | `open_OV` allowlist |
| Detalle línea factura | **UNAVAILABLE** | BillTrack RO limits | Gap A / C |
| Cuenta corriente | **UNAVAILABLE** | — | Gap A / C |
| Múltiples cuentas billing | **PARTIAL** | Phone lookup + selection | Disambiguation WA/F1 |

**Direct answers:** saldo, factura limitada, guía a pagar vía OV.  
**Navigate only:** pago, talón, muchos trámites OV.  
**External auth:** OV link resolution by celular.

---

## Services

| Capability | Class | State |
|---|---|---|
| Listado servicios | READ | **AVAILABLE** (`service_list`) |
| Selección servicio | READ/STATE | **AVAILABLE** (`selected_service_ref` / request_account_selection) |
| Servicio activo / tipo | READ | **AVAILABLE** (inventory) |
| Estado administrativo | READ | **PARTIAL** (fields present if BillTrack provides) |
| Conectividad / diagnóstico | DIAGNOSTIC | **AVAILABLE** fixed Internet; **UNAVAILABLE** for Sensa/VoIP probes |
| Instalación status | READ | **HONEST_UNAVAILABLE** (2.2D / 2.6) |
| Alta / baja / upgrade / price | COMMERCIAL ACTION | **EXTERNAL/HANDOFF** (2.2E / 2.4) |

Self-service = READ + diagnostic Internet. Mutations comerciales = humano/BSS.

---

## Connectivity

Journey “no tengo internet” (supported pieces):

1. Identify / select service (`selected_service_ref`) — **READY**  
2. Outage NAS — **READY** (proactive + N1 awareness)  
3. PHY / session / quality via portal connectivity — **READY** when service_id  
4. PPPoE / BCM / UISP probes — **READY** with PARTIAL Legacy hot path for BCM/UISP  
5. Recommendation / ticket / escalate — **READY** via create_ticket composition  

**Experience gaps (A):** clearer single narrative UX when multi-service; residual Legacy creates outside XOR; diag IA Legacy ticket.  
**Known:** PPPoE tests historically noisy (fixtures aligned 2.5D); not a product blocker.  
**Not product gaps:** missing BSS install EFFECT; Sensa not PPPoE-diagnosticable (by design).

---

## Tickets

| Capability | Customer SS | Agentic Ops | Admin/Legacy |
|---|---|---|---|
| Create | **READY** (Runtime prod) | CLOSED 2.6 | — |
| Show / list | **READY** | show_ticket | console |
| Customer note | **READY** (code); prod CSV may exclude | 2.6I | agent notes API |
| History / Events | **PARTIAL** (portal/app activity) | Events Sí | full timeline |
| Status customer-visible | **PARTIAL** | via Events | admin estado |
| Close / resolve / reassign | **OUT_OF_SCOPE** | no ActionSpec | helpdesk |
| update_ticket evidence | internal | PARTIAL / no activar | — |
| SLA breach push | proactive | 2.6A | — |
| Escalate | composition create | COMPOSITION_READY | — |

Baseline 2.6: do **not** implement update_ticket for “completeness.”

---

## Proactive

| Stage | Outage | Ticket | Billing | Connectivity lost/restored | Service lifecycle |
|---|---|---|---|---|---|
| DETECT | YES | YES (Event) | NO | NO | NO |
| DECIDE | YES (policy 2.3C) | YES | — | — | — |
| NOTIFY | YES Expo | YES Expo | — | — | — |
| DISPLAY | Home incidente | Activity ticket | — | — | — |

**Already communicate:** outage started/material/resolved; ticket created/updated/closed (visible Events).  
**Not detect:** billing due/payment; connectivity cascade as proactive event; commercial service activated.  
**Could notify if generated:** more customer-visible Events (product decision) — not invent detectors without SoT (2.3F).

---

## Mobile

Baseline claimed (ops): Expo 54 / RN 0.81.5 / APK ~1.0.6; push/voz/tickets/billing/connectivity working when Firebase configured.

| Area | State |
|---|---|
| HOME | **READY** (summary cards) |
| EKO ASSISTANT (chat) | **READY** |
| PUSH | **READY**† (preview APK may disable FCM) |
| VOICE | **READY**† (`/portal/audio`; preview may disable mic) |
| TICKETS | **READY** |
| BILLING | **READY** (balance card + OV) |
| SERVICES | **READY** |
| CONNECTIVITY | **READY** |
| ACCOUNT | **READY** (PIN/session) |
| OV | **READY** (links) |
| ERROR / LOADING / EMPTY | **PARTIAL** (components exist; polish A/F) |

† README: preview APK without `google-services.json` disables push/mic.

---

## Voice

* `POST /api/v1/portal/audio` → Whisper → same N1 portal messages path (`mobile/BACKEND_CAPABILITIES.md`)  
* Integrated as **input modality**, not a separate bot  
* Differences vs text: STT errors, no rich media in; same authority/CASI downstream  
* Classification: **READY** with channel-quality PARTIAL (STT)

---

## Multi-Account

| Surface | Multi-account |
|---|---|
| WA phone → N BillTrack | **YES** disambiguation (F1) |
| request_account_selection / service selection | **YES** |
| Billing reads | **PARTIAL** — needs selected CN |
| Connectivity diagnostics | **YES** — requires selected_service_ref |
| Tickets | **PARTIAL** — ownership by abonado; ambiguity handled on note |
| Context SoT | **YES** — selected_service_ref (2.5) |

Assumptions of single account remain in some Legacy phrase paths — **E** technical debt, not always blocker.

---

## Sensa

| Aspect | Class |
|---|---|
| N1 intent `tv_sensa` playbooks | **PARTIAL** / triage |
| BCM/PPPoE probes | **UNAVAILABLE** (not diagnosticable type) |
| App dedicated Sensa module | **MISSING** / via chat |
| Support actions / account reset | **HANDOFF** N2 |
| Adapters | KB + flujos; no Sensa BSS WRITE |

**READY** for conversational triage; **HANDOFF** for account/platform issues.

---

## VoIP

| Aspect | Class |
|---|---|
| Intent telefonía / líneas | **PARTIAL** (N1 flows) |
| SIP/Asterisk self-service | **UNAVAILABLE** in Eko |
| Diagnóstico técnico Runtime | **UNAVAILABLE** (non-diagnosticable) |
| Human ops / backend telephony | **HANDOFF** |

Eko can **read/triage** conversationally; cannot operate softswitch.

---

## Web / Portal

| Feature | App | N1 chat | Portal web abonado | Consola ibot |
|---|---|---|---|---|
| Chat Eko | YES | YES | YES | view |
| Billing cards | YES | YES | PARTIAL | — |
| Tickets list/create | YES | YES | YES | admin |
| Connectivity card | YES | YES | PARTIAL | — |
| Push | YES† | n/a | n/a | — |
| Voice | YES† | n/a | limited | — |
| Agent tools | — | — | — | YES |

Differences: **INTENTIONAL** (console vs abonado); **GAP** if portal lacks cards app has; **LEGACY** some web-only paths.

---

## Customer Context

2.5 = **CLOSED/FROZEN** — not modified.

Available: selected_service_ref, domain_stack, handoff continuity, eko_action STATE, journey STATE.  
Consumed by diagnostics, billing selection, tickets, handoff.  
**FUTURE GAP** only if a new customer capability needs more continuity — do not reopen 2.5 without blocker.

---

## Security / Authority

* LLM ≠ authority: **PASS** (CASI 2.6)  
* Ownership tickets/abonado: **PASS** on closed paths  
* BillTrack SELECT-only: **PASS**  
* OV allowlist: **PASS**  
* Multi-account disambiguation: **PASS** with residual Legacy sites  
* PII: logs eko_action avoid MSISDN/DNI in Runtime stamps  

---

## Operability

| Signal | State |
|---|---|
| `/health` `/ready` | READY |
| `action_runtime.*` boot log (2.6Q) | READY |
| `eko_action` path=runtime | READY (create smoke) |
| TicketEvent audit | READY |
| Push claim/dedup | READY (2.3) |
| Legacy create path tagging | WEAKER — known limitation |
| Journey metrics API | READY (admin) |

Gaps affecting ops: Legacy create observability (**B**); widening ACTIONS without boot verify (**B**).

---

## Product Maturity Matrix

| Dominio | READY | PARTIAL | MISSING | EXTERNAL | PRIORITY SIGNAL |
|---|---:|---:|---:|---:|---|
| Billing READ | alto | due/PDF/historial | cuenta corriente | OV pay | customer-facing gap |
| Services READ | alto | admin fields | — | — | — |
| Commercial EFFECTS | — | — | — | BSS/CRM | external dependency |
| Connectivity fixed Internet | alto | BCM/UISP XOR | — | Radius/BCM/UISP | technical debt |
| Installation | honest unavail | — | EFFECT | BSS | external dependency |
| Tickets SS | create/show/note | history UX | close/resolve SS | — | product decision / nice-to-have |
| Escalate | composition | Action unused | — | — | intentional |
| Proactive outage/ticket | alto | — | billing/conn events | — | customer-facing gap |
| Mobile | alto | preview FCM/voz | Play polish | Expo/FCM | operational / nice-to-have |
| Voice | alto | STT quality | — | Whisper | nice-to-have |
| Multi-account | medio-alto | some Legacy | — | BillTrack | technical debt |
| Sensa | triage | — | platform actions | Sensa/BSS | external / handoff |
| VoIP | triage | — | SIP ops | Asterisk | external / handoff |
| Web parity | medio | cards | — | — | nice-to-have / intentional |
| Context 2.5 | frozen | — | — | — | do not reopen |
| Observability | Runtime strong | Legacy weak | — | — | operational gap |

---

## Gap Classification

### A — CUSTOMER VALUE GAP
* Invoice due date / richer invoice / payment history in-chat  
* Proactive billing reminders (needs SoT)  
* Prod enablement of `ticket_customer_note` in ACTIONS CSV (ops)  
* Clearer multi-service “sin internet” guided path  

### B — OPERATIONAL GAP
* Legacy create path observability  
* Residual Legacy creates outside XOR (measure/harden later)  
* Preview APK without FCM complicates field push QA  

### C — EXTERNAL DEPENDENCY
* Payment execution; commercial catalog WRITE; installation EFFECT  
* Sensa account platform; Asterisk/SIP administration  
* BillTrack field limits for invoice detail  

### D — PRODUCT DECISION
* Whether customer should close/resolve tickets in-app  
* Whether escalate_human Action should ever be activated  
* Whether to widen prod ACTIONS beyond create_ticket  
* Managed commercial communications (2.4*)  

### E — TECHNICAL DEBT
* BCM/UISP PARTIAL Legacy hot path  
* diag IA `_crear_ticket_n2` direct  
* Some single-account assumptions in Legacy phrases  

### F — NICE TO HAVE
* Portal/app visual parity polish  
* Voice UX refinements  
* Empty/error state copy  

---

## Next Milestone Candidates

*(Comparable options — **no ranking**.)*

| Candidate | Problem | User | Surface | Deps | Now | Class | Evidence | Risk | Needs prod? | Needs external? |
|---|---|---|---|---|---|---|---|---|---|---|
| **Proactive ISP expansion** | Only outage/ticket notify | Abonado | Push/Home | Detectors SoT | Partial | A/C | 2.3H | Med | Yes smoke | Maybe BillTrack fields |
| **Self-Service Billing depth** | Thin invoice/pay history | Abonado | N1/App | BillTrack/OV | Partial | A/C | 2.6H | Med | Verifies | BillTrack schema |
| **Incident Experience** | Ticket journey UX beyond create/note | Abonado | App/N1 | Estate | Partial | A/D | 2.6T | Low-Med | Optional | No |
| **Mobile parity / store readiness** | Preview limits; Play | Abonado | Mobile | FCM/EAS | Partial | B/F | README | Med | Field devices | Google/Apple |
| **Connectivity experience polish** | Multi-service “sin internet” clarity | Abonado | N1 | 2.5 SoT | Partial | A/E | 2.2C/2.6 | Med | Optional | Probe systems |
| **Commercial handoff clarity** | Honest OV/BSS paths | Abonado | N1/OV | 2.2E/2.4 | Handoff | C/D | 2.4* | Low | No | BSS |

---

## Proposed 2.7 Scope Options

Factually, 2.7 should be defined as **one** of:

1. **Proactive ISP** — expand DETECT→NOTIFY only where authoritative SoT exists (avoid fake billing events).  
2. **Self-Service Expansion** — deepen Billing READ + OV handoff UX without payment WRITE.  
3. **Customer Experience / Incident** — ticket timeline, note in prod CSV, guided connectivity narrative.  
4. **Mobile** — production push/voice builds + store path.  

**Not** 2.7: reopening update_ticket/escalate Action activation; BSS commercial WRITE; 2.5 continuity rewrite.

Decision input = gap classes A vs C volume and cooperative priority — **out of this audit**.

---

## Known Limitations

* Prod ACTIONS = `create_ticket` only (intentional isolation post-2.6P)  
* 9 Legacy create sites outside XOR  
* diag IA Legacy create  
* BCM/UISP PARTIAL  
* No remote staging  
* BillTrack invoice FC limits  
* Preview APK may lack FCM/mic  
* installation_status honest unavailable  

None reopen 2.6 CLOSED.

---

## Conclusion

Eko is **production-capable self-service** for the closed 2.6 set (especially **create_ticket** Runtime + diagnostics/billing READ + proactive outage/ticket). Gaps that justify a milestone are primarily **customer value depth** (billing/proactive/incident UX) and **external dependencies** (BSS), not unfinished Agentic Ops scaffolding.

```text
Production touched: NO
Configuration changed: NO
Runtime activated: NO
ACTION_RUNTIME_ACTIONS changed: NO
Tickets created: 0
Tickets modified: 0
Database changed: NO
Mobile changed: NO
Backend changed: NO
2.5 modified: NO
2.6 modified: NO
```
