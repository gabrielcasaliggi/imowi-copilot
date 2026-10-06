# Auditoría conversacional de Eko — Parte 1 (estática)

**Fecha:** 2026-10-04 · **Estado:** borrador, sin commitear · **HEAD auditado:** `7d2dda8`
**Método:** lectura de código, `git log` y `grep`. En esta parte **no se ejecutó el producto ni los tests**.
**Alcance:** por qué el flujo conversacional (WhatsApp/portal) se volvió difícil de razonar y de probar.
**Fuera de alcance:** la Parte 2 (14 escenarios en worktrees de fines de agosto vs HEAD). Queda esperando OK.

> Lo que no pude verificar: valores reales de producción (no se leyó `.env` ni el server). El único dato
> de prod que tengo es el que dio Gabriel: `EKO_JOURNEYS_ENABLED=true`.

---

## 1. Línea de tiempo

Commits por mes: may 3 · jun 23 · jul 42 · **ago 202** · sep 106 · oct 9 (`git log --format=%ad`).

| Fecha | Hito (hash) | Qué cambia para la conversación |
|---|---|---|
| hasta 2026-08-31 | `0f63286` (último commit de agosto) | Solo **N1 legacy**: `canal_abonado.py` + playbooks. No existen `eko_journeys`, `eko_context`, `portal_services`, `canal_diagnostico_ia`. |
| 09-02 → 09-17 | `1941725` comprensión, `9e48fbd` BCM, `1e225d4` protocolo de mesa, `8d77114` auth WA, `d792811` trámites, app móvil | Se agregan fuentes (BCM, UISP, Radius) y flujos (WiFi/BCM, OV, trámites) **dentro del mismo legacy**. |
| 09-20 | `a74c569` CASI 10B–13C | Se consolidan `ConversationState` (`ctx["cs"]`), dominios y lifecycle (`domain_adapter`; `git blame` de `canal_abonado.py:3748` apunta a este commit). Segunda fuente de verdad de "de qué se habla". |
| 09-21 | `ffe1088` agentic ops F3–7 | Aparecen **journeys** y el **Action Runtime**, "apagados por defecto". Tercera capa. |
| 09-22 | `40ea8e2` Billing 2.1 / Service Mgmt 2.2 / Proactive | Selección de servicio (`selected_service_ref`), `service_catalog`, menú numerado, `_extract_service_id`. |
| 09-23 | `573184b` ticket ops 2.5–2.6Q | `create_ticket` por Runtime, confirmación, XOR Runtime/Legacy. |
| 09-28 | `fd210ca` 2.7D, `ebd5c58`, `10c7924`, `d36a1ea` | Continuidad de incidente; "no reenviar diagnóstico tras gracias". |
| 09-29 | `813a6d1`, `e5952d2`, `b67183d`, `513ef37` | Serie de **cierre post-resolución**: nace `post_resolution_hold` (silencio). |
| 10-02 → 10-04 | `64cdf9b`, `c350bb6`, `04c1aff`, `c4db413`, `8023f34`, `aa50ac9`, `fa565f5`, `9ba30d2`, `7d2dda8` | 2.8A, CTX-1/2, 2.5-ext, FIX-1, A, C, D (esta sesión). |

**Lectura:** en 5 semanas (09-20 → 09-29) se montaron **tres capas** de decisión sobre el legacy
(CASI/dominios, journeys, Runtime) y una serie de parches de cierre. Cada capa trajo su propio
clasificador y su propio estado (secciones 2, 5).

---

## 2. Inventario de claves de contexto

Cuenta de claves distintas referenciadas como `ctx["..."]` / `ctx.get("...")` en `app/` (`grep`, cota inferior;
no cuenta `trusted.ctx`, `st[...]` ni diccionarios armados aparte): **135 claves de primer nivel**.

