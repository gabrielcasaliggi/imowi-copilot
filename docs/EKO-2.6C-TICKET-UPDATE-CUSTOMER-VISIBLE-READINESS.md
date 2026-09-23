# EKO 2.6C — Ticket Update N1 / Customer-Visible Event Readiness Discovery

**Status:** DISCOVERY COMPLETE — READ ONLY  
**Date:** 2026-09-23  
**Code changes:** NONE  
**Depends on (invariants):** 2.3 / 2.3G-B / 2.5 FROZEN / 2.6A CLOSED / 2.6B SMOKE PENDING  
**Does not modify:** CASI, 2.5, Billing, Commercial, SLA pipeline, 2.6A/B code or docs  

---

## 1. Executive Summary

La pregunta:

> ¿Puede Eko soportar `update_ticket` N1 + evento customer-visible + push opcional sin romper CASI, ownership, dedup, 2.5 ni garantías de tickets?

**Respuesta corta:** la **infraestructura** proactiva (TicketEvent → detector → policy → ownership → claim → Expo → mobile → GET portal) **ya existe** y es reutilizable. La **capacidad de producto** “actualización N1 visible y notificable” **no está lista**: el path N1 de `update_ticket` **no emite** `TicketEvent`, y el path de consola que sí emite `ticket.updated` es **demasiado amplio** (casi cualquier cambio de campo → evento `visible_cliente=Sí` + push) sin materialidad ni separación clara mensaje-cliente vs detalle operativo.

**Clasificación:** `READY AFTER SMALL GAP`

No es BLOCKER de CASI. No es READY NOW.

---

## 2. Current Capability

### Qué existe hoy

| Capacidad | Estado |
|---|---|
| Cliente crea ticket (portal POST / N1 create) | READY |
| Cliente lee ticket + eventos `visible_cliente=Sí` | READY |
| Agente/admin actualiza campos vía `PUT /tickets/{id}` | READY (interno) |
| Agente agrega nota (`interno` Sí/No) | READY |
| Proactivo `ticket.created` / `ticket.updated` / `ticket.closed` / `ticket.sla_breached` | READY (2.3G-B + 2.6A) |
| Mobile `event=updated` + deep-link Activity | READY |
| N1 Action Runtime `update_ticket` | READY como **append evidencia** — **sin** TicketEvent / **sin** push |

### Mapa A–L (significado de “update”)

| Concepto | ¿Existe en código? | Customer-visible? | Notificable? |
|---|---|---|---|
| A. Actualización interna | Sí (`nota_interna`, campos ops) | Flag `No` o denylist | No (si interno/denylist) |
| B. Actualización N1 (abonado) | Sí (`_exec_update_ticket` → evidencia) | **No** (no hay evento) | **No** |
| C. Actualización visible cliente | Parcial (`nota` / `actualizacion` default Sí) | Sí (si flag) | Sí → `ticket.updated` |
| D. Nota interna | Sí `POST .../events` `interno=true` | No | No |
| E. Cambio de estado | Sí `repo.update_ticket(estado=)` | Evento `actualizacion` default Sí | Sí (`updated` o `closed`) |
| F. Asignación | Sí claim/reassign | Evento `reasignacion` flag Sí pero **denylist push** | No push; **sí puede listarse en portal** |
| G. Prioridad | **NO EVIDENCE** de campo prioridad en Ticket | — | — |
| H. Cambio SLA | `estado_sla` vía update; breach vía engine | Auto-evento puede incluir `SLA=…` en detalle | Push si `actualizacion` |
| I. Mensaje/observación visible | `nota` con `visible_cliente=Sí` | Sí (`detalle`) | Sí |
| J. Cierre | `estado=Cerrado` | → `ticket.closed` | Sí |
| K. Resolución | Campo `resolucion_tecnica`; `ticket.resolved` **UNSUPPORTED** | Detalle puede filtrarse vía evento | No como evento canónico |
| L. Reapertura | **NO EVIDENCE** | — | — |

