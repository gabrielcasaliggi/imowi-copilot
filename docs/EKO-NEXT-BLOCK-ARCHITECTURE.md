# EKO — Next Product Block

**Status:** PASS  
**Date:** 2026-09-28  
**Role:** Architect — contrato del siguiente milestone. Sin implementación.  
**Baseline cerrado:** 2.5 FROZEN · 2.6 CLOSED · 2.7D CLOSED (deploy + smoke).  
**Código, configuración y producción:** no se modifican en esta fase.

Evidencia usada: journeys y Runtime actuales, `read_invoices_fc`, `GET /portal/customer-summary`, `GET /portal/ov-links`, Home de `mobile/`, contrato proactivo 2.3/2.6A, cierre 2.7D. No se reabre 2.5, 2.6 ni la auditoría de 2.7D.

---

## 1. Current baseline

Después de 2.7D, el abonado ya puede:

| Dominio | Qué está operativo |
|---|---|
| Identidad | JWT portal, desambiguación multi-cuenta, `selected_service_ref` |
| Incidente Internet fijo | Selección → diagnóstico del servicio elegido → explicación → `create_ticket` Runtime → continuidad si ya hay ticket → frases de seguimiento y de nota |
| Espera de agente | `espera_agente` sigue en cola humana y puede retomar continuidad / nota / `show_ticket` |
| Tickets | Crear (Runtime en producción), consultar, listar en la app (Activity). Nota de cliente implementada en código y **apagada** en el CSV de producción |
| Facturación en el chat | Saldo (snapshot de padrón), cabecera FC (`show_invoice`), handoff OV para pagar / talón / ver factura. Vencimiento e historial de pagos responden honest unavailable |
| Facturación en la app | Home muestra saldo + botones OV. No lista cabeceras FC |
| Servicios | `service_list`, selección, diagnóstico de Internet fijo. `installation_status` responde que no hay fuente |
| Proactivo | `outage.started` / `material_update` / `resolved`; `ticket.created` / `updated` / `closed` / `sla_breached`. Dedup y cooldown ya existen |
| App | Home, chat, Activity, cuenta, conectividad, push y voz cuando el build tiene Firebase |

Mutación customer-facing en producción: `create_ticket`. El default de código incluye más acciones; el CSV efectivo de producción no se toca y, según el cierre 2.7D, no incluye `ticket_customer_note`.

---

## 2. Product capability map

Estados de esta sección: `READY` · `READY_WITH_SMALL_GAP` · `BLOCKED_EXTERNAL` · `OUT_OF_SCOPE` · `NOT_JUSTIFIED`.

### A. Incident / CX — READY

| Capability | Estado | SoT | Runtime / Action | Superficie | Dependencia externa | Observación |
|---|---|---|---|---|---|---|
| Continuidad de incidente | READY | `conv.ticket_id` + journey (`last_diagnostic_result`, `selected_service_ref`) | Gate en `_advance_connectivity` | Chat N1 | Ninguna | 2.7D. No reabrir |
| Seguimiento de ticket | READY | Estate ticket del abonado | `show_ticket` | Chat + Activity | Ninguna | |
| `ticket_customer_note` | READY en código; apagado en prod | `TicketEvent` tipo `nota` | Action existe; `covers()` depende del CSV | Chat, y Activity cuando el evento existe | Decisión de ops, no un sistema nuevo | No es un hueco de código. No se activa en este milestone |
| “Sin internet” | READY | Portal connectivity + probes del servicio elegido | `run_diagnostic_pppoe` (BCM/UISP en su camino actual) | Chat | Probes ya integrados | |
| Multi-servicio | READY | Catálogo + `selected_service_ref` | Selección / `needs_input` | Chat | Ninguna | Ambiguo no diagnostica |
| `espera_agente` | READY | Estado de conversación | Hook a journeys sin salir de la cola | Chat | Ninguna | |

### B. Billing self-service — READY_WITH_SMALL_GAP