| Familia | Ejemplos (referencias) | Quién escribe | Observación |
|---|---|---|---|
| Intención / paso | `intencion` (109), `paso_idx` (74), `diag_turnos` (51), `pasos_cubiertos` (44), `intencion_tecnica_pendiente` (25), `hechos` (23) | legacy, lifecycle, **journeys** | `intencion` la escriben ≥3 capas (ver §5). |
| Servicio elegido | `login_seleccionado` (20), `multi_cuenta_pendiente` (15), `pppoe_login`, `wifi_bcm_login`, `eko_journey.selected_service_ref` | legacy, wifi_bcm, journeys, sync | **4 representaciones** del "servicio en foco". |
| Menú / saludo | `menu_paso` (17), `menu_servicio` (7), `saludo` (11), `invitado`, `visitante` | legacy | `menu_paso` sobrevive a los turnos que atiende un journey. |
| Planta | `pppoe_*` (10), `bcm_*` (8), `uisp_*` (7), `tss_*` (9), `tecnologia_acceso` | probes, Runtime, sync de login | Sin dueño de servicio; se limpian parcialmente (2.5-ext). |
| WiFi/BCM | `wifi_bcm_*` (10 claves) | `wifi_bcm.py` | Flujo paralelo con su propia selección de destino. |
| Corte | `outage_id`, `outage_individual`, `outage_resuelto_avisado`, `outage_*` (7) | `canal_outage.py` | Duplicado por `tss_*` / `incident` en `portal_connectivity`. |
| Cierre / CSAT | `encuesta_*` (7), `csat_*`, `cierre_por`, `pidio_humano`, `ultima_queja`, `reiteracion_queja` | legacy | — |
| Identidad | `identificado`, `dni`, `phone_candidates` (13), `phone_auth_asked`, `pidio_dni` | legacy, WA auth | — |
| Estado de dominio | `cs` (ConversationState: dominios, covers, pending) | `domain_adapter`, `conversation_motor` | Segunda "fuente de verdad" de la intención. |
| Estado de journey | `eko_journey`: ~25 campos (`step`, `name`, `intent`, `selected_service*`, `next_required_input`, `selection_options`, `pending_confirmation`, `continuity_*`, `resolved_ack`, …) | `eko_journeys.py` (`set_journey`, `_new_journey` en `:417`) | Tercera estructura de estado. |

**Problemas estructurales visibles sin ejecutar nada**
1. `intencion` tiene tres dueños con semánticas distintas: el legacy (playbook), el lifecycle (proyección del dominio)
   y el journey (`_intent_for`, p. ej. `consulta_servicios`). Ya produjo un bug real: `canal_abonado.py:3748`
   (arreglado en `fa565f5`).
2. `menu_paso` (legacy) y `eko_journey.step` (journey) pueden estar "abiertos" a la vez; quien responde depende del orden (§3).
3. No hay un esquema de `ctx`: las claves nacen donde se necesitan; no hay lista de las que son por-servicio ni TTL.

---

## 3. Mapa del turno (`procesar_mensaje_entrante`, `canal_abonado.py:5132`–fin, ≈2.750 líneas)

Orden de precedencia de lo que decide la respuesta (primera rama que responde gana):