---

## 3. Authority Inventory

| Atributo | Clasificación | Evidencia |
|---|---|---|
| `estado` | INTERNAL WRITE | `api/v1/tickets.py` PUT → `repo.update_ticket` |
| Comentario/nota agente | AUTHORIZED WRITE (agente) | `POST /tickets/{id}/events` |
| Mensaje cliente dedicado | NO EVIDENCE (campo) | Se reutiliza `TicketEvent.detalle` |
| `asignado_a` | INTERNAL WRITE | claim / reassign / PUT |
| Prioridad | NO EVIDENCE | — |
| SLA fields | INTERNAL WRITE | `sla_engine` + opcional `estado_sla` en PUT |
| `tipo` TicketEvent | INTERNAL WRITE | writer elige string |
| `categoria` | AUTHORIZED WRITE (create) / READ ONLY portal | create portal/N1; no PATCH portal |
| `resolucion_tecnica` | INTERNAL WRITE | PUT update |
| Cierre | INTERNAL WRITE | PUT `estado=Cerrado` / bulk close |
| Evidencia / descripción (N1) | AUTHORIZED WRITE (Runtime, ownership) | `_exec_update_ticket` → `_append_evidencia_ticket` |
| Portal mutate ticket | NO EVIDENCE | Solo GET + POST create |
| LLM mutate Ticket/Event | NO EVIDENCE | CASI: LLM ≠ writer |

---

## 4. Update Paths

### Path 1 — Consola agente (campos)

```text
PUT /api/v1/tickets/{id}
  → repository.update_ticket
  → COMMIT Ticket
  → add_ticket_event(tipo=actualizacion|reasignacion, visible_cliente default "Sí")
  → COMMIT TicketEvent
  → maybe_deliver_ticket_event_push
  → policy → deliver → ownership → claim → Expo
```

### Path 2 — Consola agente (nota)

```text
POST /api/v1/tickets/{id}/events
  → add_ticket_event(tipo=nota|nota_interna, visible_cliente Sí|No)
  → detector → …
```

### Path 3 — N1 Action Runtime `update_ticket`

```text
Proposal → Policy → Runtime._exec_update_ticket
  → ticket_pertenece_abonado
  → _append_evidencia_ticket (evidencia + descripcion_falla)
  → COMMIT Ticket
  → (NO TicketEvent)
  → (NO push)
```

### Path 4 — Create (portal / N1 / bridge)

```text
create_ticket → COMMIT → add_ticket_event(creacion) → push ticket.created
```

### Path 5 — SLA (2.6A, fuera de alcance de cambio)

```text
apply_sla → COMMIT sla_breached_at → emit sla_breach → push
```

### Path 6 — Bulk close

```text
cerrar_tickets_abiertos inserta TicketEvent(cierre_masivo, visible=No)
  bypassing add_ticket_event → NO push hook
```

---

## 5. Customer Visibility Model

### Mecanismos

1. **Flag** `TicketEvent.visible_cliente` (`"Sí"` / `"No"`).
2. **Denylist push** `_INTERNAL_TIPOS` en `eko_ticket_proactive` (bloquea push aunque flag sea Sí).
3. **Portal filter** `solo_visibles=True` → solo `visible_cliente == "Sí"` (**no** aplica denylist).
4. **Proyección ticket** portal: `id, estado, categoria, origen, created_at, updated_at, conversacion_id` — sin evidencia/resolución/asignado/SLA.
5. **Eventos portal:** `id, titulo, detalle, estado, created_at`.

### Respuestas obligatorias

1. **¿Separación sólida nota interna vs mensaje cliente?**  
   **Parcial.** Existe en `POST .../events` (`interno` → `nota_interna`/`No` vs `nota`/`Sí`). **No** existe en auto-eventos de `repo.update_ticket` (siempre default `visible_cliente="Sí"`).

