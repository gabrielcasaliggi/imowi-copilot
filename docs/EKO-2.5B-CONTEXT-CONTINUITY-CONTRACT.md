# EKO 2.5B — CONTEXT CONTINUITY CONTRACT

**Status:** DESIGN / DOCUMENTATION ONLY — NOT IMPLEMENTED  
**Phase:** Canonical continuity contract  
**Depends on:** [EKO 2.5A — Continuity Discovery](./EKO-2.5A-CONVERSATIONAL-QUALITY-CONTEXT-CONTINUITY-DISCOVERY.md)  
**CASI:** intact — `LLM content ≠ authority` · `Proposal ≠ state transition`  
**Runtime impact:** NONE

> Este documento **define** el contrato. **No** implementa resolvers, flags ni migraciones.  
> Gaps F-01…F-03 de 2.5A quedan **especificados** aquí; el hardening es 2.5D/E.

---

## 1. Purpose

Definir el **contrato canónico de continuidad conversacional** de Eko:

| # | Contract answers |
|---|---|
| 1 | Qué contexto es canónico |
| 2 | Qué es derivado / shadow / legacy |
| 3 | Qué persiste entre turnos |
| 4 | Scope: domain / service / action |
| 5 | Eventos de invalidación |
| 6 | Reference resolution (≠ intent ≠ ownership) |
| 7 | Resume de dominio anterior (`domain_stack`) |
| 8 | Cómo evitar divergencia entre representaciones |
| 9 | Integración con CASI / multi-account / Sensa sin login |

**Principio:**

```text
CONTEXT ≠ MEMORY
STRUCTURED CONTEXT > NATURAL LANGUAGE RECONSTRUCTION
Ambiguity > guessing
```

No construir memoria semántica libre. Conservar **estado estructurado, confiable y acotado**.

---

## 2. Context layers (canonical model)

### A. IDENTITY / OWNERSHIP CONTEXT

| | |
|---|---|
| **Source** | `TrustedContext` (rebuild per Runtime call) + abonado / BillTrack CN |
| **Includes** | client_number, ownership binding, account when disambiguated |
| **Authority** | **TRUSTED** — never LLM |
| **Freshness** | session-long (while conversation + identity hold) |
| **Persist** | Identity keys may live in ctx; TrustedContext object is **not** serialized as authority blob |

### B. SERVICE CONTEXT

| | |
|---|---|
| **Canonical field** | `eko_journey.selected_service_ref` (`ServiceRef`) |
| **Meaning** | Currently selected customer service (catalog-validated) |
| **Authority** | Catalog + ownership check — LLM may **propose** only |
| **Freshness** | conversation/session while valid (survives domain switch) |
| **Sensa / no login** | Valid selection with `login=""` — **required** |

### C. DOMAIN CONTEXT

| | |
|---|---|
| **Canonical (CS)** | `cs.active_domain_id`, `cs.domains[]`, `cs.domain_stack` |
| **Compat journey** | `eko_journey.domain` / `name` / `intent` |
| **Legacy** | `ctx.intencion` (playbook) |
| **Kinds today** | `tecnico` · `administrativo` · `comercial` (`ConversationState`) |
| **Journey domains** | `internet` / `billing` / … (orchestration layer — map, do not conflate blindly) |

### D. CONVERSATIONAL CONTEXT

Non-authority helpers for next-turn interpretation:

| Examples | Authority? |
|---|---|
| `last_bot_act`, pending referent, last selection label | Conversational / derived |
| `comprension_turno` | Turn-only heuristic |
| Message history | Discourse only |

Must **not** override TrustedContext / ServiceRef / confirmation.

### E. ACTION CONTEXT

| | |
|---|---|
| **Canonical** | `eko_action` (`action`, `status`, confirmation) |
| **Journey flags** | `pending_confirmation`, `next_required_input`, `selection_options` |
| **Freshness** | action-long — invalidate on domain switch / selection change / reject |
| **Confirmation** | Explicit user + pending bind — never LLM |