| # | Línea | Etapa | Notas |
|---|---|---|---|
| 1 | 5230 | hilo cerrado → pedir uno nuevo | — |
| 2 | 5252–5266 | invalidar confirmaciones stale, `cs.turn += 1` | — |
| 3 | 5275 | capa de comprensión (`interpretar_turno_abonado`) | aditiva |
| 4 | 5291 | Runtime: completar `create_ticket` tras "sí/no" | **puede responder** |
| 5 | 5298 | auth WhatsApp por MSISDN | — |
| 6 | 5317 | retorno de handoff (validación) | — |
| 7 | **5332** | **Journeys** (`maybe_handle_journey_turn`) | **corre antes** de identificación por DNI, menú, outage y playbooks |
| 8 | 5362–5393 | cierre temprano, solo-DNI | — |
| 9 | 5446 | clave/SSID WiFi (BCM) | — |
| 10 | 5481 | **corte masivo por NAS** (`_talvez_respuesta_outage`) | **después** de journeys: con journeys ON gana el journey |
| 11 | 5489–5533 | **menú post-ID** (`menu_paso`) | antes de `pide_humano` |
| 12 | 5533–5700 | Domain Selection, how-to, frustración, reiteración | — |
| 13 | 5701 | escape *agente* / pedir humano | — |
| 14 | 5783 | sin abonado: pedir DNI | — |
| 15 | 6005 | saldo/pago/OV (respuesta fija) | duplica `_advance_billing` (§5) |
| 16 | 6306–6613 | corte por deuda, saludo corto, informar pago, aviso de deuda, doble tema | — |
| 17 | 6860–7223 | refinar internet, lifecycle, móvil genérico, reclasificar | — |
| 18 | 7408+ | continuación con diagnóstico IA, resuelto, derivación, avance de playbook | `_aplicar_diagnostico_ia` (`canal_diagnostico_ia.py`) |

**Hechos clave**
- Un único consumidor "principal" de journeys (`:5332`) y un segundo en espera de agente (`_try_incident_cx_en_espera`, `canal_abonado.py:4318`, llamada a journeys en `:4390`).
- Un journey que responde **no pasa** por las etapas 8–18: no limpia `menu_paso`, no clasifica el texto con el legacy y no
  actualiza `paso_idx` ni `pasos_cubiertos`. Cuando después el legacy retoma, hereda estado viejo.
- Una sola función de ≈2.750 líneas con decenas de `return`; no se puede razonar por inspección cuál rama responde.

---

## 4. Flags y configuración

| Flag | Dónde | Default | Efecto |
|---|---|---|---|
| `EKO_JOURNEYS_ENABLED` | `config.py:234` | `false` | **Prod = `true`** (dato de Gabriel). Enciende toda la capa de journeys. |
| `EKO_JOURNEYS_CHANNELS`, `EKO_JOURNEYS_ORG_IDS` | `config.py:237`, `:241` | vacío = todo | Allowlists; con master ON y vacías, journeys aplican a todos. |
| `ACTION_RUNTIME_ENABLED` | `config.py:203` | `false` | Habilita despacho Runtime (XOR vs Legacy). |
| `ACTION_RUNTIME_ACTIONS` | `config.py:206` | set por defecto (13 acciones) | Prod puede diferir (`ticket_customer_note` según CSV). No verificado. |
| `canal.usar_llama_default`, `canal.diagnostico_ia` | `platform_settings.py:560`, `:569` | `True` | Se editan en admin (DB), no en env. Apagarlos hace que `_aplicar_diagnostico_ia` devuelva `None`. |
| `BILLTRACK_ENABLED`, `RADIUS_API_ENABLED`, `UISP_ENABLED`, `BCM_ENABLED`, `OV_BATAN_ENABLED` | `config.py:188`–`:314` | `false` | Fuentes externas; sin ellas el diagnóstico es "no disponible". |
| `WHISPER_ENABLED`, `TTS_ENABLED` | `config.py:356`, `:374` | `false` | Canal de voz. |
| `AI_API_KEY` | `config.py:593` | — | **Solo emite un aviso de arranque**; ninguna ruta lo consulta. |

**Combinaciones.** Solo con 4 interruptores (journeys, runtime, `diagnostico_ia`, `usar_llama`) hay 16 estados, y cada fuente externa
(BillTrack, Radius, UISP, BCM, OV) multiplica. Los tests de journeys que revisé (p. ej. `test_eko_service_management_2_2c.py`)
activan Runtime con 4 acciones y fuentes mockeadas; no vi una matriz de combinaciones.

---

## 5. Lógica duplicada (misma decisión en ≥2 lugares)

