# ADR (borrador) — Contrato de turno de Eko: journeys ↔ legacy

**Estado:** ACEPTADO por Gabriel (2026-10-04). Implementación por tandas; ver §e. · **Fecha:** 2026-10-04 · **Base:** `17fd0d9`
**Insumos:** `docs/AUDIT-CONVERSACIONAL-2026-10.md` (Parte 1 y Parte 2, 12 causas raíz / 48 xfails) y `tests/e2e_conv`.
**Reglas de producto vigentes:** R1 (móvil/Sensa/VoIP: playbook + KB; **pedido explícito de agente → deriva directo; playbook agotado → ofrece y espera «sí»; nunca ticket sin una de las dos**) y
R2 (aviso de deuda: informativo, una vez por conversación, no bloquea).

> **Aviso 2.5.** Algunos cambios (RC-10/11 sobre `resolve_service_selection`, §12 de `EKO-2.5-…FREEZE.md`) tocan piezas
> congeladas. Este ADR es la *propuesta explícita* que exige `CLAUDE.md` §3; nada se implementa sin tu aprobación.

---

## 0. Problema en una frase

Hoy un journey **no sabe soltar el turno**: o queda vivo con estado pendiente que captura cualquier texto (RC-1, RC-12), o
autoriza casi cualquier mensaje después de resolver (RC-3). Cuando suelta, deja `ctx` con restos (`menu_paso`,
`intencion` de journey) que hacen que el legacy responda mal (RC-5). Y dos capas deciden lo mismo en distinto orden (RC-6/7/8).

## a) Contrato de turno

En cada turno, `maybe_handle_journey_turn` devuelve **exactamente uno** de:

| Resultado | Significado | Texto | Estado |
|---|---|---|---|
| `RESPOND(texto)` | El journey atiende y responde | **no vacío** | actualiza `eko_journey`; el canal envía y retorna |
| `PASS(motivo)` | El journey **no** atiende; el turno pasa al legacy | — | libera estado vía `journey_release` (§b); el canal sigue al legacy |
| `HOLD` | Silencio **solo** ante cortesía pura (`_is_pure_courtesy`) de un journey terminado | vacío | sin cambios |

Reglas duras (testeables):
1. `handled=True` con texto vacío es **inválido** salvo `HOLD` por cortesía pura o cierre explícito (`mode="cerrado"`,
   ya enviado por `_cerrar_consulta_resuelta`). Hoy FIX-1 (`aa50ac9`) lo parchea en el canal; el contrato lo vuelve parte del tipo.
2. Un journey solo responde `RESPOND` si **reclama** el texto (`claims(texto, ctx)`, §c). Si no lo reclama → `PASS`.
3. `RESPOND` no puede ejecutar una acción de efecto (ticket, nota) sin confirmación vigente del abonado (I6, R1), **salvo** el pedido explícito de agente (regla 5).
4. `PASS` y `RESPOND` son excluyentes en el mismo turno (XOR con el legacy, igual que el XOR Runtime/Legacy de 2.6).
5. **Handoff.** El pedido explícito de agente se atiende **desde cualquier estado de journey** y **el pedido ES la confirmación**:
   deriva directo (crea el ticket) sin pedir un segundo «sí». Si el bot *ofrece* derivar (playbook agotado, sin sesión), ahí sí espera
   el «sí» del abonado. Nunca hay ticket sin una de las dos (I6, R1).

**Cuándo un journey está «terminado».** Una sola definición (extiende `_journey_is_resolved`, `eko_journeys.py:631`):
`step == "done"` **y** sin `next_required_input` **y** sin `pending_confirmation` **y** sin `continuity_pending`.
Además, tras emitir un **mensaje terminal** (p. ej. «no veo Internet fijo», información de ticket, saldo) el journey pasa a
`done` en el mismo turno (hoy queda en `respond`, RC-12).