---

## 3. CONTEXT ≠ MEMORY

| Allowed | Forbidden |
|---|---|
| Persist structured refs, domains, pending, facts | Free-form “remember everything” embeddings as SoT |
| Use history for wording / weak cues | Rebuild `selected_service_ref` from chat when still valid |
| Ask again if invalidated / ambiguous / ownership fail | Re-ask “¿qué servicio?” when valid `selected_service_ref` exists |

**Exception to re-ask:** invalidation, real ambiguity, conflict, missing required data, ownership unverifiable.

---

## 4. Canonical vs shadow vs legacy matrix

| Información | Rol contract | Writer (hoy) | Reader (hoy) | Futuro |
|---|---|---|---|---|
| `selected_service_ref` | **CANONICAL** | `apply_service_ref` | `get_selected_ref`, Runtime | Keep SoT |
| `selected_service` | **SHADOW / projection** (login\|service_id) | `apply_service_ref` | journeys compat | Projection only |
| `login_seleccionado` | **LEGACY / projection** | apply_service_ref / legacy | Runtime fallback | Compat; never invent login |
| `contexto_json` | **CANONICAL persistence envelope** | `set_contexto` | `get_contexto` | Keep |
| `cs` (`ConversationState`) | **CANONICAL** domain/facts/pending (shadow dual-write) | `write_shadow_into_ctx` | Motor / hydrate | Align readers |
| `eko_journey` | **CANONICAL** journey/selection container | `set_journey` | journeys | Keep |
| `hechos` | **LEGACY** (WiFi/tech facts still live) | flujos / comprensión | playbooks T70 | Prefer cs.facts long-term |
| `pasos_cubiertos` | **LEGACY projection** | playbooks | hydrate once | cs.covered_steps canonical |
| `paso_idx` | **TEMPORARY** cursor | playbooks | playbooks | Must not erase facts |
| `domain` (journey) | **CANONICAL journey-domain** | journeys | journeys | Map ↔ cs.kind |
| `intencion` | **LEGACY** | playbooks | Legacy N1 | Deprecate candidate |
| `pending` (cs) | **CANONICAL** conversational pending | Motor stamps | Motor | Keep |
| `eko_action` / `confirmation_pending` | **CANONICAL** action | Runtime / journeys | confirm path | Keep |
| `diagnostic_started` / `last_diagnostic_result` | **DERIVED** service-scoped | journeys | journeys | Invalidate on service change |
| `pppoe_*` / TSS | **DERIVED** service-scoped | probes | diag / CONTEXTO | Invalidate on service change |
| `selection_options` | **TEMPORARY** action | needs_input | resolver | Clear on select |
| `next_required_input` | **TEMPORARY** action | journeys | journeys | Clear on fulfill |
| `comprension_turno` | **TEMPORARY** turn | comprensión | limited | Overwrite each turn |
| Message history | **CONVERSATIONAL** | add_mensaje | LLM / heuristics | Never SoT |

Labels: CANONICAL · SHADOW · LEGACY · DERIVED · TEMPORARY · REMOVE_LATER (candidate only — **not** removed in 2.5B).

---

## 5. Single source of truth — service selection

```text
CANONICAL:  selected_service_ref  (ServiceRef dict in eko_journey)
    ↓ projection
SHADOW:     selected_service      (login if present else service_id)
    ↓ projection (only if login non-empty)
LEGACY:     login_seleccionado    (MUST pop when login empty — Sensa)
```

| Rule |
|---|
| All reads for authority SHOULD prefer `get_selected_ref(ctx)` |
| Dual-read fallback to login strings is **compatibility**, not alternate SoT |
| Divergence (ref vs login) = defect; log / heal toward `selected_service_ref` (future 2.5D) |
| `login is None/""` ≠ “no selection” |
| **COMMERCIAL SERVICE SELECTION** ≠ **TECHNICAL LOGIN SELECTION** |

---

## 6. ServiceRef contract