| Decisión | Implementaciones | Riesgo |
|---|---|---|
| Clasificar intención | `clasificar_intencion` (`flujos_abonado.py:1801`), `detect_journey_name` (`eko_journeys.py:359`), `interpretar_turno_abonado` (`comprension_abonado.py:385`), `kind_from_user_signal` (`domain_lifecycle.py:452`), `refinar_playbook_internet` (`:2872`), `ajustar_intencion_a_padron` (`:1679`), `resolver_menu_servicio` (`:1449`) | 7 clasificadores; el mismo texto ("imowi") dispara selección en uno y móvil en otro. |
| Cierre / "gracias" / "resuelto" | `indica_resuelto` (`flujos_abonado.py:3869`), `_cliente_desiste_o_resuelto` (`canal_abonado.py:3289`), `_cierra_consulta_facturacion` (`diagnostico_n1.py:1550`), `_is_pure_courtesy` (`eko_journeys.py:852`), `_wants_post_diag_close` (`:868`), `_customer_confirmed_resolution` (`:642`), `_wants_explicit_conversation_close` (`:593`), `_is_continuity_decline` (`:693`) | 8 detectores. "ya se arregló" no es reconocido por el del journey (ver §7). |
| Pedir agente | `pide_humano` (`flujos_abonado.py:4248`), `pide_humano_en_flujo_activo` (`:4338`), `es_escape_agente` (`:4527`), `_explicit_handoff` (`eko_journeys.py:738`) | El journey lo evalúa solo en `step=done` con `resolved_ack` (`:1539–1547`). |
| "No tenés Internet fijo" | `eko_journeys.py:1186`, `:3678`, `_responder_sin_internet_fijo` (`canal_abonado.py`), `service_not_diagnosticable` (`eko_action_runtime.py:928–939`) | 4 textos; el journey queda abierto tras emitirlo (`step="respond"`). |
| Saldo | `_responder_consulta_saldo` (legacy), `_advance_billing` (journeys), `show_balance` (Runtime) | 3 caminos con textos distintos para la misma pregunta. |
| Ticket | legacy (`conv.ticket_id`), `_advance_ticket` (journeys), `show_ticket` (Runtime) | — |
| Corte | `_talvez_respuesta_outage` (`canal_outage.py`), `portal_connectivity._resolve_incident` (`:409`), proactivo | Con journeys ON el corte lo decide `portal_connectivity` y exige sesión Radius para conocer el NAS. |
| Selección de servicio / login | `bt.extraer_login_en_texto`, `resolve_service_selection` (`eko_service_selection.py:395`), `wifi_bcm.resolver_destino_wifi_bcm`, `_responder_seleccion_cuenta_internet` | 4 mecanismos; `_extract_service_id` (`:157–171`) interpreta "id" dentro de un login (ver §7). |
| Saludo / menú | playbook `general` (`flujos_abonado.py:679`), `texto_menu_consulta` (`:1107`), `frase_soy_eko`, mensaje del journey | El nombre mostrado depende de `BOT_DISPLAY_NAME` ("Eco" vs "Eko"). |

---

## 6. Cobertura de tests

- 155 archivos de test, **1930** tests (último run completo).
- **Tests con `procesar_mensaje_entrante`: 17 archivos. Con journeys ON + `procesar_mensaje_entrante` (e2e): 2, ambos creados en esta sesión**
  (`test_eko_a_intencion_menu.py`, `test_eko_fix1_hold_sin_texto.py`; C y D los reutilizan).
  Antes de esta sesión **no había ningún test multi-turno** que combinara journeys y legacy.
- Tests de journeys: 17 archivos usan `maybe_handle_journey_turn`, con `conv` simulado (`SimpleNamespace`). Prueban cada journey
  aislado, no el orden de precedencia con el legacy.
- Tests con LLM caído (`chat_completion` que lanza): **0** antes de esta sesión.
- Menú/saludo: solo los de esta sesión.
- Existe `qa_bot/` (corpus Botmaker, evaluación `--planta`); no verifiqué si corre en CI ni si ejercita journeys.
- Cierre post-resolución: `test_eko_conversational_closure_2_7e.py`, `test_eko_turn_continuity.py`, `test_resolved_authority.py`.