**Qué lo mantiene vivo** (única lista): `next_required_input` (selección, login, identidad), `pending_confirmation`
(derivación), `continuity_pending` (oferta de continuidad). **Todo estado pendiente expira** al primer texto no relacionado
y no cortés: la confirmación se cancela (sin ticket), la selección queda sin resolver y el turno hace `PASS`.
Repreguntar es válido **una vez** por pendiente (contador en `eko_journey.reprompts`); la segunda vez → `PASS`.

## b) Claves de `ctx` que se limpian al hacer PASS (un solo lugar)

Una única función `journey_release(ctx, motivo)` en `eko_journeys.py`, llamada solo desde el contrato (nadie más limpia):

| Clave | ¿Se limpia al PASS? | Motivo |
|---|---|---|
| `eko_journey.pending_confirmation`, `confirmation_correlation` | sí | no capturar el próximo texto (RC-1) |
| `eko_journey.next_required_input`, `asked_selection`, `selection_options` | sí | idem (RC-12) |
| `eko_journey.reprompts` (nuevo campo del journey, no de `ctx`) | sí | contador por pendiente |
| `ctx.menu_paso`, `ctx.menu_servicio` | sí, **si** el journey consumió esa respuesta | que el legacy no reinterprete el texto como respuesta del menú (RC-5) |
| `ctx.intencion` | sí, **solo** si vale una intención de journey (`consulta_servicios`, `facturacion`, `estado_ticket`, `seguimiento_instalacion`) | ya parcheado localmente en `fa565f5`; pasa a regla general |
| `ctx.multi_cuenta_pendiente` | sí | selección expirada |
| `ctx.aviso_deuda_ofrecido` | **no** | R2: el aviso es una vez por conversación |
| `ctx.eko_no_fixed_internet` | **no** | evita repetir el mensaje |
| `ctx.pppoe_*`, `uisp_*`, `bcm_*`, `tss_*` | **no** (los limpia `apply_service_ref`, 2.5-ext) | planta ligada al servicio |
| `eko_journey.selected_service_ref` | **no** | autoridad de 2.5; el PASS nunca toca la selección |

## c) `_resolved_turn_authorizes_handler` (`eko_journeys.py:747-755`)

Hoy: devuelve `True` si hay reingreso a Internet, seguimiento de incidente, nota de ticket, `detect_journey_name(texto)` o
**`_billing_user_act(texto) != "balance"`**. La última condición es casi siempre verdadera, por eso un journey ya resuelto
captura «sigue igual», «sí, pagar», etc. (RC-3).

Propuesta: **lista blanca** de frases que reclaman un journey terminado; todo lo demás → `PASS`.

| Autoriza (sí) | No autoriza (PASS) |
|---|---|
| Reingreso explícito a Internet (`_wants_connectivity_reentry`) | Texto libre sin dominio («sigue igual», «ya probé todo») |
| Seguimiento de incidente / ticket (`_wants_incident_followup`, frases de ticket, nota de cliente) | «sí»/«no» sin una oferta previa del propio bot |
| Pedido explícito de listar servicios o cambiar de servicio (frases de `service_catalog`; login del catálogo en el texto) | Dígitos sueltos fuera del turno inmediato a un menú |
| Acto de facturación **específico** (vencimiento, historial, factura, pagar) — no el «saldo» por defecto | Quejas o síntomas nuevos de otro dominio (los toma el legacy / lifecycle) |
| Dígito/«el N» **solo** si el turno anterior del bot fue el menú de selección o su «Listo/Ya tengo seleccionado» | Cortesía pura (→ `HOLD`) |
| «ya se arregló» / «ya anda» (**cierra el journey**: acuse y `done`) | — |
| «sí»/«no» **inmediatamente después de una oferta del propio bot** (confirmación o selección) | — |

El pedido de agente **no** pasa por esta función: lo maneja siempre la rama de handoff (§a, regla 5), desde cualquier estado, y el pedido es la confirmación.

## d) Dueño de `ctx.intencion`

