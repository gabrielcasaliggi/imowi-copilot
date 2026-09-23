# EKO 2.5C — CONVERSATIONAL REGRESSION MATRIX

**Status:** PASS  
**Phase:** TEST COVERAGE ONLY — no production behavior changes  
**Depends on:** [2.5A Discovery](./EKO-2.5A-CONVERSATIONAL-QUALITY-CONTEXT-CONTINUITY-DISCOVERY.md) · [2.5B Contract](./EKO-2.5B-CONTEXT-CONTINUITY-CONTRACT.md)  
**Test module:** `tests/test_eko_conversational_regression_2_5c.py`

Principio: **TEST FIRST, HARDEN SECOND.**

---

## 1. Executive summary

Se convirtió el contrato 2.5B en una matriz ejecutable que:

1. **Documenta CURRENT** (asserts que deben PASS hoy).  
2. **Marca TARGET / EXPECTED_GAP** con `@pytest.mark.xfail(strict=False)` — no FAIL de CI.  
3. **Protege** selección, Sensa sin login, confirmación, dual-read, `ese` multi, invalidación post-cambio.  

**No** se implementó resolución de “el fijo”, “el otro”, resume NL, ni cambios CASI/Motor/Runtime/playbooks.

| Totales (2.5C suite) | Count |
|---|---|
| Tests | 46 |
| PASS (CURRENT / REGRESSION) | 39 |
| EXPECTED_GAP (XFAIL) | 7 |
| FAIL | 0 |
| NOT_APPLICABLE | 0 (matrix rows may mark N/A for product paths) |

---

## 2. Test architecture

| Piece | Role |
|---|---|
| `resolve_service_selection` | Unit reference resolution |
| `apply_service_ref` / `get_selected_ref` | Canonical selection + invalidation |
| `maybe_handle_journey_turn` | Domain switch / confirmation / resume cue |
| `domain_lifecycle` / `ConversationState` | `domain_stack` MAX_STACK |
| `@EXPECTED_GAP` | Future contract xfails |

Reuse: patterns from `test_eko_service_management_2_2b`, `test_eko_conversational_hardening_6`, `test_domain_lifecycle`.

---

## 3. Current vs Target semantics

| Category | CI behavior |
|---|---|
| **CURRENT_CONTRACT** | Assert today’s behavior → must PASS |
| **REGRESSION_PROTECTION** | Guard known-good → must PASS |
| **FUTURE_CONTRACT / EXPECTED_GAP** | Assert 2.5B target → XFAIL until 2.5D/E |
| **NOT_APPLICABLE** | Documented only when path absent |

**F-01 rule:** `"el fijo"` ≠ hardcode telefonía. Unique telefonia → may select (TARGET). Internet fijo + telefonia → **NEEDS_INPUT** (CURRENT = TARGET).

---

## 4. Full regression matrix

| ID | Dominio | Caso | Entrada / setup | Contexto previo | Resultado actual | Resultado objetivo | Estado |
|---|---|---|---|---|---|---|---|
| A03 | Service/Domain | Select survives billing | “cuánto debo” | internet selected | selection kept | same | **PASS** |
| A04 | Service | Explicit switch | internet → “la fija” | catalog | switches | same | **PASS** |
| A04-T | Service | “del fijo” unique phone | “Ahora… del fijo” | only telefonia | needs_input | selected | **EXPECTED_GAP** |
| A05 | Service | Switch invalidates diag | apply_service_ref change | diag+pppoe | cleared | same | **PASS** |
| B01 | Refs | “la fija” | — | inet+tel | selected tel | same | **PASS** |
| B02-C | Refs F-01 | “el fijo” unique tel | — | only tel | needs_input | selected | CURRENT doc + **EXPECTED_GAP** target |
| B02-A | Refs F-01 | “el fijo” ambiguous | — | inet+tel | needs_input | needs_input | **PASS** |
| B03 | Refs | “el internet” | unique / dual | — | select / needs_input | same | **PASS** |
| B04 | Refs | “ese” | 1 / N | — | select / needs_input | same | **PASS** |
| B05-C | Refs F-02 | “el otro” | 2 services | — | needs_input | unique alt select | CURRENT + **EXPECTED_GAP** |
| B05-3 | Refs F-02 | “el otro” 3-way | — | A+B+C | needs_input | needs_input | **PASS** |
| B06 | Resume F-03 | “volviendo…” | NL | stack | no kind signal | resume domain | **EXPECTED_GAP** |
| C04 | Domain | stack max 3 | programmatic | A→B | ≤3 + resume API | same | **PASS** |
| C04-g | Domain | no unbounded growth | loops | — | ≤ MAX_STACK | same | **PASS** |
| D01 | Confirm | “sí” sin pending | — | selection gate | no ticket | same | **PASS** |
| D02 | Confirm | stale on domain switch | “cuánto debo” | confirm pending | CLEARED; selection kept | same | **PASS** |
| D02-L | Confirm | LLM cannot confirm | sanitize/parse | — | stripped | same | **PASS** |
| D03 | Confirm | reject flag | TrustedContext | — | rejected=True | same | **PASS** |
| E01 | Ownership | multi “ese” | — | 2 inet | needs_input | same | **PASS** |
| E02 | Ownership | foreign id | proposed | — | denied | same | **PASS** |
| E03 | Ownership | missing CN | — | — | needs_input | same | **PASS** |
| E03-L | Ownership | LLM CN | sanitize | — | stripped | same | **PASS** |
| F01 | Sensa | select no login | apply_ref | — | ref OK, login empty | same | **PASS** |
| F01-N | Sensa | natural “Sensa” | — | inet+tv | selected | same | **PASS** |
| F02 | Sensa | survive billing | domain switch | Sensa | no fake login | same | **PASS** |
| G03 | Tech | change after diag | switch | diag | invalidated | same | **PASS** |
| H01 | Correction | “No, la fija” | after internet | — | switches | same | **PASS** |
| H01-T | Correction | “No, el fijo” | unique tel | — | needs_input | selected | **EXPECTED_GAP** |
| H02 | Correction | bare “no” | no pending | selection | kept | same | **PASS** |
| I01 | Handoff | cambiar plan | clasificar | — | intent non-empty | HANDOFF exists | **PASS** |
| I02 | Handoff | return | — | — | N/A product | restore | **EXPECTED_GAP** |
| J01 | Resume | “y el internet” | billing | selection | cue works; sel kept | same | **PASS** |
| J02 | Resume | no stack cue | NL | empty | kind=None | NEEDS_INPUT-safe | **PASS** |
| K01 | Playbook | skip re-ask | valid ref | — | not enforced | consume ref | **EXPECTED_GAP** |
| L01 | State | multi ese | — | — | needs_input | same | **PASS** |
| L02 | State | LLM foreign | proposal | prior ref | denied; no mutate | same | **PASS** |
| M01 | Legacy | ref vs selected_service | — | — | coherent | same | **PASS** |
| M02 | Legacy | Sensa dual-read | — | — | login empty OK | same | **PASS** |
| M03 | Legacy | envelope | hechos+ref | — | both present | same | **PASS** |
| N04 | Loops | selection≠diag | ese | — | diagnostic_started false | same | **PASS** |
| CS | CS | hydrate | pause | — | roundtrip | same | **PASS** |