2. **¿Riesgo de filtrar información interna?**  
   **Sí (GAP).** `detalle` de `actualizacion` puede contener frases operativas (`resolución técnica actualizada`, `SLA=…`, `proveedor=…`, `motivo de escalamiento…`) y el portal las expone si el flag es Sí. El **push** no copia `detalle` (usa copy fija) — el leak es principalmente **GET portal eventos**.

3. **¿Qué evento exacto puede notificarse?**  
   Mapeo: `creacion`→`ticket.created`; `nota`/`actualizacion`(≠Cerrado)→`ticket.updated`; `actualizacion`+Cerrado→`ticket.closed`; `sla_breach`→`ticket.sla_breached`. Tipos en denylist → no push.

4. **¿Qué texto puede mostrarse?**  
   Push: títulos/cuerpos fijos en `_TICKET_COPY` (no LLM, no detalle del evento). Portal: `titulo`+`detalle` del TicketEvent.

5. **¿Quién autoriza ese texto?**  
   Writer del evento (agente/sistema/código). LLM no es autoridad de visibilidad ni de copy de push.

### LLM / IA

| Uso | Clasificación |
|---|---|
| Copy proactiva fija | CONTENT (no AUTHORITY) |
| Borrador KB desde ticket | PROPOSAL |
| Visibilidad / mutate / push | LLM ≠ AUTHORITY (evidencia: gates deterministas) |

---

## 6. CASI Audit

```text
LLM → interpretation / proposal / content
NO → mutate Ticket | TicketEvent | visibility | push
```

| Ruta | Bypass CASI? |
|---|---|
| Action Runtime `create_ticket` / `update_ticket` | No — TrustedContext + Policy + ownership |
| Journeys → create vía runtime | No |
| Escritura LLM JSON directa a ORM | **NO EVIDENCE** |
| Heurística journey que llame `repo.update_ticket` | **NO EVIDENCE** |

**Veredicto CASI:** intacto para escritura de tickets. Runtime **sí** escribe Ticket (create + evidencia) bajo trusted path; eso es diseño Action Runtime, no bypass LLM→effect.

**BLOCKER CASI:** ninguno encontrado.

---

## 7. Ownership Audit

Cadena (push y portal):

```text
Ticket → ticket_pertenece_abonado (conv.ticket_id y/o linea ∈ claves)
  → DNI / Abonado → PortalDevice → Expo
```

| Caso | Resultado esperado / real |
|---|---|
| A. Ticket del abonado | Continúa |
| B. Ticket ajeno | Portal 404; Runtime `foreign_ticket`; push 0 |
| C. Ambiguo | Solo si reglas cruzan línea/conv — sin LLM |
| D. Inexistente | Deny / 0 push |
| E. Multi-account | Ownership por abonado autenticado / DNI devices |
| F. Visitor | Portal auth requerido; sin abonado → deny |

N1 `update_ticket` exige `ticket_pertenece_abonado` antes de mutar evidencia.

---

## 8. Event Semantics

### ¿Qué significa `ticket.updated` hoy?

Cualquier `TicketEvent` con:

- `tipo=nota` (customer-visible), o
- `tipo=actualizacion` y `estado ≠ Cerrado`

después de pasar gate de visibilidad.

### Características

| Pregunta | Respuesta |
|---|---|
| ¿Se emite por cualquier modificación? | Casi: cualquier `cambios[]` en `update_ticket` (excepto solo asignación→`reasignacion`) |
| ¿Spam? | **Riesgo alto** — un push attempt por cada TicketEvent.id |
| ¿Materiality/diff? | **No** (solo lista de strings de cambio) |
| ¿Actor? | Sí (`actor`) |
| ¿Timestamp? | `created_at` del evento |
| ¿Tipo de cambio fino? | No canónico (todo cae en `updated`) |
| ¿Mensaje cliente? | Solo si writer lo pone en `detalle`/`titulo` |

### Eventos más específicos (conceptuales — NO implementar en 2.6C)