Hoy lo escriben **59 sitios en 7 archivos** (`canal_abonado.py` 43, `canal_diagnostico_ia.py` 9, `eko_journeys.py` 3,
`turno_e1.py`, `comprension_abonado.py`, `canal_outage.py`, `conversation_motor.py` vía `apply_cs_to_legacy`, `:947`).

Propuesta — **un único dueño: el lifecycle de dominios** (`ConversationState` / `apply_cs_to_legacy`), que proyecta la
intención del dominio activo. Migración en tres pasos, cada uno con sus tests. **Solo se ejecutan los pasos 1 y 2; el paso 3 queda diferido** (no se reduce ningún escritor del legacy en esta etapa):
1. **Journeys dejan de escribir `ctx.intencion`** (`eko_journeys.py:3682`, `:3734`, `:3741`); usan solo `eko_journey.intent`.
   El helper `_intencion_tras_lifecycle` (`fa565f5`) queda como red de seguridad temporal.
2. Todos los demás escritores pasan por `set_intencion(ctx, valor, fuente)` (sin cambio de comportamiento, con log de la fuente).
3. Los escritores del legacy que hoy *deciden* (no proyectan) se reducen a los que corresponden al lifecycle; el resto lee.
Invariante resultante: **el journey nunca es dueño de la intención de la conversación.**

## e) Causa raíz → parte del contrato → orden de implementación

| Causa | Parte del contrato que la arregla | Riesgo | Orden |
|---|---|---|---|
| **H6** pedido de agente tras diagnóstico no deriva (el journey lo ignora o repite la confirmación) | §a regla 5 **Handoff**: el pedido explícito se atiende desde cualquier estado y deriva directo | bajo-medio (2.6K, 2.5D-4) | **0** |
| RC-10 `_extract_service_id` toma «id» | (fuera del contrato) arreglo puntual de regex en 2.2B | bajo (1 línea + tests 2.2B) | 1 |
| RC-11 solo logins `INT*` | resolver login contra el **catálogo** en vez de regex `INT*` | bajo-medio (2.2B/2.5D-2) | 2 |
| RC-12 «sin Internet fijo» abierto | §a «terminado»: mensaje terminal → `done` | bajo | 3 |
| RC-9 selección = callejón / problema perdido | §a: tras selección, `RESPOND` con siguiente paso; guardar el problema en `eko_journey` | medio | 4 |
| RC-1 confirmación atrapa el turno | §a: expiración + `PASS` ante texto no relacionado | medio (2.6K, 2.7D/E) | 5 |
| RC-3 journey captura texto libre | §c lista blanca | **medio-alto** (2.7E cierre, continuidad) | 6 |
| RC-2 «sí» no confirma | `journey_release`/prompt marca también el *action state* `confirmation_pending` (o el journey acepta el sí por su propio flag) | **alto** (2.6K create_ticket, XOR Runtime/Legacy) | 7 |
| RC-5 saludo genérico | §b: el PASS libera `menu_paso`/intención; el legacy no cae en `general` con contexto vivo | medio | 8 |
| RC-6 / RC-7 aviso de saldo | un solo emisor del aviso, **informativo y único** (R2), antes de la rama técnica y también con journeys ON | medio (CTX-2, flujo de deuda) | 9 |
| RC-4 escalación automática | el agotamiento **ofrece** derivar y espera confirmación (R1/I6) | **alto** (cambia tickets) | 10 |
| RC-8 corte masivo vs journeys | el journey de conectividad consulta el corte antes de diagnosticar (o el corte se evalúa antes de journeys) | medio-alto (outages, proactivo) | 11 |

**RC-2 es prerrequisito de RC-4:** hasta que el «sí» a una *oferta* del bot confirme de verdad, el agotamiento del playbook no puede pasar de «crear ticket» a «ofrecer y esperar». (H6 no depende de RC-2: el pedido explícito deriva sin segundo «sí».)

Criterio: de menor a mayor riesgo y de menos a más superficie congelada (2.5/2.6/2.7). Cada paso se mide con `tests/e2e_conv`:
al hacer pasar un xfail estricto, el test avisa y se retira el marcador en el mismo commit.

