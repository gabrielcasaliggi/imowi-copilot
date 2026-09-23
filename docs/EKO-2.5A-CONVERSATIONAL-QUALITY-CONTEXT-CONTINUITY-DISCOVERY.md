# EKO 2.5A — CONVERSATIONAL QUALITY & CONTEXT CONTINUITY DISCOVERY

**Status:** PASS WITH FINDING  
**Phase:** DISCOVERY / READ-ONLY — no runtime, DB, API, prompt, or behavior changes  
**CASI:** intact — LLM content ≠ authority  
**Depends on:** ConversationState, Conversation Motor, eko_journeys, eko_service_selection, TrustedContext, Proactive 2.3 (untouched)

Principio de la fase: *¿Eko conserva y utiliza correctamente el contexto confiable entre turnos?*

---

## 1. Executive summary

El modelo real de continuidad es **híbrido**:

1. **Persistencia:** `ConversacionCanal.contexto_json` (dict `ctx`) + historial de mensajes en Estate.  
2. **Estado estructurado canónico (parcial):** `ctx["eko_journey"]` (journeys/selección) + `ctx["cs"]` (ConversationState shadow) + claves legacy (`login_seleccionado`, `intencion`, `hechos`, `pasos_cubiertos`, `eko_action`).  
3. **Autoridad de selección de servicio:** `selected_service_ref` vía `eko_service_selection` (LLM solo propone; aceptación solo contra catálogo).  
4. **Autoridad de acciones:** Policy + Runtime + TrustedContext; confirmación explícita (`confirmation_pending`), no LLM.  
5. **LLM:** recibe `CONTEXTO_ABONADO` (facts) + reglas + historial de mensajes; **no** es SoT de selección/ownership/dominio.

**Hallazgos confirmados (principales):**

| ID | Severidad | Hallazgo |
|---|---|---|
| F-01 | HIGH | `"el fijo"` **no** resuelve a telefonía en `resolve_service_selection` (sí `"la fija"` / `"teléfono"`) |
| F-02 | MEDIUM | `"el otro"` / corrección anafórica no tiene resolución determinística de servicio |
| F-03 | MEDIUM | No hay recuperación genérica de “volviendo a lo anterior” — solo cues puntuales (`_is_resume_connectivity`) |
| F-04 | INFO | Tres capas de estado (legacy ctx / eko_journey / cs shadow) aumentan riesgo de divergencia; dual-write existe |

**Comportamientos correctos confirmados:**

- Multi-servicio + `"ese"` → `needs_input` (no auto-elige)  
- Cambio de selección invalida diagnóstico / TSS / confirmación stale  
- Confirmación de ticket solo con pending + sí trusted  
- Hechos WiFi `dispositivo_sin_ethernet` bloquean paso de cable (T70)  
- Domain switch journey limpia confirmaciones stale (C10)

---

## 2. Current conversation architecture

```text
Canal (WA/TG/web/app)
  → procesar_mensaje_entrante (canal_abonado.py)
      → persist mensaje IN + get_contexto / set_contexto
      → increment_user_turn (cs.turn)
      → preparar_turno_comprension (heurística; no autoridad)
      → auth / abonado
      → runtime confirmation pending (sí/no)
      → maybe_handle_journey_turn (eko_journeys)  [flag]
           → detect journey / domain switch
           → selection / diagnostic / billing / …
           → dispatch_runtime → ActionResult
      → Legacy N1 (playbooks + motor + LLM diagnóstico)
      → respuesta + set_contexto
```

| Capa | Rol |
|---|---|
| `ConversationState` (`ctx["cs"]`) | Dominios, facts tipados, pending bot/user, covered_steps canónico |
| `eko_journey` | Journey name/step, selection, confirmation flags journey-level |
| Legacy `ctx` | `intencion`, `login_seleccionado`, `hechos`, `pasos_cubiertos`, playbook cursor |
| `eko_action` | Action Runtime confirmation_pending |
| Mensajes DB | Historial textual |
| TrustedContext | Ownership / client_number en Runtime (no se persiste como objeto; se reconstruye) |

---

## 3. Real context flow