| Capability | Estado | SoT | Runtime / Action | Superficie | Dependencia externa | Observación |
|---|---|---|---|---|---|---|
| Saldo / deuda | READY | `abonado.deuda_monto` (snapshot). Refresh BillTrack solo si `refresh=billing` | `show_balance` | Chat + Home (`customer-summary`) | BillTrack solo en el refresh explícito | No convertir el Home en saldo live |
| Cabecera de factura | READY en chat; ausente en Home | BillTrack `api_invoice` type `FC`: number, full_type, amount, date, state | `show_invoice` → `read_invoices_fc` | Chat sí. Home no. No hay `GET` portal de facturas | La misma lectura BillTrack que el chat ya usa | Hueco de este milestone |
| Vencimiento | BLOCKED_EXTERNAL | No está en el reader. El DTO fuerza `due_date: null` | Journey `honest_unavailable` + OV | Chat | Esquema BillTrack | No inventar |
| Deuda distinta del saldo | NOT_JUSTIFIED | El saldo del padrón es la deuda que el producto muestra | `show_balance` | Home | — | No abrir un segundo concepto |
| Historial de pagos | BLOCKED_EXTERNAL | No hay reader | Journey honest unavailable + OV | Chat | Sin SoT | |
| PDF / líneas / cuenta corriente | BLOCKED_EXTERNAL | Fuera de `api_invoice` cabecera | OV destino `invoice` | Botón “Ver factura” | OV | Handoff, no lectura |
| Navegación OV | READY | Allowlist `pay` / `invoice` / `payment_slip` | `open_OV` + `GET /portal/ov-links` | Chat + Home | El abonado se identifica en la OV | No es un pago |
| Ejecución de pago | OUT_OF_SCOPE | — | — | — | PSP / OV | |
| Hint `can_answer_invoice_fields: false` | READY como guarda | Metadata 2.1, no un SoT | Prompt | N1 | — | Sigue en false. No significa “no hay cabecera”; significa “no hay campos de detalle”. No invertirlo |

### C. Proactive — READY

| Capability | Estado | SoT | Runtime / Action | Superficie | Dependencia externa | Observación |
|---|---|---|---|---|---|---|
| Corte de red | READY | Outage de red | Pipeline 2.3 | Push + Home | Ninguna nueva | |
| Ticket creado / actualizado / cerrado | READY | `TicketEvent` visible | 2.3G | Push + Activity | Ninguna nueva | |
| SLA | READY | `sla_breached_at` | `ticket.sla_breached` | Push | Ninguna nueva | |
| Dedup / cooldown | READY | Claim del pipeline | Policy 2.3C | Push | — | |
| Facturación proactiva | BLOCKED_EXTERNAL | No hay vencimiento ni pago como evento | — | — | SoT inexistente | |
| Conectividad perdida/restaurada como evento | BLOCKED_EXTERNAL | No hay detector con SoT | — | — | — | El diagnóstico bajo demanda ya existe |
| Nuevo tipo de evento | NOT_JUSTIFIED | Los siete eventos habilitados cubren el SoT actual | `SUPPORTED_PROACTIVE_EVENTS` | — | — | No endurecer 2.3 sin regresión demostrada |

### D. Service management — READY

| Capability | Estado | SoT | Runtime / Action | Superficie | Dependencia externa | Observación |
|---|---|---|---|---|---|---|
| Listado | READY | Inventario portal / BillTrack | `service_list` | Chat + Home | Ninguna nueva | |
| Selección | READY | `selected_service_ref` | `request_account_selection` | Chat | Ninguna | 2.5 congelado: no nuevo campo |
| Conectividad / diagnóstico fijo | READY | Portal connectivity + probes | `run_diagnostic_*` | Home + chat | Sistemas ya integrados | |
| Sensa / VoIP operativo | OUT_OF_SCOPE | Sin probe de esos tipos | Triage + handoff | Chat | Plataforma externa | |
| `installation_status` | BLOCKED_EXTERNAL | No hay agenda ni orden | Action que responde `source_unavailable` | Chat | BSS / cuadrilla | La respuesta honesta ya está |
| Alta / baja / cambio de plan | OUT_OF_SCOPE | — | — | OV / humano | BSS WRITE | |

### E. Mobile / customer experience — READY_WITH_SMALL_GAP

| Capability | Estado | SoT | Runtime / Action | Superficie | Dependencia externa | Observación |
|---|---|---|---|---|---|---|
| Home saldo, servicios, conectividad, reclamo | READY | `customer-summary`, connectivity, tickets | Portal GET/POST ya usados | Home | Ninguna | |
| Chat, voz, push | READY condicionado al build | Mismos APIs | `/portal/messages`, `/portal/audio`, FCM | Chat / push | Firebase en el binario de producción | Empaquetado de tienda no es este milestone |
| Tickets | READY | Estate | `GET/POST /portal/tickets` | Activity | Ninguna | |
| Facturas en Home | READY_WITH_SMALL_GAP | El reader de cabecera | No hay endpoint portal | Home, junto a `BalanceCard` | La misma BillTrack del chat | Único hueco de superficie con SoT |
| OV | READY | `GET /portal/ov-links` | Handoff | `BalanceCard` | Auth en la OV | El botón “Ver factura” abre la OV; no lista cabeceras |