## f) Riesgos para 2.5 / 2.6 / 2.7 (cerrados) y cómo se protege lo validado

| Área | Archivos que se tocan | Tests de protección existentes |
|---|---|---|
| 2.2B / 2.5D-1/2 (selección, `ServiceRef`) | `eko_service_selection.py` (RC-10/11) | `test_eko_service_management_2_2a/b/c/d`, `test_eko_canonical_service_read_2_5d1`, `test_eko_reference_resolution_2_5d2`, `test_eko_c_menu_seleccion`, `test_eko_d_seleccion_idempotente` |
| 2.5C/D (continuidad, dominios, handoff) | `eko_journeys.py` (§a/§c), `canal_abonado.py` (intención) | `test_eko_conversational_regression_2_5c`, `test_eko_domain_stack_resume_2_5d3`, `test_eko_playbook_handoff_continuity_2_5d4`, `test_eko_turn_continuity` |
| 2.6K (create_ticket Runtime, XOR) | `eko_action_bridge.py` (RC-2), `canal_abonado.py` (RC-4) | `test_eko_create_ticket_runtime_2_6k`, `test_eko_runtime_isolation_2_6nc`, `test_eko_n1_ticket_customer_note_2_6i`, `test_eko_ticket_customer_note_2_6e` |
| 2.7D/E (incidente CX, cierre) | `eko_journeys.py` (§a, §c) | `test_eko_incident_cx_2_7d`, `test_eko_conversational_closure_2_7e`, `test_eko_deferred_close`, `test_eko_fix1_hold_sin_texto` |
| CASI / planta | no se tocan | `test_guardrails_planta`, `test_resolved_authority`, `test_escalate_authority` |

Cómo se protege:
1. **Cero cambios de comportamiento sin test que lo exija**: cada paso del orden (e) arranca con el xfail estricto de `e2e_conv` que lo cubre.
2. **Antes/después**: correr los archivos de la tabla antes de tocar y después de cada commit; el cierre exige ambas tandas verdes
   (`pytest -m e2e_conv` y `pytest -m "not e2e_conv"`, ver `docs/TESTING-TANDAS.md`).
3. **Un commit por causa**, con hash previo para rollback; sin mezclar causas.
4. **Contratos intactos**: `get_selected_ref` (lectura única), `apply_service_ref` (escritura única), CASI (el LLM no es autoridad,
   Proposal ≠ transición) y XOR Runtime/Legacy no cambian de semántica. El `PASS` nunca escribe `selected_service_ref`.
5. **Silencio legítimo preservado**: cortesía pura (`post_resolution_courtesy`) y cierre explícito siguen sin respuesta/ya enviados.
6. **No usar flags nuevos** para el contrato (duplicaría estados: hoy ya hay 16 combinaciones de interruptores); el rollback es por commit.

## Fuera de alcance de este ADR
Implementación; cambios de copy; KB; el arreglo de planta real (Radius/UISP/BCM); y el modo de LLM «normal» en los tests.

## Decisiones (APROBADAS por Gabriel, 2026-10-04)
1. **APROBADA.** Contrato `RESPOND / PASS / HOLD` (§a) y orden de (e), con H6 como orden 0.
2. **APROBADA.** Dueño único de `ctx.intencion`: el lifecycle de dominios (§d). Se ejecutan solo los pasos 1 y 2; el paso 3 queda diferido.
3. **APROBADA.** La lista blanca de §c, con «ya se arregló / ya anda» y el «sí/no» tras una oferta del propio bot.
4. **APROBADA.** RC-10/11 como cambio explícito de 2.5/2.2B, **acotado** a `_extract_service_id` y a la resolución de login contra el
   catálogo, con regresión dedicada (§12 del freeze). No se toca `get_selected_ref` ni `apply_service_ref`.

Orden de implementación aceptado (tanda 1): Fase 0 docs → H6 → RC-10 → RC-11 → RC-12.