```text
USER MESSAGE
    ↓
INGEST          add_mensaje + get_contexto
    ↓
INTERPRETATION  comprension_abonado (enriquece; no decide ownership)
    ↓
CONTEXT LOAD    ctx + hydrate_conversation_state + get_journey
    ↓
PROPOSAL/INTENT detect_journey_name / clasificar_intencion / LLM proposal (allowlist)
    ↓
POLICY          evaluate / capability gates / confirmation
    ↓
MOTOR           conversation_motor + domain_lifecycle (slots/pending)
    ↓
STATE UPDATE    apply_service_ref / set_journey / hechos / cs write_shadow
    ↓
RUNTIME/PLAYBOOK dispatch_runtime OR playbook paso
    ↓
RESPONSE        user_message determinístico o LLM wording
    ↓
PERSISTENCE     set_contexto (JSON) + mensaje OUT
    ↓
NEXT TURN       reload contexto_json
```

| Stage | Entra | Sale | Quién modifica | Riesgo pérdida |
|---|---|---|---|---|
| Ingest | texto | msg + ctx | canal_repo | Bajo |
| Comprensión | texto, hist | texto_para_reglas, comprension_turno | comprension_abonado | Bajo (aditivo) |
| Journey | ctx, texto | JourneyTurn / None | eko_journeys | Medio si switch limpia de más |
| Selection | catalog + texto | selected_service_ref | eko_service_selection + apply_service_ref | Alto si refs fallan |
| Runtime | TrustedContext + ctx | ActionResult + eko_action | eko_action_runtime | Bajo (gates) |
| Persist | ctx | JSON | set_contexto + write_shadow | Medio si shadow mismatch |

**Authoritative for selection:** `selected_service_ref` (catalog-bound).  
**Authoritative for identity:** TrustedContext / abonado / BillTrack CN.  
**Not authoritative:** LLM proposal params, free text alone, phone/DNI under ambiguity.

---

## 4. Context inventory (evidence-based)

| Campo | Ubicación | Tipo | Scope | Persistencia | Quién escribe | Quién limpia | Quién consume | Riesgo |
|---|---|---|---|---|---|---|---|---|
| `selected_service_ref` | `eko_journey` | A TRUSTED | SERVICE | Yes (ctx JSON) | `apply_service_ref` | Cambio selección / no explicit wipe-all | Runtime, journeys | Dual-read con login |
| `selected_service` | `eko_journey` | I LEGACY | SERVICE | Yes | `apply_service_ref` (compat = login\|id) | Al cambiar | Journeys | Shadow de ref |
| `selection_options` | `eko_journey` | D TEMP | ACTION | Yes | Selection needs_input | Al seleccionar | resolve_service_selection | Stale options |
| `next_required_input` | `eko_journey` | D TEMP | ACTION | Yes | Journeys | Al completar | Journeys | — |
| `login_seleccionado` | `ctx` | I LEGACY | SERVICE | Yes | apply_service_ref / legacy | pop si servicio sin login (Sensa) | Runtime fallback | Divergencia |
| `eko_journey.*` | `ctx` | A/C | DOMAIN | Yes | set_journey | Domain switch parcial | maybe_handle_journey_turn | — |
| `eko_action` | `ctx` | A ACTION | ACTION | Yes | set_action_state | clear on switch / reject | Runtime confirm | Stale confirm |
| `confirmation_pending` | eko_action / journey | A | ACTION | Yes | Runtime / journeys | `_clear_stale_confirmation` | `_talvez_runtime_confirmation_pending` | — |
| `diagnostic_started` / `last_diagnostic_result` | journey | E DOMAIN | SERVICE | Yes | journeys | selection_changed | journeys | Correct invalidation |
| `pppoe_*` / TSS keys | ctx | C DERIVED | SERVICE | Yes | probes | `limpiar_tss_de_ctx` on selection change | diagnóstico / CONTEXTO | Correct |
| `cs` (ConversationState) | ctx | A (shadow) | DOMAIN | Yes | write_shadow_into_ctx | sync/hydrate | Motor, facts | Dual vs legacy |
| `domains` / `active_domain_id` / stack | cs | E DOMAIN | DOMAIN | Yes | domain_lifecycle | pause/close | Motor | MAX_DOMAINS=3 |
| `facts` (cs) | cs | A/C | DOMAIN | Yes | upsert_fact | supersede / trim | Motor | MAX_FACT_HISTORY=3 |
| `pending_bot` / `pending_user` | cs / slot | G ACTION | DOMAIN | Yes | stamp_* | invalidate_pending* | Motor | Invalidation |
| `intencion` | ctx | I LEGACY | DOMAIN | Yes | playbooks / sync | cambio intención | Legacy N1 | Dual with journey |
| `hechos` | ctx | C/I | DOMAIN | Yes | flujos / comprensión | limpieza parcial | playbooks WiFi | Canonical for T70 |
| `pasos_cubiertos` | ctx | I LEGACY | DOMAIN | Yes | playbooks | — | proyección; cs covered canónico | Dual |
| `paso_idx` | ctx | D TEMP | DOMAIN | Yes | playbooks | — | cursor only | Must not erase facts |
| `multi_cuenta_pendiente` | ctx | D TEMP | ACTION | Yes | selection | apply_service_ref | journeys | — |
| `comprension_turno` | ctx | B CONVERS | TURN | Yes | preparar_turno | overwritten each turn | eleccion aviso deuda | Low trust |
| Historial mensajes | DB | B | CONV | Yes | add_mensaje | cierre hilo | LLM, heurísticas | Truncation in helpers |
| TrustedContext | Runtime arg | A | REQUEST | No (rebuild) | Runtime builder | N/A | Policy/Runtime | Correct |