Existing dataclass (`eko_service_selection.ServiceRef`) — **no new fields required** for 2.5B.

| Field | Role |
|---|---|
| `service_id` | **Identity** (primary when present) |
| `login` | Technical identity (optional) |
| `client_number` | **Ownership** binding |
| `service_type` | Capability / routing (`internet`, `tv`, `telefonia`, …) |
| `label` / `product` | **Presentation** |
| `active` | Commercial/active flag from catalog (≠ technical up) |

| Proposed / NOT IMPLEMENTED |
|---|
| `selection_source` (`user`\|`auto_single`\|`ordinal`\|…) — optional audit aid |
| `selected_at_turn` — optional freshness aid |

Do not invent fields without a later gate.

---

## 7. Invalidation contract

| Event | Conserva | Invalida |
|---|---|---|
| **A. Service change** (`selection_changed`) | Ownership, client_number, conversation, **new** `selected_service_ref`, domain (unless also switched) | Prior diagnostic, `last_diagnostic_result`, `pppoe_*`/TSS, service-scoped pending, journey `pending_confirmation` tied to old service |
| **B. Domain switch** (kind / journey) | Ownership, **`selected_service_ref`** (default), general conversation | Action confirmation stale (`_clear_stale_confirmation`), domain-local pending, journey-local steps of **previous** journey; **not** automatic wipe of selection |
| **C. Journey change** | Global identity + selection (unless service also changes) | Previous journey step/name; confirmation; domain-local journey flags; may set `previous_journey` |
| **D. Handoff (agent)** | ctx JSON while hilo open; selection/domain usually | Bot orchestration paused; on **new** conv after close → **all** ctx reset (intentional) |
| **E. Confirmation stale** | Selection, domain | `confirmation_pending` when: domain/journey switch, selection change, action reject, payload fingerprint mismatch |
| **F. Error / timeout (action)** | Selection, domain, ownership | Action result may be UNKNOWN; pending may remain or clear per action policy — **never** invent success; do not wipe selection by default |
| **G. Outage intercept** | Selection typically | Outage-scoped keys via `_limpiar_ctx_outage` |
| **H. Explicit “sí” without pending** | All | No transition (no false confirm) |

**Confirmation remains valid only if:** same action + same pending bind + ownership unchanged + selection unchanged (when action service-scoped) + no domain/journey clear.

---

## 8. Domain continuity & domain_stack

### 8.1 Current fact (2.5A)

`ConversationState.domain_stack` **already exists** (`MAX_STACK = 3`) with `push_domain_stack` / `pause_domain` / `resume_domain`. Journey layer has **narrow** resume cues (`_is_resume_connectivity`). Generic “volviendo a lo anterior” is **not** wired end-to-end (F-03).

### 8.2 Contract (target semantics — NOT IMPLEMENTED as product behavior)

| Aspect | Contract |
|---|---|
| **Represents** | Ordered list of paused/prior **domain slot ids** (kind slots), not free text topics |
| **Push** | When pausing current to activate another kind |
| **Pop / resume** | Explicit user resume **or** matching kind signal → `resume_domain` |
| **Replace** | Same kind reactivates existing slot (if not closed) |
| **Remove** | Closed slots; trim to `MAX_STACK` |
| **Max depth** | **3** (existing constant — keep bounded) |
| **Cycles** | Re-push moves id to front; no infinite history |
| **With current** | `active_domain_id` is current; stack holds others |
| **With service** | Resume domain **does not** clear `selected_service_ref` by default |

### 8.3 Domain ↔ service relationship

```text
selected_service_ref MAY survive domain change.
Example: ref=internet + domain=billing → later domain=connectivity
         → same internet selection remains valid.

Service change MUST invalidate service-scoped technical context
(diagnostic, PPPoE/TSS, service-bound pending).
```

---

## 9. Reference resolution contract

### 9.1 Separation of concerns