| Evento | ¿Necesario? |
|---|---|
| `ticket.updated` (genérico) | Insuficiente solo; hoy es bucket amplio |
| `ticket.customer_message` | **Recomendado conceptualmente** para N1/agente mensaje al cliente |
| `ticket.status_changed` | Útil para separar admin noise |
| `ticket.assigned` | Ya parcialmente `reasignacion` (denylist) |
| `ticket.resolved` | Dominio no tiene estado Resuelto — CLOSED cycle = `Cerrado` |

---

## 9. Dedup / Anti-Spam

| Capa | Garantía |
|---|---|
| `TicketEvent.id` + `push_claimed_at` | AT-MOST-ONCE attempt Expo **por evento** |
| Mismo evento reprocesado | `already_claimed` → 0 segundo attempt |
| Multi-device | Todos los tokens elegibles en **un** attempt del claim |
| Transient Expo | No desactiva; claim ya consumido → no reintento automático |
| Permanent DeviceNotRegistered | Deactivate token |

### Gaps

- **Misma actualización lógica** no se re-pushea (OK).
- **Dos actualizaciones administrativas consecutivas** → **dos** TicketEvents → **dos** pushes `ticket.updated` → **GAP anti-spam / materiality**.
- N1 evidencia repetida (`bloque in ev`) evita re-append, pero sin evento de todas formas.

---

## 10. Transaction Boundaries

```text
update_ticket:
  mutate Ticket → COMMIT A
  → (si cambios) add_ticket_event → COMMIT B → post-commit push

_append_evidencia_ticket:
  mutate Ticket → COMMIT
  → sin evento

create_ticket:
  COMMIT ticket (+ SLA commit) → add_ticket_event (otro commit)
```

Posibles estados intermedios:

- Ticket actualizado **sin** TicketEvent (crash entre A y B; o path N1 evidencia).
- TicketEvent **sin** push (ownership fail antes de claim; o claim sin delivery exacta).
- No se observa TicketEvent sin Ticket persistido en paths normales (evento referencia `ticket_id` existente).

Arquitectura **no** se cambia en esta fase (solo documentada).

---

## 11. Mobile Contract

Archivos inspeccionados: `pushIncidente.ts`, `push.ts`, `AppShell.tsx` (Activity focus).  

| Item | Estado |
|---|---|
| `tipo=ticket` | Soportado |
| `event=updated` | En allowlist canónica |
| `created` / `closed` / `resolved` / `sla_breached` | Allowlist |
| Deep-link | `pushFocusTicketId` → Activity |
| Autoridad | GET autenticado; push ≠ SoT |

**`ticket.updated` E2E (infra):** READY.  
**Semántica de producto “qué updated significa”:** NO READY (ver §8–9).

---

## 12. Portal Authorization

| Endpoint | Cliente puede |
|---|---|
| `GET /portal/tickets` | Listar propios |
| `GET /portal/tickets/{id}` | Detalle + eventos visibles; **404** si no ownership |
| `POST /portal/tickets` | Crear reclamo |
| PATCH/PUT/DELETE | **NO EVIDENCE** |

Campos internos del modelo Ticket **no** se proyectan en list/detail.  
Eventos con `visible_cliente=Sí` **sí** exponen `detalle` completo (riesgo §5).

N1/agente: escritura por APIs internas / Runtime, no por portal mutate.

---

## 13. Test Coverage

| Área | Suite | Resultado (sesión) |
|---|---|---|
| ticket create / portal IDOR | `test_portal_tickets.py` | PASS |
| nota visible Sí/No | `test_helpdesk_features.py` | PASS |
| proactive map/gate/push | `test_eko_ticket_proactive_2_3gb.py` | PASS |
| SLA + map created/updated/closed | `test_eko_ticket_sla_breach_2_6a.py` | PASS |
| CASI / final authority | `test_final_authority_audit.py` | PASS |
| Runtime foreign / update capability | `test_eko_action_runtime_4b.py` (subset update) | PASS (foreign/update paths) |
| Diagnostic 4b unrelated | `test_4b_explicit_diagnostic_invokes_reader_when_selected` | **FAIL** (preexistente / 2.5 service selection — fuera de alcance 2.6C) |
| Materiality / anti-spam updated | — | **MISSING** |
| N1 update → TicketEvent | — | **MISSING** |
| Leak detalle operacional portal | — | **MISSING** |
| Reopen | — | **MISSING** (no feature) |

