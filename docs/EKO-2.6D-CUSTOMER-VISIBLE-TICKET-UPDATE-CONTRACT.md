# EKO 2.6D — Customer-Visible Ticket Update Contract & Authority Design

**Status:** DESIGN / CONTRACT — READ ONLY  
**Date:** 2026-09-23  
**Code changes:** NONE  
**Upstream:** `docs/EKO-2.6C-TICKET-UPDATE-CUSTOMER-VISIBLE-READINESS.md` → READY AFTER SMALL GAP  
**Invariants:** 2.3G-B reusable · 2.5 FROZEN · CASI · 2.6A/B untouched · no migration · no push enablement in this phase  

---

## 1. Executive Summary

**Pregunta de diseño:** ¿qué significa, de forma inequívoca, “N1 / el sistema actualizó mi ticket” para el cliente?

**Respuesta contractual:**

> Un **acto customer-visible** es únicamente la emisión explícita de un `TicketEvent` con  
> `tipo=nota`, `visible_cliente=Sí`, y `detalle` = mensaje customer-safe autorizado.  
> Ese acto puede mapear a `ticket.updated` + push opcional.  
> Todo lo demás (evidencia N1, campos admin, reasignación, notas internas, SLA fields) es **INTERNAL** o **NON_MATERIAL** y **no** debe producir push ni timeline customer-unsafe.

| Gap 2.6C | Resolución de contrato |
|---|---|
| G-01 | Acto explícito `ticket_customer_note` (o equivalente) emite `nota` visible; `update_ticket` N1 permanece evidencia interna |
| G-02 | Auto-eventos de `repo.update_ticket` → `visible_cliente=No` por defecto; tipología allowlist para timeline/push |
| G-03 | Materiality determinística: solo actos MATERIAL disparan `ticket.updated` / push |

**Readiness:** `CONTRACT READY — IMPLEMENTATION NEXT`

---

## 2. Design Alternatives

### 4.x — Semántica customer-visible

| Opción | Descripción | Autoridad | Leak | Portal | Mobile | Push | Dedup | Materiality | Compat | Complejidad | 2.5/CASI |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **A** | Solo `nota` explícita `visible_cliente=Sí` | Writer explícito (agente POST / Runtime acto) | Bajo si writers restringidos | Ya lista `nota` | `event=updated` | Ya mapea | Por Event.id | Clara (acto = material) | Alta | Baja | Neutro |
| **B** | Nuevo `customer_message` (tipo/campo) | Nueva semántica | Bajo | Cambio proyección | Puede requerir allowlist | Nuevo map o alias | Igual | Clara | Media (nuevo tipo) | Media | Neutro si no LLM |
| **C** | Mantener `actualizacion` + contrato estricto | Depende de campos/flags | Medio si falla allowlist | Históricos `actualizacion` Sí | OK | Spam histórico risk | Por Event.id | Hay que filtrar campos | Alta en código | Media–Alta | Neutro |
| **D** | Evidencia N1 como visible | Runtime append | Alto (texto técnico) | Expondría evidencia | N/A sin evento | No hoy | Débil | Confusa | Baja | Baja | Mal UX |

**Evidencia código:**

- `map_ticket_event_type`: `nota` → `ticket.updated`; `actualizacion` → `updated`/`closed` (`eko_ticket_proactive.py`).
- Agente ya tiene `POST .../events` con `interno` → `nota`/`nota_interna` (`tickets.py`).
- N1 `_exec_update_ticket` solo `_append_evidencia_ticket` — sin evento (`eko_action_runtime.py`).

**Recomendación única:** **Opción A** como vehículo del acto customer-visible, **más** endurecimiento tipo **C solo para writers admin** (auto-`actualizacion` deja de ser customer-visible por defecto).  
No adoptar B en v1 (taxonomía nueva innecesaria). No adoptar D.

---

### 6.x — Separación mensaje vs operativo