| Pipeline | Responsibility |
|---|---|
| **INTENT DETECTION** | What the user wants to do (journey/playbook/domain signal) |
| **REFERENCE RESOLUTION** | What entity (service/domain) a phrase points to |
| **SERVICE SELECTION** | Bind resolved candidate → `ServiceRef` via catalog |
| **OWNERSHIP AUTHORIZATION** | TrustedContext / CN / catalog membership |

```text
USER TEXT
  → REFERENCE CANDIDATE(S)     (deterministic + optional LLM proposal)
  → CONTEXT RESOLUTION         (options, last ref, domain_stack)
  → CATALOG MATCH              (eko_service_selection)
  → OWNERSHIP VALIDATION       (client_number / TrustedContext)
  → ServiceRef | NEEDS_INPUT | DENIED
  → Conversation Motor / State
```

LLM may propose candidates. **Must not** authorize selection or mutate state.

### 9.2 Outcomes

| Outcome | When |
|---|---|
| `selected` | Exactly one safe catalog match + ownership OK |
| `needs_input` | 0 useful signal, or **≥2** valid candidates, or relative ref unsafe |
| `denied` | Explicit id/login not in catalog / ownership fail |
| `no_match` / `unavailable` | Empty catalog / source down |

**Ambiguity > guessing.** Never auto-pick among ≥2 valid candidates.

### 9.3 Natural references (target behavior — NOT IMPLEMENTED where marked)

| Phrase | Deterministic? | Needs | 1 match | ≥2 matches | 0 match |
|---|---|---|---|---|---|
| **A. "el fijo"** | **Yes (target)** — treat as telefonia synonym of `fija` / fijo; if also used for “internet fijo”, require type disambiguation when both internet+telefonia present | Catalog types | select | NEEDS_INPUT | NEEDS_INPUT / list |
| **B. "la fija"** | Yes (today) | Catalog | select | NEEDS_INPUT | NEEDS_INPUT |
| **C. "el internet"** | Yes (today) | type internet | select | NEEDS_INPUT | NEEDS_INPUT |
| **D. "la fibra"** | Yes (today-ish) | internet/fibra | select | NEEDS_INPUT | NEEDS_INPUT |
| **E/F. "ese"/"esa"** | Yes if **single** catalog row **or** single pending option | options/catalog | select | NEEDS_INPUT | NEEDS_INPUT |
| **G/H. "el otro"/"la otra"** | **Relative** — see §10 | last ref + candidates | select if unique alternate | NEEDS_INPUT | NEEDS_INPUT |
| **I. "ese servicio"** | Same as ese | | | | |
| **J. "el anterior"** | Prefer prior `selected_service_ref` before last change if stored; else NEEDS_INPUT | selection history (future bounded) | | | |
| **K. "lo mismo"** | Conversational — usually keep current selection + prior intent; not a service switch | current ref | keep | — | NEEDS_INPUT if no current |
| **L. "volviendo a lo anterior"** | **CONTEXT RESUME** via domain_stack / previous_journey — §11 | stack | resume | NEEDS_INPUT if empty/ambiguous | NEEDS_INPUT |

**F-01 contract fix (future 2.5E):** include morphological/synonym map `fijo` ↔ `fija` ↔ telefonia; when “fijo” could mean fixed broadband **or** phone and both exist → **NEEDS_INPUT** with labeled options (do not guess).

---

## 10. Relative service reference — "el otro"

**Concept:** `RELATIVE SERVICE REFERENCE`

| Input | Rule |
|---|---|
| **Candidate set** | Current catalog rows (or last `selection_options` if still open) |
| **Exclusion** | Exclude current `selected_service_ref` (by service_id, else login) |
| **Recency** | If exclusion leaves **exactly one** remaining in a **2-item** set → that one |
| **Ambiguity** | If ≥2 remain after exclusion → **NEEDS_INPUT** (list them) |
| **No current selection** | **NEEDS_INPUT** (cannot resolve “otro”) |
| **Fallback** | Never invent; never pick “most popular” |

Example: Internet + Fija + Sensa, current=Fija, “el otro” → **NEEDS_INPUT** (Internet vs Sensa).  
Example: Internet + Fija, current=Fija, “el otro” → Internet (**safe**).