---

## 14. Risks / Gaps

| ID | Gap | Severidad |
|---|---|---|
| G-01 | N1 `update_ticket` no emite TicketEvent → no consultable en timeline ni notificable | Alto (bloquea la capability deseada) |
| G-02 | `repo.update_ticket` auto-event default `visible_cliente=Sí` + detalle operativo → leak portal | Alto |
| G-03 | Sin materiality: N updates admin → N pushes `ticket.updated` | Alto (spam) |
| G-04 | Portal filter ≠ push denylist (`reasignacion` puede listarse) | Medio |
| G-05 | No hay campo `mensaje_cliente` — `detalle` dual-use | Medio |
| G-06 | `ticket.resolved` / reopen: unsupported / inexistente | Bajo–Medio (claridad producto) |
| G-07 | Cliente no puede mutar ticket vía portal (solo create/read) | Info (puede ser intencional) |

Ninguno se **resuelve** en 2.6C.

---

## 15. External Dependencies

Ninguna dependencia BSS/ externa bloqueante para esta capability.  
Depende de producto/contrato interno:

- qué escritura N1/agente es “mensaje al cliente”;
- política de materiality;
- alineación portal vs denylist.

Expo / PortalDevice / ownership ya disponibles (2.3).

---

## 16. Recommendation

**No implementar** push/customer-visible N1 update en la próxima fase hasta cerrar un contrato mínimo:

1. **Definir** el acto customer-visible (p.ej. solo `nota` explícita o futuro `ticket.customer_message`), no “cualquier `update_ticket`”.
2. **Separar** auto-eventos administrativos (`visible_cliente=No` o tipo denylist) de mensajes al cliente.
3. **Decidir** si N1 Runtime debe emitir TicketEvent (hoy no) y con qué texto autorizado (nunca LLM-as-authority).
4. **Añadir** materiality / anti-spam antes de habilitar más `ticket.updated` en producción.
5. Reutilizar pipeline 2.3G-B sin nuevo push provider.

Orden sugerido (futuro, no esta fase): contrato → gaps G-01/G-02/G-03 → tests → readiness audit tipo 2.6B.

---

## 17. Final Classification

```text
READY AFTER SMALL GAP
```

**Por qué no READY NOW:** falta autoridad/emit customer-visible en el path N1 y falta política de visibilidad/materiality en el path agente que hoy dispara `ticket.updated`.

**Por qué no BLOCKED:** CASI intacto; ownership/dedup/mobile/portal auth reutilizables; no hace falta infraestructura nueva de push.

**Por qué no DOCUMENTATION ONLY:** hay writers, eventos y push reales; el gap es de cableado/contrato, no de ausencia total de sistema.

---

## 18. Audit meta

| Item | Value |
|---|---|
| Files inspected (core) | `models.py`, `repository.py`, `tickets.py`, `portal.py`, `abonado_tickets.py`, `eko_ticket_proactive.py`, `eko_proactive_policy.py`, `eko_proactive_push.py`, `app_push.py`, `eko_action_runtime.py`, `canal_abonado.py` (`_append_evidencia_ticket`), `pushIncidente.ts`, `AppShell.tsx`, docs 2.3G-B / 2.6A / 2.6B |
| Tests executed | portal, 2.3G-B, 2.6A, helpdesk notes, CASI, 4b subset |
| Code changes | **NONE** |
| Docs created | este archivo |
| SAFE_SMOKE | NOT_AVAILABLE (discovery; no harness controlado ejecutado) |
| Production side effects | Ninguno |

---

**FINAL:** `EKO 2.6C — READY AFTER SMALL GAP`