| Modelo | Evita | No evita | DB | Portal | Mobile | Compat | Migración |
|---|---|---|---|---|---|---|---|
| **1** Storage actual + writers restringidos | Dual-use futuro si writers cumplen | Históricos leaky | 0 | Filtro writers + allowlist tipo | 0 | Alta | No |
| **2** `detalle_interno` + `mensaje_cliente` | Dual-use estructural | Complejidad | Migration | Cambio shape | 0 | Baja corto plazo | **Sí — evitar** |
| **3** Proyección determinística customer-safe | Leak en GET aunque flag Sí | Writer sigue guardando basura | 0 | Capa proyección | 0 | Alta | No |

**Recomendación:** **Modelo 1 + proyección Modelo 3** (sin migration):

- Writers del acto customer-visible solo escriben mensaje allowlisted en `detalle`.
- Portal GET aplica proyección: si `tipo` ∉ allowlist customer **o** `visible_cliente≠Sí` → omitir; opcional sanitizar históricos `actualizacion` (ver §15).

---

## 3. Customer-Visible Act

### Nombre canónico (implementación futura)

```text
ACT = ticket_customer_note
```

### Definición inequívoca

| Campo | Valor |
|---|---|
| **Nombre** | `ticket_customer_note` |
| **Actor** | `agente` (consola) **o** `abonado` (N1 Runtime trusted) **o** `sistema` (solo si contrato futuro explícito; **fuera de v1**) |
| **Input** | `ticket_id` + `mensaje` (string no vacío, max length fijo p.ej. 800) |
| **Authority** | Conversation Motor + Policy + Runtime **o** API agente autenticada — **nunca** LLM directo |
| **Ownership** | `ticket_pertenece_abonado` antes de escribir (N1); org/RBAC agente (consola) |
| **Event** | `TicketEvent(tipo="nota", visible_cliente="Sí", titulo=fijo, detalle=mensaje)` |
| **Message** | Solo el `mensaje` input; **prohibido** concatenar resolución/SLA/proveedor/asignación |
| **Visibility** | Explícita `Sí` en el acto; no default implícito desde update de campos |
| **Materiality** | `MATERIAL` (ver §7) |
| **Push** | Opcional según actor (ver §13) → canónico `ticket.updated` / mobile `event=updated` |
| **Portal** | Aparece en timeline vía proyección allowlist |
| **Idempotency** | Ver §13 |

### Qué **no** es este acto

| Concepto (2.6C A–H) | Clasificación contrato |
|---|---|
| A. Cambio interno / nota interna | INTERNAL |
| B. Evidencia técnica N1 (`update_ticket`) | INTERNAL |
| C. Cambio administrativo de campos | INTERNAL (evento audit opcional `visible_cliente=No`) |
| D. Mensaje explícito al cliente | **= ACT** |
| E. Cambio de estado (no cierre) | NON_MATERIAL para push v1; timeline solo si producto decide después |
| F. Cierre | Ya `ticket.closed` — fuera de este ACT |
| G. SLA | Ya `ticket.sla_breached` — fuera |
| H. Reasignación | INTERNAL (+ G-04) |

---

## 4. Authority Model

```text
LLM
  → ActionProposal / content only
  → NO visibility, NO TicketEvent, NO push, NO materiality

Trusted path
  → Policy ALLOW
  → Runtime / Agent API
  → ownership / RBAC
  → write TicketEvent (ACT) OR internal evidence/fields
```

| Acción | Quién autoriza | LLM |
|---|---|---|
| `visible_cliente=Sí` | Solo writers del ACT o `POST .../events` con `interno=false` | Nunca |
| Append evidencia | Runtime `update_ticket` | Solo vía proposal→policy→runtime |
| Mutar campos Ticket | API agente `update_ticket` | No |
| Emitir push | Detector post-commit + policy + ownership + claim | No |

---

## 5. Visibility Contract

### Regla determinística (v1)

```text
CUSTOMER_TIMELINE_ELIGIBLE :=
  visible_cliente ∈ {Sí, Si, yes, true, 1}
  AND tipo ∈ CUSTOMER_EVENT_ALLOWLIST

CUSTOMER_PUSH_ELIGIBLE :=
  CUSTOMER_TIMELINE_ELIGIBLE
  AND tipo ∉ _INTERNAL_TIPOS          # denylist existente
  AND map_ticket_event_type ≠ None
  AND materiality = MATERIAL
  AND push_policy(actor) = ALLOW
```