---

## 11. Context resume — "volviendo a lo anterior"

| | |
|---|---|
| **Mechanism** | Prefer `cs.domain_stack` top + paused slot state; journey may expose `previous_journey` |
| **Restores** | Previous **domain** (kind/slot), relevant domain facts/covered steps; **selection** unchanged unless resume implies service |
| **Does not restore** | Expired action confirmation; discarded journeys’ mutating pending |
| **Insufficient context** | Empty stack / closed slot / ambiguous “anterior” → **NEEDS_INPUT** (“¿volves a internet, a facturación o a …?”) |
| **Not** | Full message-history replay as memory |

Narrow cues like `_is_resume_connectivity` remain valid specializations under this contract.

---

## 12. Explicit service switch vs reference to current

| User signal | Class | Behavior |
|---|---|---|
| “Ahora hablame del fijo” / “pasame al internet” | **EXPLICIT SERVICE SWITCH** | Run reference resolution → may replace `selected_service_ref` → invalidate service-scoped tech |
| “¿Y ese cuánto cuesta?” / “lo mismo” | **REFERENCE TO CURRENT** | Keep selection; route intent (e.g. billing) without clearing ref |
| LLM proposes different service while no switch language | **Conflict** | Structured current selection **wins** unless EXPLICIT SWITCH validated via catalog |

Ownership always re-checked on switch.

---

## 13. Playbook contract

```text
BEFORE asking the user:
  1. TrustedContext / identity
  2. selected_service_ref
  3. Domain / journey context
  4. Action / pending
  5. Valid hechos / cs.facts
  6. Ask only for what is missing, stale, or ambiguous
```

| Data state | Playbook |
|---|---|
| Valid structured | **Do not re-ask** |
| Stale / invalidated | Re-ask |
| Ambiguous | Clarify (NEEDS_INPUT) |

`paso_idx` is a **cursor**, never a license to drop known facts (T70).

---

## 14. State vs history

| From STRUCTURED STATE | From MESSAGE HISTORY |
|---|---|
| Ownership, ServiceRef, domain, pending, confirmation, diagnostic flags, action state | Wording, discourse, weak anaphora cues |
| Catalog-validated selection | Never overwrite ServiceRef |

History must **not** override trusted structured state.

---

## 15. LLM contract (continuity)

| PERMITIDO | NO PERMITIDO |
|---|---|
| Detect intent | Change ownership |
| Propose reference / domain | Authorize `selected_service_ref` |
| Interpret language | Assert service belongs to customer without catalog |
| Generate wording / summarize for UX | Confirm actions |
| | Mutate state without Motor |
| | Invalidate structured context unilaterally |
| | Resolve ambiguity as “safe enough” alone |

```text
LLM → Proposal → Resolver/Catalog → Ownership → Policy → Motor → State
```

---

## 16. CASI integration

Unchanged architecture:

```text
ActionProposal → Policy → Conversation Motor → Runtime
TrustedContext = ownership authority
LLM content ≠ authority
Proposal ≠ state transition
```

Reference resolution is **not** a parallel mutation path: it feeds Motor/Runtime the same way as today (`apply_service_ref` only after catalog+ownership).

---

## 17. Context priority (validated vs proposal)

**Proposal from brief (validated):**

1. TrustedContext  
2. Canonical structured state (`selected_service_ref`, `eko_action`, `cs` domains)  
3. Current validated selection  
4. Domain / action state  
5. Recent conversation history  
6. LLM interpretation  
7. Heuristic fallback (`comprension_turno`)

**As-is code nuance (2.5A):** Legacy N1 may still weight `intencion` / playbook and historial heavily when journeys miss; Runtime path already matches 1–4 for EFFECTS. Contract **targets** the hierarchy above for all continuity-sensitive decisions; closing the Legacy gap is **2.5D**, not a silent rewrite of priority.

---

## 18. Context freshness