`mobile/BACKEND_CAPABILITIES.md` (2026-09-15) está viejo en OV: `GET /portal/ov-links` existe. Sigue siendo cierto que no hay endpoint portal de facturas.

### F. Knowledge / support — NOT_JUSTIFIED

| Capability | Estado | SoT | Runtime / Action | Superficie | Dependencia externa | Observación |
|---|---|---|---|---|---|---|
| Playbooks N1 | READY | Platform settings | Motor de conversación | Chat técnico | Ninguna | Ya alimentan el incidente |
| KB de consola | READY para agentes | Estate KB | Admin | Consola | Ninguna | No es FAQ de abonado |
| FAQ de abonado | NOT_JUSTIFIED | No hay corpus customer-safe distinto del playbook | — | — | — | Publicar la KB interna sería otra autoridad |
| Recuperación de contexto | READY | 2.5 congelado | Journey state | Chat | Ninguna | No reabrir |

---

## 3. Open product gaps

Solo huecos vistos en código o en el cierre 2.7D.

### UX gap

- El Home muestra saldo y un botón OV “Ver factura”. No muestra número, importe, fecha de emisión ni estado de las FC que `show_invoice` ya puede decir en el chat.
- El portal web es chat. Ahí la cabecera ya se responde. No hace falta un panel nuevo en la web para cerrar el hueco.

### Backend capability gap

- No existe un GET portal que proyecte `read_invoices_fc` con la identidad del JWT. El reader y la Action de chat sí existen.
- `customer-summary` arma saldo + OV y declara que no inventa facturas. Meter la lectura BillTrack dentro de ese GET cambiaría la latencia y el fallo de un contrato que el Home ya usa para el saldo.

### SoT gap

- `due_date`, líneas, PDF, moneda de factura, período, historial de pagos, agenda de instalación, evento proactivo de facturación o de “se cayó internet”.

### External dependency

- Pago, BSS/CRM WRITE, orden de instalación, control Sensa/VoIP, FCM/tienda si se quisiera un release de canal.

### Operational gap

- `ticket_customer_note` no está en el CSV de producción. El camino de código y los tests de 2.7D ya existen. Activarlo es una decisión de ops, no un desarrollo. Queda fuera de este milestone.

---

## 4. Candidate next blocks

### Cabecera de factura en el inicio

### Problema del cliente

Para ver el número, el importe y la fecha de la última factura, el abonado tiene que escribirle a Eko o salir a la Oficina Virtual. El saldo ya está en el inicio. La cabecera, no.

### Capacidad existente reutilizable

`read_invoices_fc`, formato de monto ya usado por el chat, identidad del JWT portal, `BalanceCard` y links OV para el PDF y el pago.

### Qué falta

Un GET portal de solo lectura y una sección en el Home que consuma ese GET. El fallo de facturas no puede borrar el saldo.

### SoT

BillTrack `public.api_invoice`, `type = FC`, columnas ya seleccionadas: `id` (interno, no se expone), `number`, `full_type`, `amount`, `date`, `state`. Ownership: `account_number` = `abonado.client_number` del JWT.

### Runtime / Action

No se agrega Action. No se cambia `ACTION_RUNTIME_ACTIONS`. El chat sigue en `show_invoice`. El Home no pasa por el Runtime: es el mismo reader detrás de un endpoint portal, igual que servicios y OV.

### Superficie

`mobile/` Home, debajo o junto a `BalanceCard`. Portal web: sin UI nueva.

### Riesgos

- Una query BillTrack en cada apertura del Home. Aislada del summary para que un timeout no tire el saldo.
- Mostrar `due_date: null` invita a dibujar un vencimiento vacío. El contrato no incluye esa clave.
- Exponer `client_number` o el id interno de BillTrack no aporta a la lectura y amplía superficie. No van en el JSON.

### Dependencias

BillTrack de lectura, ya usada por `show_invoice`. Si no responde, el endpoint dice `unavailable` y el saldo sigue.

### Scope sugerido

1. `GET /api/v1/portal/invoices`
2. Proyección pública de cabeceras (máximo 5 por defecto, tope 20, la misma pinza del reader).
3. Home: lista con carga, vacío, no disponible y éxito.
4. Tests de ownership, allowlist de campos, BillTrack caído y regresión del summary.