Types: A TRUSTED · B CONVERSATIONAL · C DERIVED · D TEMPORARY · E DOMAIN · F SERVICE · G ACTION · H INVALIDATABLE · I LEGACY · J UNKNOWN

---

## 5. Context ownership

| Concern | Owner |
|---|---|
| Service identity | `selected_service_ref` + catalog |
| Client ownership | TrustedContext / abonado.client_number |
| Journey step | `eko_journey` |
| Domain slots / covered steps | ConversationState |
| Playbook cursor / hechos WiFi | Legacy ctx (still live) |
| Confirmation | `eko_action` + TrustedContext.confirmation_received |
| Wording | LLM / renderer |

LLM **must not** mutate selection (tested: `test_t22_casi_llm_cannot_mutate_selection_state`).

---

## 6. Context persistence

| Store | Content | Lifetime |
|---|---|---|
| `ConversacionCanal.contexto_json` | Full ctx including `cs`, `eko_journey`, legacy | Open conversation |
| `MensajeCanal` | Text turns | Conversation |
| New conversation after close | Empty `{}` | **Loss intentional** when hilo cerrado |

`set_contexto` dual-writes ConversationState shadow (`write_shadow_into_ctx`). On mismatch, logs `cs_shadow_mismatch` (observability).

---

## 7. Domain continuity

Mechanisms:

1. **Journey domain switch** (`maybe_handle_journey_turn`): explicit new intent → `_clear_stale_confirmation`, `previous_journey`, may preserve `selected_service` string on switch.  
2. **ConversationState** `apply_domain_signal`: pause current kind, resume/create other (tecnico/admin/comercial); closed slots do not reopen from historic signal.  
3. **Legacy `intencion`**: playbook classification still drives much of N1 when journeys miss.

**Preserved across billing↔connectivity switches (tests):** correlation/previous_journey; selection often preserved as string (`prev_sel`).  
**Cleared:** pending confirmations, diagnostic flags on selection change (not always on domain switch alone).

---

## 8. Service continuity

### Selection path

`resolve_service_selection` order: proposed id/login → text id/login → ordinal → single-service generic (“ese”) → natural type/product match → needs_input.

`apply_service_ref`:

- Writes `selected_service_ref` + compat `selected_service`  
- Sets `login_seleccionado` **only if login**; **pops** it for Sensa-like (no fabricated login) — **CONFIRMED correct**  
- On change: clears diagnostic, confirmation journey flags, pppoe/TSS

### Invalidation events (intentional)

| Event | Effect |
|---|---|
| New `ServiceRef` different id/login | Diagnostic + TSS + pending_confirmation cleared |
| Domain/journey switch | Stale `confirmation_pending` cleared (`_clear_stale_confirmation`) |
| Outage path | `_limpiar_ctx_outage` (outage keys; not full selection wipe by default) |