### Allowlist customer (propuesta v1)

```text
CUSTOMER_EVENT_ALLOWLIST = {
  creacion,   # ya en timeline/create push
  nota,       # ACT
  sla_breach, # 2.6A
  actualizacion  # SOLO si estado=Cerrado → closed; ver abajo
}
```

Para `actualizacion` en v1 implementación:

- Si `estado=Cerrado` → elegible como hoy (`ticket.closed`).
- Si `estado≠Cerrado` → **dejar de emitir** con `visible_cliente=Sí` desde `repo.update_ticket` (G-02). Eventos nuevos admin: `visible_cliente=No`.

### Quién puede setear `visible_cliente=Sí`

| Writer | Permitido Sí | Condición |
|---|---|---|
| ACT `ticket_customer_note` | Sí | Siempre en ese acto |
| `POST /events` `interno=false` | Sí | Agente consciente (mismo shape que ACT) |
| `repo.update_ticket` auto-event | **No** (default **No**) | Excepto cierre→usar path closed / o evento cierre dedicado |
| `_append_evidencia_ticket` | N/A | No crea evento |
| SLA emit | Sí | Solo `sla_breach` (2.6A, no tocar) |
| LLM | No | — |

**Combinación:** allowlist + denylist + flag explícito (las tres). Flag solo no basta (G-02/G-04).

---

## 6. Message Contract

```text
customer_safe_message :=
  trim(input.mensaje)
  length ∈ [1, MAX]
  charset printable
  NO auto-append de campos Ticket
```

| Superficie | Contenido permitido |
|---|---|
| `TicketEvent.detalle` (ACT) | Solo `customer_safe_message` |
| `TicketEvent.titulo` (ACT) | Constante fija p.ej. `"Actualización"` / `"Nota"` |
| Push title/body | Copy fija `_TICKET_COPY["ticket.updated"]` — **nunca** `detalle` crudo |
| Portal timeline | `titulo` + `detalle` del evento si allowlist; nunca campos Ticket internos |

**Prohibido en mensaje customer-visible:** SLA, proveedor, routing, motivo escalamiento, resolución técnica, asignación, IDs internos de ops, evidencia concatenada.

---

## 7. Materiality Contract

Función determinística (pseudo):

```text
materiality(actor, tipo, changed_fields, visible_cliente) →
  MATERIAL | NON_MATERIAL | INTERNAL
```

| Caso | Clase | TicketEvent | `ticket.updated` | Push | Portal timeline |
|---|---|---|---|---|---|
| ACT `nota` visible (agente→cliente) | MATERIAL | Sí | Sí | **Sí** (si ownership) | Sí |
| ACT `nota` visible (abonado N1 self-note) | MATERIAL | Sí | Sí | **No** (SUPPRESS self-notify) | Sí |
| Evidencia N1 `update_ticket` | INTERNAL | No | No | No | No |
| `nota_interna` | INTERNAL | Sí | No | No | No |
| Auto update campos (nivel, proveedor, SLA field, resolución…) | INTERNAL | Opcional audit `visible=No` | No | No | No |
| Reasignación / claim | INTERNAL | Sí tipo `reasignacion` `visible=No` | No | No | No |
| Cierre | MATERIAL (otro evento) | `actualizacion`+Cerrado o equivalente | → `ticket.closed` | Sí (existente) | Sí |
| SLA breach | MATERIAL (2.6A) | `sla_breach` | → `sla_breached` | Sí | Sí |
| Cambio estado Abierto↔En Revisión sin mensaje | NON_MATERIAL | Preferible no / o visible=No | No | No | No |

**LLM no clasifica materiality.**

---

## 8. Event Contract

### Reutilizar (mínimo v1)

| Canónico | Origen TicketEvent | Uso |
|---|---|---|
| `ticket.created` | `creacion` | Intact |
| `ticket.updated` | **`nota` customer-visible (ACT)** | Único vehículo “hubo novedad para el cliente” en v1 |
| `ticket.closed` | `actualizacion` + Cerrado | Intact |
| `ticket.sla_breached` | `sla_breach` | Intact (2.6A) |