### Out of scope

Vencimiento, PDF, líneas, historial, pago, refresh de saldo, cambio del hint N1, journeys, CSV de acciones, nota de ticket, portal web.

### Exit criteria

- Sin query `client_number` / `dni` / `account_number`: 400 y cero lecturas.
- Identidad solo del JWT. Cuenta sin `client_number`: `unavailable` + `missing_client_number`, sin query.
- `ok` devuelve solo `invoice_number`, `full_type`, `amount`, `issued_at`, `status`.
- `empty` con `no_fc_invoices` no inventa filas.
- BillTrack down: `unavailable` o `error` con `invoices: []`. `GET /portal/customer-summary` sigue igual.
- Home no pinta vencimiento ni un botón de pago nuevo. Los botones OV actuales quedan.
- Si las facturas fallan, el saldo sigue visible.
- `ticket_customer_note` sigue fuera del CSV. Ningún flag de producción cambia.

---

### Activar la nota de ticket en producción

### Problema del cliente

“Quiero agregar que…” no deja un evento visible mientras el CSV de producción no cubre la Action.

### Capacidad existente reutilizable

Action, Policy, Event `nota`, journey 2.7D, Activity cuando el evento existe.

### Qué falta

Decisión de ops y un cambio de CSV más restart. No falta código de producto.

### SoT

`TicketEvent`.

### Runtime / Action

`ticket_customer_note` ya registrada. Hoy `covers()` es falso en producción.

### Superficie

Chat. Activity ya puede mostrar el evento.

### Riesgos

Más eventos y push `ticket.updated` en producción.

### Dependencias

Ninguna de sistema. Sí una decisión explícita de producto/ops.

### Scope sugerido

Ninguno en este ciclo. El procedimiento de activación ya está en el cierre 2.7D.

### Out of scope

Reimplementar la nota. Ampliar Actions. `update_ticket`.

### Exit criteria

No aplica hasta que ops pida la activación en un ciclo aparte, con smoke de identidad autorizada.

---

### Proactivo nuevo o de facturación

### Problema del cliente

Avisar un vencimiento o un pago sin que el abonado pregunte.

### Capacidad existente reutilizable

Pipeline de outage y ticket, con dedup.

### Qué falta

Un hecho autoritativo que hoy no existe. El pipeline no debe inventarlo.

### SoT

No hay SoT de vencimiento ni de pago.

### Runtime / Action

No corresponde.

### Superficie

Push. No usarla sin evento real.

### Riesgos

Notificación masiva de un dato fabricado.

### Dependencias

Esquema o evento externo que este repo no tiene.

### Scope sugerido

Ninguno.

### Out of scope

Nuevos `event_type`. Detectores de billing o de “conectividad perdida”.

### Exit criteria

No entra a implementación.

---

### Instalación, pago, Sensa, VoIP, tienda

### Problema del cliente

Seguir una visita, pagar dentro de Eko, operar TV/telefonía, o publicar la app.

### Capacidad existente reutilizable

`installation_status` honesto, OV de pago, triage de Sensa/VoIP, binario Expo.

### Qué falta

SoT o cuenta externa (BSS, PSP, Sensa, Asterisk, Firebase/EAS).

### SoT

No está en Eko para esos efectos.

### Runtime / Action

No crear Actions de efecto.

### Superficie

No ampliar.

### Riesgos

Efecto comercial o de red sin autoridad.

### Dependencias

Todas externas.

### Scope sugerido

Ninguno dentro de Eko.

### Out of scope

Todo efecto WRITE de esos dominios.

### Exit criteria

Siguen en espera.

---

## 5. Recommended sequencing

No hay ranking. Hay una sola cadena posible con lo que ya existe.

```text
Ahora
  Cabecera de factura en el Home
    usa reader + JWT + BalanceCard
    no depende de la nota ni del proactivo

Decisión de producto (ciclo distinto, cuando ops lo pida)
  Activar ticket_customer_note en el CSV
    el código de 2.7D ya está
    no bloquea ni es bloqueado por la cabecera

Dependencia externa (no empieza)
  Vencimiento, historial, PDF, pago, instalación, Sensa/VoIP, proactivo de billing
    cada uno espera un SoT que hoy no está

Espera
  Nuevos eventos proactivos
  FAQ de abonado a partir de la KB interna
  update_ticket / cierre / resuelto como Action del abonado
  Reescritura de 2.5 o de 2.6
```

La cabecera no genera el vencimiento. Cuando algún día exista esa columna, un bloque de vencimiento podría leerla. Hasta entonces el Home no reserva un hueco visual para “vence el …”.