---

## 7. Hallazgos ya observados en esta sesión (de corridas previas; **no** de esta Parte 1)

Para no perderlos. Cada uno requiere confirmación en la Parte 2.

| # | Hallazgo | Evidencia | Estado |
|---|---|---|---|
| 1 | Silencio por `post_resolution_hold` tras elegir un servicio | `eko_journeys.py:3745`, `:780` | mitigado (`aa50ac9`) |
| 2 | El saludo genérico salía por `ctx.intencion` vieja | `canal_abonado.py:3748` | corregido (`fa565f5`) |
| 3 | Menú con filas idénticas | `eko_service_selection.py:70–90` | corregido (`9ba30d2`) |
| 4 | Repetir "1" repetía "Listo" | `eko_journeys.py` (`_advance_service_catalog`) | corregido (`7d2dda8`) |
| 5 | Un login que contiene "id" (p. ej. `tupaciretacuidaBAI`) se interpreta como `service_id` y se responde "Ese servicio no pertenece a tu cuenta" | `eko_service_selection.py:157–171` (regex `(?:service[_ ]?id|id)\s*[:=]?\s*(...)`); `git bisect`/`git log -S` → `40ea8e2` | **abierto** |
| 6 | Tras un diagnóstico, "quiero hablar con un agente" se contesta "Ya revisé tu conexión en este chat" y el "sí" siguiente "No tengo una acción pendiente" | `eko_journeys.py:1598–1650` (skip idempotente) vs `:1539–1547` (handoff solo con `step=done` + `resolved_ack`); en agosto derivaba con ticket; `git bisect` no concluyente (resultado no monótono: `ffe1088` con criterio estricto, `40ea8e2` con criterio amplio) | **abierto** |
| 7 | "ya se arregló" no cierra ni se reconoce (ni en agosto ni hoy) | detectores §5 | **abierto** |
| 8 | Elegir Sensa/TV responde "Listo: seleccioné «Sensa TV»." sin pregunta siguiente | `eko_journeys.py` (selección) | **abierto** |
| 9 | Journey "sin Internet fijo" queda abierto y captura cualquier texto posterior | `eko_journeys.py:1170–1186` | **abierto** (E) |
| 10 | El problema declarado antes de elegir servicio se pierde | `_advance_service_catalog` (no guarda `texto`) | **abierto** (B) |

Datos crudos sin procesar: un escaneo lineal de los 115 commits entre `0f63286` y `7d2dda8` (escenarios 6, 11 y 12) terminó y
dejó `scan.out` en el scratchpad de la sesión. No lo procesé para esta Parte 1.

---

## 8. Hipótesis (a confirmar en la Parte 2)

1. **Orden de capas, no falta de lógica.** Cada pieza hace lo que dice; el problema es quién responde primero y qué estado
   deja para la siguiente (journeys antes del legacy; legacy hereda `menu_paso`, `intencion`, `cs`).
2. **Estado sin dueño.** Planta, intención y servicio se escriben en varios lugares y se limpian en pocos.
3. **Parches de cierre sobre un journey sin modelo de ciclo de vida.** La serie del 09-29 agregó holds/silencios en vez de definir
   cuándo un journey "termina" y devuelve el turno al legacy.
4. **Ceguera de tests.** Sin e2e con journeys ON, las regresiones entre capas no se detectan; solo las ve un usuario.

## 9. Parte 2 (pendiente de OK)

- Un script con los **14 escenarios**, worktrees en `0f63286` (y opcionalmente `21eb4f8`) y HEAD, LLM y BillTrack mockeados.
- **Sin** suite completa por commit; **con** `timeout` en cada ejecución (≤ 60 s por escenario, ≤ 5 min por tanda).
- Entregable: tabla escenario × commit y, solo donde pasó de bien a mal, `git log -S` acotado al archivo.
- Worktrees temporales borrados al terminar (los de esta sesión ya fueron eliminados; `git worktree list` = 1).

---