### No introducir en v1

- `ticket.customer_message` (proactivo)
- `ticket.status_changed`
- `ticket.assigned`
- `ticket.resolved`

**Motivo:** mobile y contract 2.3G-B ya cubren `updated`; taxonomía extra no cierra G-01..G-03.

### Cambio semántico crítico

```text
ANTES:  actualizacion (cualquier campo) → ticket.updated + push
DESPUÉS: nota (ACT)                   → ticket.updated + push (si material+policy)
         actualizacion admin           → visible_cliente=No → no push / no timeline
```

---

## 9. N1 Runtime Contract

### Alternativas

| Modelo | Idea | Autoridad | Seguridad | Idempotencia | CASI | UX | Audit |
|---|---|---|---|---|---|---|---|
| **A** | `update_ticket` muta Ticket; acto aparte `ticket_customer_note` | Dos actos explícitos | Alta | Por acto | Excelente | Dos pasos si ambos | Clara |
| **B** | `update_ticket(customer_visible, customer_message)` | Un acto con flags | Media (LLM puede setear flags en proposal) | Una | OK si Policy strippea flags no trusted | Simple | Media |
| **C** | `update_ticket` = solo evidencia; otro acto genera visible | Igual A | Alta | Por acto | Excelente | Explícito | Clara |
| **D** | Emitir `nota` automáticamente desde toda evidencia | Implícito | Baja (leak) | Débil | Confuso | “Mágica” | Opaca |

**A y C son equivalentes en espíritu.** Se recomienda **Modelo C / A**:

```text
update_ticket
  = INTERNAL evidence append only (comportamiento actual + documentado)
  = NUNCA setea visible_cliente ni emite nota

ticket_customer_note   # nuevo action name en Runtime O wrapper de servicio compartido
  = ownership
  = add_ticket_event(tipo=nota, visible_cliente=Sí, detalle=mensaje)
  = materiality MATERIAL
  = push: SUPPRESS si actor=abonado (self); ALLOW si actor=agente
```

**Policy/Motor:** LLM puede *proponer* `ticket_customer_note` con texto; Policy debe exigir confirmación trusted / source≠raw LLM write; Runtime valida ownership y length. Visibilidad no la decide el LLM: el action name implica `Sí`.

**Consola agente:** `POST /events` con `interno=false` **es** el mismo ACT (mismo shape Event). Implementación debe compartir helper `emit_ticket_customer_note(...)`.

---

## 10. Ownership

Sin cambios de regla:

```text
Ticket → ticket_pertenece_abonado → conv/línea → DNI → PortalDevice → Expo
```

| Regla | |
|---|---|
| Foreign ticket | DENY / 0 push / portal 404 |
| Unresolved owner | 0 push; evento puede existir |
| No ownership por texto/LLM/label/servicio inferido | Obligatorio |

Customer-visible update **no** puede cruzar cuentas: mismo gate que create/show ticket.

---

## 11. Portal Projection

`GET /portal/tickets/{id}` (contrato futuro, sin cambiar ahora):

```text
eventos_expuestos = events where
  visible_cliente == "Sí"
  AND tipo ∈ CUSTOMER_EVENT_ALLOWLIST
  AND NOT (tipo == "actualizacion" AND estado != "Cerrado")  # post-hardening; históricos ver §15
```

| Campo API | Exponer |
|---|---|
| `id`, `titulo`, `created_at`, `estado` | Sí |
| `detalle` | Sí **solo** si evento allowlisted (ACT/nota/cierre/sla) |
| `tipo`, `actor` | Opcional; si se expone `actor`, valores genéricos (`sistema`/`agente`/`vos`) — **no** email interno en v1 salvo ya expuesto |
| SLA / proveedor / routing / resolución / asignación | **Nunca** vía eventos ni ticket projection actual |

Ticket projection actual (`id, estado, categoria, origen, timestamps, conversacion_id`) se mantiene.

---

## 12. Push Contract

Reutilizar:

```json
{ "tipo": "ticket", "ticket_id": "<id>", "event": "updated" }
```

| Regla | |
|---|---|
| Title/body | Fijos `_TICKET_COPY["ticket.updated"]` |
| Incluir `detalle` / mensaje cliente en data Expo | **No** |
| Incluir estado en data | **No** (GET es autoridad) |
| Self-note N1 | **No push** (`SUPPRESS` / skip deliver) |
| Agente `nota` visible | Push ALLOW si ownership |
| Admin field update | No push (post G-02) |

Push ≠ SoT. Mobile sin cambios en esta fase ni requisitos nuevos de allowlist (`updated` ya existe).

---

## 13. Idempotency

### Capas

| Capa | Clave | Efecto |
|---|---|---|
| Push | `TicketEvent.id` + `push_claimed_at` | AT-MOST-ONCE Expo attempt (existente) |
| Negocio ACT | `ticket_id` + `tipo=nota` + hash normalizado(`detalle`) | Si ya existe nota idéntica reciente/any → **no** segundo Event (v1: any equal detalle en ticket) |
| Evidencia N1 | `bloque in evidencia` (existente) | No re-append |
| Action Runtime | `idempotency=PROTECTED` en spec | Policy class; no sustituye Event key |

### Escenarios

| Escenario | Resultado esperado |
|---|---|
| Retry Runtime mismo mensaje | 0 segundo Event / 0 segundo push |
| Retry HTTP agente misma nota | Idempotente vía hash detalle |
| Doble click | Idempotente |
| Dos mensajes distintos | Dos Events / dos pushes (agente) — correcto |
| Mismo ACT + cambio estado en una op agente | **Un** Event `nota` si solo hay mensaje; cierre aparte si `estado=Cerrado` — **no** doble `updated`+`updated`. Si una sola operación agente incluye mensaje+cierre: preferir **un** evento de cierre customer-visible **o** nota+closed con **un** push (`closed` gana). Regla v1: **una operación HTTP = un customer push máximo** (closed > updated > none). |

---

## 14. Dedup / Anti-Spam (síntesis)

```text
1. Crear TicketEvent  ↔ solo ACT / create / close / sla / audit interno
2. Material          ↔ §7
3. ticket.updated    ↔ solo nota MATERIAL (ACT)
4. Push attempt      ↔ MATERIAL + push_policy + ownership + claim
5. Doble push        ↔ claim por Event.id; max 1 customer push por request agente
```

`customer message + estado cambiado` en una sola operación → ver §13 (closed wins).

---

## 15. Backward Compatibility

| Tipo histórico | Comportamiento post-contrato (sin migrar filas) |
|---|---|
| `nota` + Sí | Sigue timeline + push elegible |
| `nota_interna` | Invisible |
| `actualizacion` + Sí (histórico) | **Deuda:** pueden seguir visibles en portal hasta proyección endurecida; **no backfill**. Proyección v1 puede: (a) dejarlos, o (b) ocultar `actualizacion` no-Cerrado en portal going-forward filter even if flag Sí |
| `reasignacion` + Sí | G-04 |
| `cierre_masivo` | Denylist / No |
| `sla_breach` | Intact |

**Recomendación proyección v1:** ocultar en portal `tipo=actualizacion` con `estado≠Cerrado` aunque `visible_cliente=Sí` (filtro de lectura, no UPDATE histórico). Así se mitiga leak sin migration.

Nuevos writes admin: `visible_cliente=No`.

---

## 16. G-04 Decision

> `reasignacion` puede listarse en portal si flag Sí aunque push denylist.

**Decisión: C — entra en el contrato 2.6D.**

Reglas:

1. Writers de reasignación/claim → `visible_cliente=No`.
2. Portal proyección → excluir `tipo=reasignacion` (alineado a denylist push).
3. No migration de filas viejas; filtro de lectura cubre histórico.

Clasificación residual: no BLOCKER; deuda operativa cubierta por proyección.

---

## 17. Test Contract (fase implementación — no crear ahora)

### Customer visible