### Gaps

- Natural language **`"el fijo"`** does not hit telefonia hints (`fija` yes, `fijo` no) — see F-01.  
- Customers often say “fijo” for **fixed internet**; resolver also lacks that sense → ambiguity / re-ask.

---

## 9. Reference resolution

| Expression | Mechanism | Result |
|---|---|---|
| `ese` / `ese servicio` | Deterministic if **1** catalog row; else needs_input | Safe |
| Ordinals / `el segundo` | Against `selection_options` | Tested (C08) |
| `el internet` / `sensa` / `imowi` | `_natural_matches` type hints | Works |
| `la fija` / `teléfono` | telefonia hints | Works |
| **`el fijo`** | No hint `fijo` | **needs_input** (CONFIRMED) |
| **`el otro`** | No special case | **needs_input** (CONFIRMED) |
| `sí` | Confirmation **only if** pending; else selection gate | Tested C08 |
| `volviendo a lo anterior` | **No** general resolver | Gap F-03 |
| `y el internet` (resume) | `_is_resume_connectivity` cue list | Narrow, works for billing→inet |

**REFERENCE RESOLUTION ≠ INTENT DETECTION:** selection resolver is catalog-bound; intent/journey detection is separate (`detect_journey_name`, `clasificar_intencion`).

---

## 10. LLM context

Built primarily via:

- `eko_context.build_eko_facts` + `format_n1_contexto` → block **CONTEXTO_ABONADO** (customer, account, services catalog labels, billing, technical observations).  
- `diagnostico_n1` rules + `historial_mensajes` (full list often passed; helpers use last ~8 bot messages for cues).  
- Playbook/intención flags (wifi, facturación, Sensa).  

**Does LLM get enough for references?** Partial: catalog labels in CONTEXTO + historial text; **structured `selected_service_ref` is not guaranteed** as a first-class LLM field in CONTEXTO_ABONADO (facts list services; selection lives in journey/ctx). LLM may infer from history — **risk of stale text vs state**.

| Question | Answer |
|---|---|
| Enough for references? | Partial — structured selection for Runtime; LLM mostly historial + catalog |
| Receives forbidden authority? | Stripped confirmation / selection mutation (CASI tests) |
| Duplication? | Yes — legacy hechos + cs facts + journey + historial |
| Contradiction risk? | Possible if shadow ≠ legacy (logged) |
| Truncation? | Helpers `-ultimos: 8`; catalog items `[:20]`; growing hist grows prompt cost |
| Size limit? | No hard continuity contract; practical LLM window limits apply |

---

## 11. State vs history

| Information | Primary source today |
|---|---|
| Selected service | Structured: `selected_service_ref` |
| Domain / journey | Structured: eko_journey + cs slots |
| Intent (legacy) | Structured: `intencion` + detection |
| Ownership | TrustedContext / abonado |
| Customer data | BillTrack/Estate facts |
| Diagnostic result | Journey + ctx probe keys |
| Confirmation | eko_action pending |
| WiFi device facts | `hechos` (+ cs facts when synced) |
| “What did we ask?” | Historial + pending_bot / last_bot_act |
| Anaphora (“ese”, “el otro”) | Structured resolver **or** historial/LLM — weak for “el otro” |

Reconstruction from language when structured state exists is an anti-pattern still possible in Legacy LLM paths — Policy/Runtime mitigate for actions.

---

## 12. Playbook interaction

- Playbooks use `paso_idx`, `pasos_cubiertos`, `hechos`.  
- **Correct (T70):** `dispositivo_sin_ethernet` blocks cable steps; cursor must not erase facts.  
- Conversation motor / flujos skip contradictory WiFi steps.  
- Commercial playbooks (`alta_plan`, `baja_servicio`) are HANDOFF-oriented; **do not** consume `selected_service_ref` as commercial SoT (aligned with 2.4).  
- Risk: static playbook questions may re-ask identity/DNI when already in TrustedContext — often **security/scope** (class 1–2), not always bug.

---

## 13. Handoff continuity