| Class | Examples | Lifetime |
|---|---|---|
| **session-long** | ownership / client_number (while hilo + identity) | Until logout / new conv / identity change |
| **conversation-long** | `selected_service_ref` while valid | Until switch / wipe / new conv |
| **domain-long** | domain facts, covered steps | While domain slot active/paused |
| **journey-long** | journey name/step | Until journey switch/end |
| **action-long** | confirmation, selection_options | Until complete/clear/stale |
| **turn-only** | LLM proposal, comprension_turno | Next turn overwrite |

No TTL engine in this phase.

---

## 19. Multi-account (unchanged guarantees)

- phone ≠ account ownership  
- DNI alone ≠ authorization under multi-account  
- `selected_service_ref` must validate against catalog + CN  
- Contextual reference **cannot** bypass TrustedContext  
- Account ambiguity → **NEEDS_INPUT**  
- No silent account auto-select  

---

## 20. Sensa / services without login

| Rule |
|---|
| Sensa (and similar) MAY be a full `selected_service_ref` |
| Do **not** require `login` for selection validity |
| Do **not** fabricate login |
| Technical diagnostics that need login → `unavailable` / handoff honestly, without clearing commercial selection unless user switches |

---

## 21. Compatibility (no removal)

| Field | Stance |
|---|---|
| `login_seleccionado` | compatibility-only projection |
| `selected_service` | shadow projection |
| `cs` | canonical shadow dual-write |
| `contexto_json` | canonical envelope |
| `hechos` / `pasos_cubiertos` / `intencion` | legacy live; deprecate **candidates** only after 2.5D dual-read audit |

No migrations. No deletes.

---

## 22. Conflict resolution summary

| Situation | Winner |
|---|---|
| Valid ServiceRef + vague “ese” | Current ServiceRef if unique context; else NEEDS_INPUT |
| Valid ServiceRef + explicit switch phrase | New catalog-validated ref |
| LLM disagrees without switch | Structured state |
| Confirmation pending + domain switch | Confirmation invalidated |
| Two catalog matches | NEEDS_INPUT |

---

## 23. Future implementation sequence

| Phase | Goal |
|---|---|
| **2.5C** | Conversational Regression Matrix — measurable cases for F-01…F-03, A–H, multi-account, Sensa |
| **2.5D** | Context Continuity Hardening — single-read path, invalidation enforcement, playbook “ask only if missing”, domain resume wiring |
| **2.5E** | Reference Resolution Hardening — fijo/fija, el otro, resume phrases |

Division is justified: **specify (2.5B) → measure (2.5C) → harden state (2.5D) → harden language (2.5E)**.

**Do not implement 2.5C/D/E in this phase.**

---

## 24. Explicit non-goals (2.5B)

- No code, prompts, playbooks, CASI, Runtime, Policy changes  
- No Redis / embeddings / free memory  
- No schema migrations  
- No EFFECTS / notifications / external calls  

---

## 25. Validation (this phase)

| Check | Result |
|---|---|
| Static alignment with 2.5A + `ServiceRef` / `domain_stack` / journeys | Done |
| `pytest tests/test_eko_conversational_hardening_6.py tests/test_domain_lifecycle.py tests/test_conversation_motor.py` | PASS (baseline; no new tests) |
| Code / DB / API modified | **NONE** |

---

## 26. Closure checklist

- [x] Canonical context layers defined  
- [x] `selected_service_ref` = canonical selection  
- [x] Projections / shadow / legacy matrix  
- [x] Invalidation matrix  
- [x] Domain continuity + domain_stack contract  
- [x] Reference resolution ≠ intent  
- [x] “el fijo” / “el otro” / “volviendo a lo anterior” specified  
- [x] Ambiguity → NEEDS_INPUT  
- [x] State vs history + LLM boundary  
- [x] CASI + multi-account + Sensa without login  
- [x] Freshness + conflicts  
- [x] No code / migrations / effects  
- [x] Future 2.5C–E documented  

**STATUS: PASS**