# Parte 2: causas raíz de los xfail

**Fecha:** 2026-10-04 · **HEAD:** `17fd0d9` · **Fuente:** `tests/e2e_conv` (80 tests: 32 pasan, **48 xfail estrictos**).
**Método:** cada xfail se ejecutó con `--runxfail`; se tomó la **primera** aserción que falla como causa primaria y la rama
que respondió (`Turn.branch`, sacada de la pila de llamadas y de un espía sobre `maybe_handle_journey_turn`, sin tocar producto).
Cada xfail se asigna a **una** causa primaria; las secundarias se anotan aparte. Toda cuenta incluye los dos canales
(WhatsApp y portal, resultados idénticos salvo ids de ticket).

**Resultado: 12 causas raíz distintas para 48 xfails.** Por capa: 7 de journeys, 3 de legacy, 2 de la unión (orden de capas).

| # | Causa raíz | Dónde decide (archivo:línea) | Capa | xfails (n) | Invariante / regla |
|---|---|---|---|---|---|
| RC-1 | La confirmación de derivación pendiente **atrapa cualquier texto**: si no es sí/no repite «confirmame con un «sí»» | `eko_journeys.py:1965-1975` (`_handle_ticket_confirmation` definida en `:1927`, rama `if not rec`) | journeys | **6**: `test_06`×2, `test_07`×2, `test_h7`×2 | I5; «resuelto» no debe abrir handoff (R1) |
| RC-2 | El «sí» **nunca confirma**: `resolve_user_confirmation` exige `action_state.status == "confirmation_pending"` y el journey solo marca su propio `pending_confirmation` (sonda: `action_state == {}`) | `eko_action_bridge.py:69-116`; prompts en `eko_journeys.py:758-777` y `:1050` | unión journeys↔Runtime | **2**: `test_h6`×2 | I5, I3; R1 (ticket tras confirmar imposible) |
| RC-3 | El journey de servicios **captura texto libre** tras resolver (devuelve el listado) | `eko_journeys.py:747-755` (`_resolved_turn_authorizes_handler`: termina en `_billing_user_act != "balance"` → casi siempre `True`) + lista en `_advance_service_catalog` (def `:3267`, rama de lista `:3477-3530`) | journeys | **2**: `test_e14b`×2 | R2 (links de pago); secundaria en `e16a/b` |
| RC-4 | **Escalación automática** al agotar el playbook: crea el ticket sin confirmar | `canal_abonado.py:7790-7791` (llamada a `_escalar("Playbook … agotado")`; `_escalar` definido en `:7574`) | legacy | **4**: `test_e16a`×2, `test_e16b`×2 | I6; R1 |
| RC-5 | **Saludo genérico** por el playbook `general` cuando el estado es `aviso_deuda`/`general` y el texto no se entiende | `canal_abonado.py:7762-7767` (`_preguntar_o_recordar`) y `:7878-7883` (`_preguntar`); texto en `flujos_abonado.py:679-683` | legacy | **10**: `test_e14a`×2, `e14c`×2, `e14d`×2, `test_13[journeys_off]`×2, `test_14a[journeys_off]`×2 | I2 |
| RC-6 | El **aviso de saldo bloquea** («¿Querés que te ayude primero a pagar…?»); hay 3 sitios que lo ofrecen | `canal_abonado.py:813-822`, `:3802-3807`, `:6645-6649` | legacy | **4**: `test_e13`×2, `test_14b[journeys_off]`×2 | R2 |
| RC-7 | Con journeys ON **no hay aviso de saldo**: el journey responde antes de la rama de deuda | orden: `canal_abonado.py:5332` (journeys) antes de `:6645` (aviso) | unión | **6**: `test_13/14a/14b[journeys_on]`×2 c/u | R2 |
| RC-8 | El **corte masivo** se evalúa después de journeys y el diagnóstico legacy del journey no lo mira | `canal_abonado.py:5332` vs `:5481` (`_talvez_respuesta_outage`); `canal_pppoe._talvez_mensaje_pppoe` | unión | **2**: `test_09`×2 | (regla de producto: avisar el corte) |
| RC-9 | **Selección = callejón**: «Listo: seleccioné…» cierra el journey sin siguiente paso y el problema declarado no se guarda | `eko_journeys.py:3411` (rama de éxito, «Listo: seleccioné…») y `:3450-3475` (rama ambigua, no guarda `texto`) | journeys | **6**: `test_10`×2, `test_h8`×2, `test_h10`×2 | R1 |
| RC-10 | `_extract_service_id` toma «id» **dentro de un login** (`tupaciretacuidaBAI` → `aBAI`) → «no pertenece a tu cuenta» | `eko_service_selection.py:157-171` | journeys (2.2B) | **2**: `test_h5`×2 | I4 |
| RC-11 | La selección por texto solo reconoce logins **`INT*`**; «el de tupaciretaBAI» no se resuelve y vuelve el menú | `eko_service_selection.py:174-179` (`_extract_login`) | journeys (2.2B/2.5D-2) | **2**: `test_12`×2 | I4 |
| RC-12 | El journey **«sin Internet fijo» queda abierto** (`step="respond"`) y responde igual a cualquier texto, incluido «hola» | `eko_journeys.py:1170-1186` | journeys | **2**: `test_h9`×2 | I5 |
| | **Total** | | | **48** | |