| Event | Survives | Cleared / risk |
|---|---|---|
| Journey domain switch | Often `selected_service` string; previous_journey | Confirmation stale cleared |
| Agent handoff (`espera_agente`) | ctx JSON until reopen | New bot turns stopped; return depends on estado |
| Closed conversation | Historial exists | **New** conv → empty ctx |
| OV navigation / link | External; local ctx may remain | No commercial order state |
| Ticket create confirm reject | Action cleared | Selection usually kept |

**Question:** Does handoff wipe useful selection? **Not systematically** in journey switch (preserves prev_sel). Agent handoff freezes bot path; reopen after close **loses** ctx by design.

---

## 14. Reset / invalidation map

| Lugar | Campo | Trigger | Motivo | Correcto? | Riesgo |
|---|---|---|---|---|---|
| `apply_service_ref` | diagnostic, TSS, login if empty | Selection change | Fresh probes | Yes | — |
| `_clear_stale_confirmation` | eko_action pending | Domain/journey switch | Anti stale sí | Yes | — |
| `invalidate_pending*` | cs pending | Text / API | Anti stale Q | Yes | Over-invalidate |
| `_limpiar_ctx_outage` | outage keys | Outage flow | Scope outage | Yes | — |
| `limpiar_tss_de_ctx` | TSS | Selection change | Tech scope | Yes | — |
| `ctx.pop(JOURNEY_KEY)` | journey | Explicit clear | Journey end | Intentional | Continuity loss |
| New conv after closed | All ctx | Ticket closed / hilo cerrado | Fresh session | Intentional | User expects memory |
| `sync_from_legacy` | cs slots | Persist | Align shadow | Mostly | Cover dual |

**Intentional invalidation** dominates selection/confirmation. **Accidental loss** risk concentrates on: failed natural refs (re-ask), closed-thread reset, dual-layer divergence.

---

## 15. Repetition analysis

| Caso | Clasificación |
|---|---|
| Re-ask service when multi + ambiguous | 2 necessary scope / 1 security |
| Re-ask after `"el fijo"` fails | **4 pérdida / gap** (F-01) — CONFIRMED |
| Re-ask confirmation after domain switch | 1 security (stale cleared) |
| Re-ask DNI when unidentified | 1 security |
| Re-ask selection after already selected (spam) | Guarded by tests C04 / 5_no_repeat_selection_spam — **should not** |
| Playbook step again with facts known | Mitigated for WiFi ethernet (T70); other steps POSSIBLE |

---

## 16. Loop analysis

| Mechanism | Status |
|---|---|
| Selection loop | Tests assert no spam when selected |
| Confirmation loop | Pending required; bare “sí” without pending ≠ ticket |
| Domain switch → menu | Possible in Legacy; journeys try resume cues |
| Diagnostic re-run | Requires `_wants_rediagnose` or new selection — not auto |
| Duplicate inbound Meta message | `_omitir_duplicado` |

Existing suites: `test_eko_conversational_hardening_6`, `test_eko_agentic_journeys_5`, `test_continuidad_conversacional`, `test_domain_lifecycle`, `test_conversation_motor`.

---

## 17. Legacy compatibility

| Canonical (preferred) | Shadow / compat |
|---|---|
| `selected_service_ref` | `selected_service`, `login_seleccionado` |
| `cs.covered_steps` | `pasos_cubiertos` (hydrate once; sync does not reintroduce) |
| `eko_action` confirmation | `pending_confirmation` on journey |
| Journey `domain` | Legacy `intencion` / playbook kind |

**Dual-write:** `set_contexto` → `write_shadow_into_ctx`.  
**Dual-read:** `get_selected_ref` falls back to login strings.  
**Divergence:** possible; mismatch logged — FINDING F-04.

---

## 18. Conversation case analysis (A–H)

### CASE A — Service continuity (“qué servicios” → “el fijo” → “cuánto pago”)

| Expectation | Evidence |
|---|---|
| List services | `service_list` / catalog READ |
| Select “el fijo” | **FAIL** natural match (`el fijo` → needs_input) — CONFIRMED probe |
| “¿Y cuánto pago?” | `show_balance` is **account-level**, not service-scoped — selection may be unnecessary; billing journey switch possible |