La nota de ticket no comparte archivos de dominio con las facturas (`eko_journeys` / Runtime vs portal invoices + Home). Se pueden decidir en ciclos distintos sin acoplarse. Este ciclo no la incluye para no mezclar un cambio de producción con un read nuevo.

Empaquetar la app en tienda es un trámite de canal. No aporta la cabecera y la cabecera no lo necesita.

---

## 6. Proposed next milestone

**Nombre:** EKO 2.8 — Cabecera de factura en el inicio

**Objetivo:** El abonado ve en el Home las mismas cabeceras FC que el chat ya puede leer, sin vencimiento inventado y sin salir a pagar dentro de Eko.

**Alcance:**

- `GET /api/v1/portal/invoices` autenticado con el JWT portal existente (`_portal_auth`, abonado del token).
- Query opcional `limit`. Misma pinza que el reader: default 5, mínimo 1, máximo 20. Un valor inválido cae al default, como `read_invoices_fc`.
- Si el query trae `client_number`, `dni` o `account_number`: HTTP 400. No se leen, no se usan.
- Sin `client_number` en el abonado: HTTP 200, `status: unavailable`, `reason_code: missing_client_number`, `invoices: []`.
- Lectura: `read_invoices_fc(client_number=<del abonado>, limit=...)`.
- Mapa de estado, HTTP 200 en todos los casos de negocio:

| Reader | Body |
|---|---|
| `ok` | `status: ok`, `invoices` con la proyección |
| `empty` | `status: empty`, `reason_code: no_fc_invoices`, `invoices: []` |
| `unavailable` | `status: unavailable`, `reason_code` del reader, `invoices: []` |
| `error` | `status: error`, `reason_code` del reader, `invoices: []` |

- Cada ítem, y nada más:

```json
{
  "invoice_number": "string",
  "full_type": "string",
  "amount": "string decimal",
  "issued_at": "ISO-8601 o null",
  "status": "string"
}
```

- Claves prohibidas en la respuesta: `due_date`, `period`, `currency`, `line_items`, `pdf`, `client_number`, `account_number`, `invoice_id`, `id`.
- Home: una lista bajo el saldo. Estados `loading`, `empty`, `unavailable`/`error`, `success`. Importe con el formato ARS que ya usa la tarjeta. La fecha es la de emisión. El estado es el `state` de la FC, tal cual.
- El saldo sigue viniendo de `customer-summary`. Este GET no lo refresca.

**No alcance:**

- Cambiar `customer-summary`, journeys, `billing_capabilities_hint`, Runtime, `ACTION_RUNTIME_ACTIONS`, Policy, CASI.
- Activar `ticket_customer_note`.
- Portal web, consola, push, proactivo.
- Pago, PDF, vencimiento, historial, líneas.
- Producción, `.env`, smoke de identidad real.

**Archivos / áreas probables:**

- `app/api/v1/portal.py` — el GET, junto a `ov-links` y `services`.
- Proyección chica al lado del reader o un helper de portal que solo recorte campos. El SQL del reader no cambia.
- `tests/` — módulo nuevo del endpoint. No reescribir suites 2.5 / 2.6 / 2.7D.
- `mobile/src/api.ts`, `mobile/src/types.ts`, un hook de lectura, `HomeScreen.tsx` y un bloque que reutilice `Card` / `Text`. Sin componente de diseño nuevo si `Card` alcanza.

**Agentes:** Architect (este contrato) → Developer → QA y Reviewer-Security en paralelo sobre el diff → Design-system solo en los estados del Home.

**Criterios de salida:** los de la sección 4 de este candidato, más regresión de `show_invoice` (el chat no cambia de texto) y de `customer-summary` (el saldo no depende del GET nuevo).

---

## 7. Agent workflow

### ARCHITECT

Este documento es el contrato. No hay un segundo diseño en paralelo.

- Contrato: el GET y el JSON de arriba.
- Límite: cabecera FC. Sin campos nulos de cortesía.
- Arquitectura: el Home llama un read portal; el chat sigue en `show_invoice`. No se fusionan.
- SoT: `api_invoice` FC del `client_number` del JWT.
- Invariantes: el LLM no elige la cuenta; un fallo de facturas no borra el saldo; no aparece un vencimiento.
- Exit criteria: sección 6.

### DEVELOPER

- Implementa solo ese contrato.
- No amplía el SQL, no agrega Actions, no toca producción ni el CSV.
- Si un campo del contrato no sale del reader, se detiene y vuelve al architect. No completa con otro origen.

