# EKO-CTX-1 — Contexto del abonado en el prompt N1: servicio en foco

**Estado:** IMPLEMENTADO 2026-10-02 (2.8A + CTX-1 commiteados; G4/G5 siguen como CTX-2/CTX-3).
**Fecha:** 2026-10-02
**Origen:** auditoría de qué datos del abonado llegan realmente al prompt N1, por canal.
**No reabre:** 2.5 FROZEN, 2.6 CLOSED, 2.7D CLOSED. Solo *lee* `selected_service_ref`; no agrega campos a `ctx`.

---

## 1. Qué se auditó (evidencia en el repo)

Camino del contexto al LLM, común a portal web, app y WhatsApp (todos terminan en `canal_abonado.procesar_mensaje_entrante`):

```
canal_diagnostico_ia.py:481-546
  extras_ctx  ← ctx (pppoe_*, uisp_*, bcm_*, tecnologia_acceso) + canal + links OV
  build_contexto_abonado(abonado, org_id, extras, db)        eco_voice.py:487
    └ build_eko_facts(abonado, db)                           eko_context.py:81
        customer · account · services · billing · tickets · ov
    └ format_n1_contexto(facts, extras, dni_enmascarado)     eko_context.py:375
```

Qué datos del abonado SÍ llegan al LLM: nombre, DNI enmascarado, línea, nro de asociado, estado comercial, plan, `servicio_agregado`, catálogo de servicios (tipo/label/activo), saldo (snapshot), tickets (id[:12], estado, categoría), links OV, `canal`, observaciones técnicas del último diagnóstico.

## 2. Gaps encontrados

| # | Gap | Evidencia | Impacto |
|---|---|---|---|
| G1 | **El prompt no sabe qué servicio eligió el abonado.** Con multi-cuenta ve el catálogo completo, pero ningún campo dice cuál está en foco. | `eko_context.py` no referencia `selected_service_ref`; `canal_diagnostico_ia.py` tampoco lo pasa en `extras_ctx`. | El LLM puede hablar de otro servicio o preguntar cuál de nuevo. |
| G2 | **Observaciones técnicas pueden ser de otro login.** `pppoe_*`/`uisp_*`/`bcm_*` se copian de `ctx` sin comprobar que correspondan al servicio en foco. | `canal_diagnostico_ia.py:484-506` copia sin validar login. | Con 2+ servicios y cambio de login, el LLM razona con la planta del servicio anterior. |
| G3 | **Tickets sin fecha en el prompt.** `ticket_fact_item` ya trae `created_at`/`updated_at`, pero `format_n1_contexto` solo imprime `id[:12]:estado/categoría`. | `abonado_tickets.py:111-121` vs `eko_context.py:504-511`. | Eko no puede decir "tu reclamo del martes sigue abierto" ni distinguir viejo de reciente. |
| G4 | **Placeholders muertos.** `cortes_zona` y `pago_qr_reciente` nunca se completan en ningún lado; siempre salen `(sin dato — integrar …)`. | grep en `app/`: solo definición y render. | Tokens de ruido e invitación a decir "no tengo dato de cortes" aunque haya un outage en `ctx` (`outage_id`, `outage_individual`). |
| G5 | **Paridad de canales: NO verificada.** Portal/app abren la conversación con `ctx.identificado/dni/client_number` (`portal.py:288-299`). WhatsApp identifica por teléfono (`phone_candidates`). El prompt solo recibe `canal` como diferencia. | No se leyó el camino de identificación por WA dentro de `canal_abonado.py`. | Pendiente de auditar; no se afirma que haya diferencia. |

Dependencia con 2.8A: el canal por texto escribe `login_seleccionado` pero no `selected_service_ref` (diagnóstico previo, `_sincronizar_login_desde_mensaje`). **G1 solo rinde si 2.8A está cerrado**; si no, "servicio en foco" salvo en journeys quedaría vacío.

## 3. Tarea propuesta (UNA)

**EKO-CTX-1 — Servicio en foco en CONTEXTO_ABONADO.** Cubre G1, G2 y G3. G4 y G5 quedan como tareas aparte.

### Cambio