**Impact:** User may be re-prompted for service before billing; billing itself does not need service ref.

### CASE B — Service switch (fijo → internet → “ese tiene problemas”)

| Turn | Expected | Actual (code) |
|---|---|---|
| Select internet | `el internet` → selected | CONFIRMED |
| “¿Y ese?” after switch | If 1 match context weak; multi → needs_input | “ese” alone with multi catalog → needs_input |
| Diagnostic | Requires fixed-internet diagnosticable ref | Sensa/TV not diagnosticable as PPPoE |

### CASE C — Ambiguous “¿Y ese?” with internet+Sensa

**CONFIRMED:** `ese` with ≥2 rows → `needs_input` / `service_selection_required`. Safe clarification.

### CASE D — Technical continuity (“internet no anda” → “¿Y por WiFi?”)

Hechos / playbook wifi + historial drive continuity; selection should remain if set. Domain may stay tecnico. **LIKELY** preserved; WiFi facts tested. Full end-to-end “por WiFi” after PPPoE: covered partially by WiFi playbook + comprehension — not one single test for exact phrase.

### CASE E — Negation (“No, me refiero al otro”)

Hardening test C07 switches with **explicit** “el del local” against options. Bare **“el otro”** → **needs_input** (CONFIRMED probe). Correction works when alternative is named/ordinal; pure anaphora weak.

### CASE F — Handoff return (“cambiar plan” → handoff → “qué plan tengo”)

Commercial = HANDOFF_ONLY. Inventory/plan labels still via `service_list` / account facts if abonado bound. Selection may persist in ctx if not closed. **LIKELY** READ still available; no commercial EFFECT.

### CASE G — “Volviendo a lo anterior…”

**No** general stack-pop of “previous topic” beyond domain_stack resume by **kind signal** and specific connectivity resume cues. Phrase alone → **NOT supported** (F-03).

### CASE H — Confirmation “sí”

Governed by `eko_action.status == confirmation_pending` + TrustedContext rebuild of confirmation_received from user text — **not** LLM. Tested extensively (4c/4d/5/6). Bare “sí” without pending does **not** create ticket (C08).

---

## 19. Findings matrix

| ID | Severidad | Estado | Área | Hallazgo | Evidencia | Impacto | Reproducción | Recomendación (futuro) |
|---|---|---|---|---|---|---|---|---|
| F-01 | HIGH | CONFIRMED | Selection | `"el fijo"` no matchea telefonia (`fija` sí) | Probe `resolve_service_selection`; `_natural_matches` keys | Re-ask / wrong domain | Static probe 2.5A | 2.5B: synonym map fijo↔fija / internet fijo |
| F-02 | MEDIUM | CONFIRMED | Reference | `"el otro"` sin resolución | Probe + looks_like_selection lacks “otro” | Forced re-list | Probe | 2.5B: alternate-of-selection_options |
| F-03 | MEDIUM | CONFIRMED | Domain | Sin “volviendo a lo anterior” genérico | Only `_is_resume_connectivity` cues | Topic loss | Code read | 2.5B: resume via domain_stack |
| F-04 | MEDIUM | LIKELY | Legacy | Triple state (ctx/journey/cs) | dual-write + dual-read | Occasional divergence | Logs mismatch | 2.5B: single-read contract |
| F-05 | LOW | CONFIRMED | LLM | Selección estructurada débil en CONTEXTO_ABONADO | format_n1_contexto | Anaphora via LLM guess | Code | Optional selected_ref in facts (read-only) |
| F-06 | INFO | CONFIRMED | Close | Nuevo hilo borra ctx | get_or_create closed | Expected memory loss | Code | Document UX |
| F-07 | INFO | CONFIRMED | Safety | Multi + ese → clarify | Probe + design | Good | Probe | Keep |
| F-08 | INFO | CONFIRMED | Selection | Change invalidates diag/TSS | apply_service_ref | Correct | Tests 2.2B/C | Keep |
| F-09 | INFO | CONFIRMED | Confirm | Domain switch clears stale confirm | `_clear_stale_confirmation` + C10 | Correct | Tests | Keep |
| F-10 | INFO | CONFIRMED | Playbook | Tablet/ethernet facts honored | test_continuidad T70 | Correct | pytest | Keep |
| F-11 | LOW | POSSIBLE | Playbook | Other static steps may re-ask known data | Pattern | UX friction | Not fully matrixed | 2.5C regression matrix |
| F-12 | LOW | LIKELY | Billing | “cuánto pago” no usa service ref | show_balance account-level | Usually OK | Code | Document in 2.5B |