### QA

- Happy path: una o más FC, campos exactos, orden del reader (fecha e id descendentes).
- Bordes: sin cuenta, vacío, `limit` fuera de rango, query de identidad ajena, BillTrack down.
- Regresión: `customer-summary`, `show_invoice`, journeys de incidente 2.7D sin cambio de comportamiento.
- Ownership: dos abonados, cada uno ve solo su `client_number`.
- Runtime/Legacy XOR: no aplica. Este GET no es una Action. Verificar que el chat de factura sigue su XOR actual y que este endpoint no dispara Legacy ni Runtime.

### REVIEWER-SECURITY

- Autoridad: abonado solo desde el JWT. Parámetros de identidad rechazados.
- Ownership: el `WHERE account_number = :client_number` del reader se mantiene; el endpoint no lo reemplaza por un id del cliente.
- Input no confiable: `limit` pinzado; texto libre ignorado.
- Sin `ActionProposal`. No hay efecto. No hay secreto en el JSON. No hay DNI, teléfono ni número de cuenta en la lista.
- BillTrack sigue siendo lectura. El endpoint no abre un write.

### DESIGN-SYSTEM

Interviene porque hay UI en el Home.

- Reutilizar `Card`, `Text`, `EmptyState` si ya cubre el vacío. No crear un sistema visual.
- `mobile/` no usa los tokens CSS del portal web.
- Documentar y implementar cuatro estados: loading, empty, unavailable/error, success.
- No dibujar vencimiento, deuda distinta del saldo, ni un CTA de pago además de los botones OV ya presentes.
- El fallo de facturas no reemplaza la tarjeta de saldo.

---

## 8. Definition of Ready

El developer puede empezar cuando este documento queda aceptado. Ya están definidos:

| Ítem | Definición |
|---|---|
| Problema | El Home no muestra la cabecera FC que el chat ya lee |
| Scope | GET portal + lista en Home |
| No-scope | Sección 6 y sección 10 |
| SoT | `api_invoice` FC, columnas del reader actual |
| Autoridad | JWT portal → abonado → `client_number` |
| Action | Ninguna nueva. Chat permanece en `show_invoice` |
| Ownership | Filtro por el `client_number` del token. Query de otra cuenta = 400 |
| UX | Lista de cabeceras; cuatro estados; saldo independiente; OV actual intacto |
| Tests | Ownership, allowlist, vacío, fuente caída, summary intacto, chat intacto |
| Exit criteria | Sección 6 |

No hace falta otro discovery.

---

## 9. Definition of Done

- El GET y el Home implementados según el contrato.
- Pytest del módulo nuevo en verde, más una regresión corta de `show_invoice` y de `customer-summary`.
- Ruff sobre los Python tocados.
- `npm run lint` en `mobile/` (`tsc --noEmit`).
- Reviewer-security sin hallazgos abiertos sobre identidad, campos y ausencia de efecto.
- Estados de UI cubiertos en el Home, no solo el caso con datos.
- Este documento sigue siendo la spec; el developer no la reescribe para ampliar scope.
- Ningún test nuevo se acepta como única prueba si no ejerce el endpoint real (cliente del router o equivalente ya usado en portal).
- Observabilidad: el fallo de BillTrack ya lo loguea el reader; no agregar un log con número de cuenta, DNI ni importe.
- XOR: el GET no entra al Runtime. El camino de `show_invoice` queda como está.
- Producción, env y CSV sin cambios en el mismo ciclo. El deploy, si ocurre, es un acto posterior y separado.

---

## 10. Explicit exclusions

- No activar `ticket_customer_note`.
- No editar `ACTION_RUNTIME_ACTIONS` ni el default de `app/config.py`.
- No reabrir 2.5 ni 2.6. No rehacer 2.7D.
- No tocar `_advance_connectivity`, frases de incidente ni `espera_agente`.
- No tocar Policy, CASI ni el registro de Actions.
- No pago, no write BSS/CRM, no orden de instalación, no `update_ticket`, no cierre ni resuelto de ticket por el abonado.
- No control Sensa ni VoIP.
- No vencimiento, historial de pagos, PDF, líneas ni moneda inventada.
- No evento proactivo nuevo.
- No FAQ desde la KB interna.
- No cambiar `customer-summary` para colgarle facturas.
- No panel de facturas en el portal web.
- No producción, no `.env`, no smoke con abonados reales en esta fase de diseño.