**Suma de control:** 6+2+2+4+10+4+6+2+6+2+2+2 = 48.

**Causas secundarias (no cambian la cuenta):** RC-1 también corta el turno 2 de `test_13/14b[journeys_on]`; RC-3 también aparece en
`e16a/b` (los textos libres caen al listado de servicios).

**Lectura transversal.** Las 12 causas se reducen a cuatro patrones:
1. **Un journey no sabe soltar el turno** (RC-1, RC-2, RC-3, RC-12): mantiene estado vivo o autoriza cualquier texto.
2. **Dos dueños de la misma decisión** (RC-5, RC-6, RC-7, RC-8): legacy y journeys deciden lo mismo en distinto orden.
3. **Escalación sin confirmación** (RC-4): el legacy crea tickets por agotamiento.
4. **Selección de servicio frágil** (RC-9, RC-10, RC-11): regex y mensajes de la 2.2B/2.5.


## Deuda H19-raíz (abierta)

H19 (paso Wi-Fi/router re-emitido tras responder la potencia) se cerró con un fix **acotado** en `_avanzar_fallback_por_respuesta`
(`canal_diagnostico_ia.py`, helper `_saltar_paso_ya_emitido`), común al LLM caído y al LLM vivo. Regla: sin `pending_bot`, con el último mensaje del
bot que no es la pregunta de ningún paso (venía de una respuesta lateral) y un paso que ya salió en los últimos 6 turnos (I10), se avanza al siguiente.
Excluye pasos de derivación, repreguntas (el último mensaje del bot era el paso) y no muta `ctx`.

**Corrección de la Fase 1:** el perfil `primer_paso` no repite por el `except` de `diagnosticar_turno` sino por el camino de **LLM vivo** (devuelve el
primer paso sin cubrir con `paso_cubierto` vacío). Un kwarg en `_fallback_ask` solo cubría LLM caído y además rompía rc4/rc5/rc13/h12e, que re-emiten a propósito.

**Raíz sin tocar:** `_responder_potencia_cualitativa` (`canal_abonado.py`, rama sin dato) hace `stamp_bot_question(step_id="derivar_oferta_agotado")`
y **pisa el `pending_bot`** del paso diagnóstico en curso (`reinicio_lento`). Al turno siguiente el paso queda «preguntado y sin cubrir» sin dueño.
Un fix de raíz implica que una consulta lateral (potencia, saldo…) conserve/restaure el `pending_bot` del diagnóstico; toca estado conversacional (2.5).
**Deuda para después de consolidar `ctx.intencion`**; requiere propuesta explícita.