---

## 20. Confirmed risks

1. **Natural language “fijo” gap** causes avoidable selection prompts (F-01).  
2. **Weak anaphora** for “el otro” / topic resume (F-02, F-03).  
3. **State layering** increases maintenance/divergence risk (F-04).  
4. **LLM historial vs structured selection** for references (F-05) — mitigated for EFFECTS by Runtime.

---

## 21. Not reproduced / correctly working

| Claim | Status |
|---|---|
| Selection always lost on domain switch | **NOT_REPRODUCED** — prev_sel often kept |
| “sí” alone creates tickets | **NOT_REPRODUCED** — pending required |
| Sensa fabricates login | **NOT_REPRODUCED** — login popped |
| WiFi asks ethernet for tablet after fact | **NOT_REPRODUCED** — blocked (T70) |
| LLM can set confirmation_received | **NOT_REPRODUCED** — stripped |
| Multi “ese” silently picks wrong service | **NOT_REPRODUCED** — needs_input |

---

## 22. Recommended future changes (do not implement in 2.5A)

1. Synonym / morphology for selection (`fijo`/`fija`, internet fijo vs telefonía).  
2. Deterministic “el otro” against `selection_options` / last ref.  
3. Explicit resume-from-`domain_stack` for “lo anterior”.  
4. Continuity contract: single read path for service selection.  
5. Optional read-only injection of `selected_service_ref` into CONTEXTO_ABONADO.  
6. Regression matrix 2.5C covering A–H + synonyms.

---

## 23. Proposed 2.5B scope — Context Continuity Contract

Document (only) that defines:

1. Canonical fields and writers/consumers.  
2. Invalidation rules (what clears what).  
3. Reference resolution contract (deterministic vs needs_input).  
4. Domain/journey switch continuity rules.  
5. Confirmation binding.  
6. State vs historial vs LLM obligations.  
7. Explicit non-goals (no new memory DB, no embeddings, no CASI changes).  
8. Acceptance criteria feeding 2.5C matrix and 2.5D hardening.

**Do not implement 2.5B automatically in this session.**

---

## 24. Explicit non-goals (2.5A)

- No code/prompt/playbook/CASI/Runtime/Policy changes  
- No Redis/embeddings/new RAG memory  
- No new capabilities or feature flags  
- No external calls / notifications / EFFECTS  
- No “fix” without evidence  

---

## 25. Validation results

| Check | Result |
|---|---|
| Static code inspection | Done (canal_abonado, journeys, selection, CS, motor, eko_context, runtime) |
| `pytest tests/test_eko_conversational_hardening_6.py tests/test_domain_lifecycle.py tests/test_eko_agentic_journeys_5.py tests/test_eko_service_management_2_2b.py` | **PASS** (all green) |
| `pytest tests/test_continuidad_conversacional.py tests/test_conversation_motor.py` | **PASS** (all green) |
| Offline probe `resolve_service_selection` (fijo/ese/el otro) | Executed locally — evidence for F-01/F-02/F-07 |
| Runtime / DB / API / migrations modified | **NONE** |
| External writes / notifications | **NONE** |

---

## Closure checklist

- [x] Real conversational flow map  
- [x] Context inventory with writers/consumers  
- [x] Resets/invalidation map  
- [x] selected_service_ref audited  
- [x] domain/journey/user_act audited  
- [x] pending/confirmation audited  
- [x] TrustedContext audited  
- [x] LLM context audited  
- [x] Playbook interaction audited  
- [x] Handoff audited  
- [x] References / repetitions / loops  
- [x] Cases A–H  
- [x] Confirmed vs hypothesis separated  
- [x] No behavior changes  
- [x] Validations documented  
- [x] 2.5B scope proposed  

**STATUS: PASS WITH FINDING** (discovery complete; continuity gaps F-01–F-03 are findings, not audit failure).