- [ ] N1/agente `ticket_customer_note` → Event `nota` Sí → portal visible
- [ ] N1 `update_ticket` evidencia → sin Event / invisible
- [ ] `nota_interna` → invisible
- [ ] `repo.update_ticket` campos ops → Event `visible=No` / no portal / no push

### Materiality

- [ ] MATERIAL agente nota → push `updated`
- [ ] N1 self-note → Event sí, push no
- [ ] NON_MATERIAL / INTERNAL → no push
- [ ] N admin updates → no customer spam

### Ownership

- [ ] own → allow
- [ ] foreign → deny / 404 / 0 push
- [ ] unresolved → 0 push

### CASI

- [ ] LLM proposal no escribe Event directo
- [ ] LLM no setea visibility
- [ ] LLM no dispara push

### Portal

- [ ] customer message visible
- [ ] internal detail / actualizacion admin invisible bajo proyección
- [ ] foreign 404

### Dedup

- [ ] retry mismo mensaje → no segundo Event / no segundo push
- [ ] claim ya tomado → already_claimed

### Regresión

- [ ] `ticket.created` / `closed` / `sla_breached` / outage / 2.5 / CASI

---

## 18. Implementation Plan (fase posterior — no ejecutar aquí)

1. Helper compartido `emit_ticket_customer_note(db, org, ticket_id, mensaje, actor, *, notify: bool)`.
2. Runtime: registrar action `ticket_customer_note`; documentar `update_ticket` = evidence-only.
3. `repo.update_ticket`: auto-event `visible_cliente="No"`; tipo `reasignacion` también `No`.
4. Portal proyección: allowlist + ocultar `actualizacion` no-Cerrado + ocultar `reasignacion`.
5. Detector/push: self-note suppress; copy fija; sin `detalle` en Expo data.
6. Idempotencia hash mensaje en emit helper.
7. Tests del §17 + regresiones 2.3G-B / 2.6A / portal / CASI / 2.5.
8. Doc 2.6E implementation report (futuro).

**Fuera de alcance v1:** migration columnas, nuevo event canónico, mobile changes, SLA, 2.5, Commercial, Billing.

---

## 19. Final Design Decision

```text
CUSTOMER-VISIBLE ACT = ticket_customer_note

Storage:           TicketEvent.tipo=nota, visible_cliente=Sí, detalle=mensaje safe
Canonical push:    ticket.updated / mobile event=updated
N1 update_ticket:  INTERNAL evidence only (no Event)
Admin auto-update: visible_cliente=No (G-02)
Materiality:       deterministic table §7 (no LLM)
Self-note push:    SUPPRESS
Agent note push:   ALLOW + ownership + claim
Portal:            allowlist + hide unsafe históricos via read filter (no backfill)
G-04:              visible=No on write + portal exclude reasignacion
Idempotency:       Event.id claim + mensaje hash pre-insert
Authority:         Policy + Runtime / Agent API — LLM ≠ visibility/push/event writer
```

Este bloque es la especificación ejecutable para la siguiente fase.

---

## 20. Implementation Readiness

| Criterio | Estado |
|---|---|
| G-01 | Resuelto en contrato (acto explícito) |
| G-02 | Resuelto (default No + proyección) |
| G-03 | Resuelto (materiality table) |
| Autoridad / mensaje / event / ownership / dedup / portal / push | Resueltos |
| Open decisions bloqueantes | **Ninguna** |

```text
CONTRACT READY — IMPLEMENTATION NEXT
```

---

## 21. Validation meta

| Item | Value |
|---|---|
| Files inspected | `eko_ticket_proactive.py`, `eko_action_runtime.py`, `repository.update_ticket`, `tickets.py` events, `models.TicketEvent`, `EKO-2.6C-*.md` |
| Tests executed | Ninguno nuevo; diseño grounded en evidencia 2.6C + re-lectura código |
| Code changes | **NONE** |
| Docs created | `docs/EKO-2.6D-CUSTOMER-VISIBLE-TICKET-UPDATE-CONTRACT.md` |
| Docs 2.6A/B/C | No modificados |

---

**FINAL:** `EKO 2.6D — CONTRACT READY — IMPLEMENTATION NEXT`