1. En `canal_diagnostico_ia.py`, donde se arma `extras_ctx`: leer `get_selected_ref(ctx)` (solo lectura) y pasar a `extras_ctx` los datos del servicio en foco (login, tipo, label, `service_id`).
2. En `eko_context.format_n1_contexto`: nueva sección `## SERVICE IN FOCUS` con esos datos.
   - Con ref: `servicio_en_foco: <label> (<login>)`.
   - Sin ref y catálogo con más de un servicio de Internet: `servicio_en_foco: (sin seleccionar — preguntar cuál antes de diagnosticar)`.
   - Sin ref y un solo servicio: `servicio_en_foco: único servicio` (sin inventar login).
3. Guarda de frescura (G2): si el login de `pppoe_login`/`uisp_login` en `ctx` no coincide con el del ref, **no** copiar `pppoe_*`/`uisp_*`/`bcm_*` a `extras_ctx`. Sin fallback, sin adivinar.
4. Tickets (G3): en el render, agregar `actualizado: <fecha>` por ítem usando `updated_at` que ya está en `ticket_fact_item`. Sin cambiar el reader ni el SQL.

### Invariantes

- `selected_service_ref` sigue siendo la única autoridad. Se lee con `get_selected_ref`; no se escribe, no se infiere desde texto, no se agrega lectura de `login_seleccionado`.
- Sin campos nuevos en `ctx`. Sin cambios en Runtime, Policy, `ACTION_RUNTIME_ACTIONS`, journeys, 2.5/2.6/2.7.
- El contexto es insumo de lectura para el LLM: LLM content ≠ authority (CASI). Ninguna mutación nueva.
- Planta manda el turno: `tests/test_guardrails_planta.py` debe seguir en verde sin cambios.
- No ampliar stack; sin nuevas llamadas a BCM/UISP/Radius (el contexto sigue sin probes).

### Fuera de alcance

- G4 (cortes_zona / `pago_qr_reciente`): tarea siguiente. Recomendación: quitar `pago_qr_reciente` (no hay fuente) y alimentar `cortes_zona` desde `ctx` (`outage_id`, `outage_individual`) sin consulta nueva.
- G5 (paridad WA vs portal vs app): auditoría aparte sobre la identificación en `canal_abonado.py`.
- Vencimiento, historial de pagos, cabecera de factura en Home (2.8).
- `ticket_customer_note`, CSV de producción, `.env`.

### Archivos probables

- `app/services/canal_diagnostico_ia.py` (armado de `extras_ctx`)
- `app/services/eko_context.py` (render `SERVICE IN FOCUS`, fecha de ticket)
- `tests/` módulo nuevo; no reescribir suites existentes.

## 4. Criterios de aceptación

1. Abonado con 2+ logins y ref aplicado → el contexto incluye `## SERVICE IN FOCUS` con el login y label del ref.
2. Abonado con 2+ logins sin ref → `servicio_en_foco: (sin seleccionar …)` y no se copian `pppoe_*`/`uisp_*`/`bcm_*` del `ctx`.
3. `ctx` con `pppoe_login` distinto al login del ref → esas claves no llegan a `extras_ctx`.
4. Abonado con un solo servicio → comportamiento actual, más la línea `servicio_en_foco: único servicio`.
5. Tickets en el contexto muestran fecha de actualización; sin tickets, el texto actual no cambia.
6. Invitado (sin abonado) → render idéntico al actual.
7. `get_selected_ref` es lo único que se lee; verificado por test que `ctx` no cambia tras armar el contexto.

## 5. Sensores (cierre)

- `.venv/bin/python -m pytest` sobre los módulos nuevos más los tests existentes de `eko_context`, `tests/test_guardrails_planta.py`, `tests/test_multi_cuenta_senal.py` y `tests/test_eko_incident_cx_2_7d.py`.
- `.venv/bin/ruff check` sobre los archivos tocados.
- Sin cierre sin salida de comando pass/fail.

## 6. Orden recomendado

1. **2.8A** (login nombrado → `selected_service_ref`) — prerequisito de G1.
2. **EKO-CTX-1** (este brief).
3. **EKO-CTX-2** — G4 (cortes_zona desde `ctx`, quitar `pago_qr_reciente`).
4. **EKO-CTX-3** — auditoría de paridad por canal (G5).