---

## 5. F-01 / F-02 / F-03

| ID | CURRENT | TARGET | Tests |
|---|---|---|---|
| **F-01** | `el fijo` → needs_input (even unique tel) | unique tel → select; inet+tel → needs_input | `b02_*`, `a04_target_*`, `h01_target_*` |
| **F-02** | `el otro` → needs_input | unique alternate → select; ≥2 alts → needs_input | `b05_*` |
| **F-03** | NL resume not a kind signal; programmatic stack OK | NL → resume via domain_stack | `b06_j01_*`, `j02_*`, `c04_*`, `j01_narrow_*` |

---

## 6–18. Family coverage (index)

| Family | Covered in suite |
|---|---|
| A Service continuity | A03, A04, A05 |
| B Natural references | B01–B06 |
| C Domain continuity | C04 (+ A03 switch) |
| D Confirmation | D01–D03 |
| E Multi-account | E01–E03 |
| F Sensa | F01–F02 |
| G Technical | G03 |
| H Correction | H01–H02 |
| I Handoff | I01–I02 |
| J Resume | J01–J02, B06 |
| K Playbook | K01 (gap) |
| L State vs history | L01–L02 |
| M Legacy dual-read | M01–M03 |
| N Loops | N04 |

Cases A–H of 2.5A narrative are represented via these IDs (list→select via resolver; follow-ups via journey; WiFi deep playbook path remains in `test_continuidad_conversacional` as adjacent protection).

---

## 19. Test results

```text
pytest tests/test_eko_conversational_regression_2_5c.py
→ 39 passed, 7 xfailed, 0 failed

pytest tests/test_eko_conversational_hardening_6.py \
       tests/test_domain_lifecycle.py \
       tests/test_eko_service_management_2_2b.py \
       tests/test_conversation_motor.py
→ PASS

ruff check tests/test_eko_conversational_regression_2_5c.py
→ All checks passed
```

---

## 20. Known expected gaps (do not “fix” in 2.5C)

1. **F-01** synonym / morphology for `fijo` (context-sensitive).  
2. **F-02** relative reference API (`el otro` + current_ref).  
3. **F-03** NL → `domain_stack` resume.  
4. **K01** playbooks must consume valid `selected_service_ref` before re-asking.  
5. **I02** handoff return / restore.  

---

## 21. 2.5D implementation scope (recommendation)

Order after this safety net:

1. **Reference resolution hardening (2.5E overlap OK to start in 2.5D):** `fijo`/`fija` map + ambiguity with fixed-internet; wire relative “el otro”.  
2. **Single-read path:** prefer `get_selected_ref` everywhere; keep projections.  
3. **NL resume:** map “volviendo a lo anterior” → `resume_domain` / stack top with NEEDS_INPUT fallback.  
4. **Playbook ask-gate:** skip questions when structured context valid (K01).  
5. **Do not** touch CASI ownership rules, Billing 2.1, Proactive 2.3, Commercial 2.4.

**Do not implement 2.5D automatically in this phase.**

---

## Closure checklist

- [x] Full matrix document  
- [x] F-01, F-02, F-03 covered  
- [x] Families A–N covered  
- [x] Current vs Target separated  
- [x] No production behavior changes  
- [x] No DB/migrations/effects  
- [x] Tests + ruff documented  
- [x] 2.5D recommendation  

**STATUS: PASS**
