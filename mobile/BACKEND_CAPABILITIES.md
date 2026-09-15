# Eko App vNext — capacidades backend utilizables sin modificar FastAPI

Inventario de solo lectura (2026-09-15). Complementa [`CURRENT_STATE.md`](./CURRENT_STATE.md).

**Alcance:** `app/api/v1/*`, `app/services/canal_abonado.py` y servicios de planta/padrón, `app/radius|bcm|uisp`, `app/estate`, modelos citados.  
**Nota:** no existe el paquete `app/billtrack/`; el padrón vive en `app/services/billtrack.py`.

**Estados**

| Tag | Significado |
|-----|-------------|
| **READY** | Endpoint (o payload ya expuesto por portal) usable desde la app con JWT portal + `X-Canal: app`, sin cambiar backend |
| **BACKEND CHANGE REQUIRED** | Capacidad existe en consola/servicios internos, pero **no** hay contrato portal-seguro para el abonado |
| **NOT AVAILABLE** | No hay API ni superficie abonado para esa capacidad |

**Auth portal vs consola**

- Portal: JWT `typ=portal` (`Authorization: Bearer` o cookie web). Header recomendado: `X-Canal: app` (queda en JWT en auth).
- Consola: JWT agente/admin vía `get_tenant_context` / `require_permiso(...)`. **El JWT portal no sirve** para tickets, outages, inbox, admin, analytics.

---

## Convenciones de cada ficha

1. Endpoint  
2. Método HTTP  
3. Autenticación  
4. Headers  
5. Request  
6. Response real (campos observados en código)  
7. Tipos/datos disponibles  
8. Fuente de datos  
9. Lectura / escritura  
10. Usado por mobile hoy  
11. Usado por portal web hoy  
12. Riesgos / restricciones  
13. ¿Requiere cambio backend? → tag final

---

# A. Customer / abonado

### A1. Perfil mínimo embebido en conversación — **READY**

1. `GET /api/v1/portal/conversations/{conv_id}` (también en auth verify / login-pin / messages)  
2. GET (y payloads de POST auth/messages)  
3. JWT portal; `conv_id` debe coincidir con claim `conversacion_id`  
4. `Authorization: Bearer …`, `X-Canal: app` (opcional en GET si el canal ya está en JWT)  
5. Path: `conv_id`  
6. `conversacion.abonado` vía `abonado_to_dict`:

```json
{
  "id": "...",
  "dni": "...",
  "telefono_e164": "...",
  "nombre": "...",
  "servicio": "internet|movil|ambos|...",
  "estado": "activo|corte|suspendido|baja|...",
  "deuda_monto": "0",
  "plan": "...",
  "linea_msisdn": "...",
  "client_number": "..."
}
```

7. Réplica estate `Abonado` (no BillTrack live en ese GET)  
8. Data Estate; se refresca desde BillTrack en auth / flujos N1 (`ensure_local_abonado`)  
9. Lectura  
10. Mobile: **parcial** (tipos omiten `deuda_monto`, `plan`, `client_number`, `linea_msisdn` pero el JSON **sí llega**)  
11. Portal web: sí (mismo payload)  
12. No es padrón live; DNI/teléfono en cliente; no hay endpoint “/me” dedicado  
13. **READY** (usar campos ya presentes; ampliar tipos en app)

### A2. Auth DNI + OTP / PIN — **READY**

| Endpoint | Método | Auth | Body | Response clave |
|----------|--------|------|------|----------------|
| `/api/v1/portal/auth/start` | POST | pública | `{ dni, org_slug?, linea? }` | `challenge_id`, `contact_masked`, `expires_in_seconds` (+ `debug_otp` solo non-prod) |
| `/api/v1/portal/auth/verify` | POST | pública | `{ challenge_id, otp, org_slug? }` | `portal_token`, `has_pin`, `conversacion`, `mensajes`, … |
| `/api/v1/portal/auth/login-pin` | POST | pública | `{ dni, pin, org_slug? }` | igual AuthPayload |
| `/api/v1/portal/auth/set-pin` | POST | JWT portal identified | `{ pin }` | `{ status, has_pin }` |

Headers: `Content-Type: application/json`, `X-Canal: app` en auth para marcar canal.  
Fuente: BillTrack RO (lookup) + `PortalAbonadoLink` + estate.  
Mobile: **sí**. Portal web: **sí**.  
Riesgos: anti-enumeración (errores genéricos); rate limit; `debug_otp` solo dev.  
**READY**

### A3. Eliminar datos de app — **READY**

1. `POST /api/v1/portal/account/delete`  
2. POST  
3. JWT portal identified + dni  
4. Bearer (+ X-Canal)  
5. body `{}`  
6. `{ "status": "ok" }` — borra PIN/link, devices, OTPs; **no** toca padrón  
7–9. Escritura local portal  
10. Mobile: sí. 11. Portal web: no (client).  
**READY**

### A4. Logout cookie — **READY** (bajo valor en app nativa)

1. `POST /api/v1/portal/logout` — limpia cookie; app usa SecureStore.  
**READY** (opcional)

### A5. Guest `/portal/session` — no recomendado para vNext app

Consolida sesión web/guest. App identificada usa auth/*.  
Estado: usable pero **no** es el camino app; guest puede estar off en prod. Tratar como **READY** solo si el brief lo pide; no es perfil abonado.

### A6. Catálogo BillTrack completo / multi-cuenta REST — **NOT AVAILABLE**

Lookup y servicios viven en `billtrack.py` solo servidor. Sin `GET /portal/abonado` ni `/portal/servicios`.  
**NOT AVAILABLE** → para API dedicada: **BACKEND CHANGE REQUIRED**

---

# B. Servicios contratados

### B1. Campo agregado `abonado.servicio` — **READY**

Misma fuente que A1. Valores tipicamente `internet` | `movil` | `ambos` (clasificación BillTrack al sincronizar).  
No lista login/producto/localidad.  
**READY** (badge grueso)

### B2. Lista de servicios BillTrack (logins, tipos, TV, etc.) — **NOT AVAILABLE**

`lookup_servicios_*` solo interno N1.  
**NOT AVAILABLE** / API abonado: **BACKEND CHANGE REQUIRED**

### B3. Selección de cuenta internet en chat — **READY** (conversacional)

Vía `POST /portal/messages` cuando N1 pide elegir login/domicilio.  
No hay REST de selección.  
**READY** (solo chat)

---

# C. Estado de Internet (visión abonado)

### C1. On-demand “¿está online mi internet?” REST — **NOT AVAILABLE**

No hay `GET /portal/conexion`.  
**NOT AVAILABLE** → **BACKEND CHANGE REQUIRED**

### C2. Estado vía N1 (texto + contexto) — **READY**

1. `POST /api/v1/portal/messages` → `procesar_mensaje_entrante`  
2. Tras diagnóstico, `conversacion.contexto` puede incluir claves `pppoe_*`, `bcm_*`, `uisp_*`, `outage_*` (ver D–G)  
3. Refresh: `GET /portal/conversations/{id}`  
Fuente: Radius/BCM/UISP según tecnología, solo cuando N1 consultó.  
**READY** con restricciones: no garantizado al login; no es contrato tipado; mezcla estado UI interno.

### C3. Admin probe Radius/BCM/UISP — **BACKEND CHANGE REQUIRED** (para app)

`POST /admin/settings/test-*` exige rol admin consola.  
No usar desde mobile.

---

# D. Estado FTTH / BCM

### D1. REST portal BCM — **NOT AVAILABLE**

Módulos `app/bcm/*` + `conexion_bcm.py` solo servidor/admin test.  
**NOT AVAILABLE** → dashboard live: **BACKEND CHANGE REQUIRED**

### D2. Snapshot en `conversacion.contexto` tras N1 — **READY** (oportunista)

Claves posibles (cuando N1 enriqueció): `bcm_resumen`, `bcm_triage`, `bcm_rama`, `bcm_rx_dbm`, `bcm_calidad_optica`, `bcm_online`, `bcm_olt`, `bcm_serial`.  
Expuestas porque `conversacion_to_dict` serializa `contexto` completo.  
Riesgos: campos internos (serial, OLT); desactualizado hasta nuevo turno diagnóstico; no documentado como API pública.  
**READY** (consumo defensivo / feature flag) o, si se exige contrato estable: **BACKEND CHANGE REQUIRED**

---

# E. Estado radio / UISP

### E1. REST portal UISP — **NOT AVAILABLE** → **BACKEND CHANGE REQUIRED**

### E2. Snapshot `contexto` — **READY** (oportunista)

Claves: `uisp_resumen`, `uisp_triage`, `uisp_rama`, `uisp_signal_dbm`, `uisp_calidad_senal`, `uisp_online`, `uisp_sitio`.  
Mismas restricciones que D2.  
**READY** / contrato estable: **BACKEND CHANGE REQUIRED**

---

# F. RADIUS / PPPoE

### F1. REST portal sesión PPPoE — **NOT AVAILABLE** → **BACKEND CHANGE REQUIRED**

### F2. Snapshot `contexto` — **READY** (oportunista)

Claves: `pppoe_rama`, `pppoe_triage`, `pppoe_resumen`, `pppoe_ip`, `pppoe_uptime`, `pppoe_producto`, `pppoe_plan_mbps`, `pppoe_login`, `pppoe_informado`.  
**READY** / API estable: **BACKEND CHANGE REQUIRED**

### F3. Lista NAS consola — **BACKEND CHANGE REQUIRED** (para abonado)

`GET /api/v1/nas` + health: permiso `outages.manage` (consola).

---

# G. Incidencias / NetworkOutage

### G1. CRUD/list outages consola — **BACKEND CHANGE REQUIRED**

| Endpoint | Auth |
|----------|------|
| `GET/POST /api/v1/outages`, `PATCH ...`, `.../resolve` | JWT consola + `outages.manage` |

Response `outage_to_dict`: id, nas_*, alcance, tipo, comentario, mensaje_cliente, eta_*, estado, fechas, …  
**No** acepta JWT portal.  
Mobile: no. Portal web abonado: no. Consola incidentes: sí.

### G2. Intercepción N1 de outage masivo — **READY**

Vía `POST /portal/messages` + `canal_outage.py`.  
Mensaje canned al abonado; `contexto`: `outage_id`, `outage_nas`, `outage_informado`, `outage_ack`, etc.  
**READY** (experiencia chat / banners leyendo `contexto`)

### G3. Lista de incidentes activos filtrados al abonado — **NOT AVAILABLE**

Sin endpoint portal “mis cortes”.  
**NOT AVAILABLE** → **BACKEND CHANGE REQUIRED**

### G4. Push por incidente a app — **READY** (infra) / cableado app pendiente

Backend `app_push.notificar_incidente_app` + devices registrados.  
Registro device: ver M.  
**READY** (si la app registra token); sin registro = no llega.

---

# H. Tickets

### H1. API tickets consola — **BACKEND CHANGE REQUIRED** (para abonado)

`GET/PUT /api/v1/tickets*`, claim, timeline, notifications, etc. → JWT **consola** (`get_tenant_context`).  
Portal JWT → 401.  
**BACKEND CHANGE REQUIRED** para “mis tickets” abonado.

### H2. `conversacion.ticket_id` — **READY** (referencia opaca)

Campo string en conversación portal. Sin detalle/timeline cliente.  
**READY** (mostrar “Hay un ticket asociado: {id}” como máximo)

### H3. `CasoConversacion` — **NOT AVAILABLE** (abonado)

Modelo del motor consola `/chat` v1, no del canal portal.  
**NOT AVAILABLE** para la app abonado.

---

# I. Conversaciones

### I1. Obtener hilo propio — **READY**

1. `GET /api/v1/portal/conversations/{conv_id}`  
2. GET  
3. JWT portal; `conv_id == JWT.conversacion_id`  
4. Bearer, `X-Canal: app`  
5. path id  
6. `{ conversacion: conversacion_to_dict, mensajes: [mensaje_to_dict...] }`  

`conversacion` incluye: id, canal, canal_display, estado, ticket_id, contexto, abonado, servicio_detectado, es_visitante, cola_prioridad, timestamps, …  
`mensaje`: id, direccion, autor, texto, created_at, media_*, media_url  

7–9. Lectura estate `ConversacionCanal` / `MensajeCanal`  
10. Mobile: sí. 11. Portal web: sí.  
12. Solo **una** conversación del token; media_url apunta a `/api/v1/inbox/.../media` (**auth consola**) → abonado **no** puede bajar media por esa URL.  
13. Texto/estado/contexto: **READY**. Media binaria: **BACKEND CHANGE REQUIRED** (URL portal) o **NOT AVAILABLE** hoy.

### I2. Enviar mensaje N1 / agente — **READY**

1. `POST /api/v1/portal/messages`  
2. POST  
3. JWT portal  
4. Bearer, `Content-Type: application/json`, `X-Canal: app`  
5. `{ "texto": "..." }` (1–4000)  
6. Mezcla result N1 (`ok`, `modo`, `estado`, …) + `conversacion` + `mensajes`  
Fuente: `canal_abonado.procesar_mensaje_entrante`  
Escritura. Mobile: sí. Portal web: sí.  
**READY**

### I3. Inbox agente (list/claim/close) — **BACKEND CHANGE REQUIRED**

`/api/v1/inbox/*` — solo consola. No para app abonado.

### I4. Session guest web — ver A5

---

# J. Facturación / deuda

### J1. `abonado.deuda_monto` + `estado` — **READY**

En payloads de conversación (A1). Réplica estate; puede desfasarse vs BillTrack hasta próximo sync auth/N1.  
Mobile tipos incompletos.  
**READY**

### J2. Consulta saldo por chat — **READY**

`POST /portal/messages` con lenguaje natural → N1 responde saldo/medios.  
**READY**

### J3. Endpoint portal “mi factura / saldo live” — **NOT AVAILABLE**

**NOT AVAILABLE** → **BACKEND CHANGE REQUIRED**

---

# K. Oficina Virtual / deep-links

### K1. Deep-links en texto de mensajes — **READY**

N1 (`ov_intencion` + `ov_batan`) inserta URLs en `mensajes[].texto`.  
App ya parsea links (`MessageText`).  
Fuente: API OV Batán servidor-side.  
**READY**

### K2. `GET /portal/ov-links` (o similar) — **NOT AVAILABLE**

`urls_ov_gestiones` / `get_fast_link` solo internos. Admin: `POST /admin/settings/test-ov-batan`.  
**NOT AVAILABLE** → botones OV sin chat: **BACKEND CHANGE REQUIRED**

---

# L. CSAT

### L1. Voto vía mensaje — **READY**

Cuando `conversacion.contexto.encuesta_pendiente === true`, enviar `"1"`…`"5"` por `POST /portal/messages`.  
`encuesta_satisfaccion` persiste en estate.  
Mobile: sí (estrellas). Portal web: sí.  
**READY**

### L2. Analytics CSAT consola — **BACKEND CHANGE REQUIRED**

`GET /api/v1/analytics/csat` — JWT consola.

### L3. Endpoint dedicado “POST /portal/csat” — **NOT AVAILABLE**

Innecesario si se usa L1; dedicado sería **BACKEND CHANGE REQUIRED**.

---

# M. Push devices

### M1. Registrar device — **READY**

1. `POST /api/v1/portal/devices`  
2. POST  
3. JWT portal **identified**  
4. Bearer, JSON, `X-Canal: app`  
5. `{ expo_push_token, platform?, device_name? }`  
6. `{ status: "ok", device_id }`  
Fuente: `PortalDevice` + validación `token_push_valido`  
Escritura. Mobile client: implementado, **UI/push no cableado**. Portal web: no.  
**READY**

### M2. Unregister — **READY**

1. `DELETE /api/v1/portal/devices`  
2. DELETE  
3. JWT portal  
5. mismo body con `expo_push_token`  
6. `{ status: "ok" }`  
Mobile: no usado. **READY**

---

# N. Audio / Whisper

### N1. Enviar audio — **READY**

1. `POST /api/v1/portal/audio`  
2. POST multipart `file`  
3. JWT portal  
4. Bearer (+ X-Canal); **sin** Content-Type JSON  
5. archivo audio (límite 8 MB)  
6. `{ ok, transcripcion?, conversacion, mensajes }` — Whisper si disponible; si no, fallback texto bot sin N1  
Fuente: `transcription` + `canal_abonado` (`entrada_audio=True`)  
Mobile: client `sendAudio` sin UI. Portal web: no.  
**READY**

### N2. TTS playback API portal — **NOT AVAILABLE**

TTS existe para otros canales; app no tiene endpoint de audio-out.  
**NOT AVAILABLE**

---

# O. Acciones disponibles

| Acción | Vía actual | Tag |
|--------|------------|-----|
| Chatear con Eko / agente | `POST /portal/messages` | **READY** |
| CSAT 1–5 | messages | **READY** |
| Set PIN / delete account | auth/set-pin, account/delete | **READY** |
| Registrar push | devices | **READY** |
| Enviar nota de voz | audio | **READY** |
| Abrir link OV | texto mensaje + Linking | **READY** |
| Cambio Wi‑Fi vía BCM | solo N1 chat (`wifi_bcm`) | **READY** conversacional; REST: **NOT AVAILABLE** |
| Crear/ver ticket N2 detalle | — | **BACKEND CHANGE REQUIRED** |
| Declarar/ver outage NAS (ops) | consola | **BACKEND CHANGE REQUIRED** |
| Forzar refresh planta sin mensaje | — | **NOT AVAILABLE** / **BACKEND CHANGE REQUIRED** |
| Branding público | `GET /api/v1/public/branding` | **READY** (sin auth) |

### Branding — **READY**

1. `GET /api/v1/public/branding`  
2. GET  
3. ninguna  
6. `bot_display_name`, `bot_display_name_short`, `org_hint`, `product_display_name`, `assistant_tagline`, `assistant_intro`  
Mobile + portal: sí.

---

## Modelos (referencia)

| Modelo | Rol vs app |
|--------|------------|
| `Abonado` | Réplica en `conversacion.abonado` |
| `ConversacionCanal` / `MensajeCanal` | Hilo portal/app |
| `PortalAbonadoLink` / `PortalDevice` / OTP | Auth app |
| `NetworkOutage` | Ops + intercepción N1; no list portal |
| `Ticket` / `TicketEvent` | Consola; solo `ticket_id` en conv |
| `CasoConversacion` | Motor `/chat` operador; **no** canal abonado |
| `EncuestaSatisfaccion` | Persistencia CSAT tras voto por mensaje |

Integraciones **sin** endpoint abonado: BillTrack RO, Radius, BCM, UISP, OV API — solo orquestadas por N1/admin.

---

# Tabla 1 — Capability | Endpoint | Mobile ready | Backend change | Source

| Capability | Endpoint | Mobile ready | Backend change | Source |
|------------|----------|:------------:|:--------------:|--------|
| Auth OTP/PIN/set-pin | `/portal/auth/*` | READY | No | BillTrack + PortalLink |
| Branding | `/public/branding` | READY | No | config |
| Perfil abonado (campos dict) | embebido en `/portal/conversations/*` + auth | READY* | No | Estate Abonado |
| Deuda/plan/estado | mismos payloads | READY* | No | Estate ← BillTrack sync |
| Servicios (lista detallada) | — | NOT AVAILABLE | Yes | BillTrack interno |
| Chat N1 / handoff | `/portal/messages` | READY | No | canal_abonado |
| Leer hilo + contexto | `/portal/conversations/{id}` | READY | No | canal_repo |
| Media mensaje binario | `media_url` → `/inbox/.../media` | NOT AVAILABLE | Yes | inbox (consola) |
| CSAT | messages + `contexto.encuesta_*` | READY | No | encuesta_satisfaccion |
| Push register/unregister | `/portal/devices` | READY† | No | PortalDevice |
| Audio in | `/portal/audio` | READY† | No | Whisper + N1 |
| OV deep-links | texto en mensajes | READY | No | ov_batan |
| OV links REST | — | NOT AVAILABLE | Yes | ov_batan |
| Snapshot BCM/UISP/PPPoE | `conversacion.contexto` | READY‡ | Ideal sí | conexion_* |
| BCM/UISP/Radius REST portal | — | NOT AVAILABLE | Yes | bcm/uisp/radius |
| Outage masivo (chat) | messages + contexto | READY | No | canal_outage |
| Outages list/CRUD | `/outages`, `/nas` | BACKEND CHANGE REQUIRED | Yes (auth) | NetworkOutage |
| Ticket detalle abonado | `/tickets*` | BACKEND CHANGE REQUIRED | Yes (auth) | Ticket |
| ticket_id en conv | conversations | READY | No | ConversacionCanal |
| Account delete / logout | `/portal/account/delete`, `/logout` | READY | No | portal |
| CasoConversacion | — | NOT AVAILABLE | N/A | motor consola |

\* Mobile ya recibe JSON; tipos UI incompletos.  
† Client listo; runtime app no cableado (ver CURRENT_STATE).  
‡ Solo tras diagnóstico N1; no on-demand.

---

# Tabla 2 — Qué se puede implementar en Eko App vNext **solo** con el backend actual

| Feature UI vNext | Cómo, sin tocar FastAPI | Tag |
|------------------|-------------------------|-----|
| Home / ficha abonado (nombre, DNI, servicio, estado, deuda, plan) | Leer `conversacion.abonado` post-login / poll | READY |
| Chat Eko + handoff + banners estado | messages + poll conversations (ya existe) | READY |
| Badge “corte / deuda” | `abonado.estado` + `deuda_monto` | READY |
| CSAT estrellas | `contexto.encuesta_pendiente` + send `"n"` | READY |
| Botones “Pagar / Factura / OV” | **No** REST; atajos que envían texto N1 **o** parsear últimos links OV del hilo | READY (UX) |
| Panel “estado de red” live al abrir app | Solo si `contexto` ya tiene bcm/uisp/pppoe; senos, pedir al usuario un mensaje o quedar vacío | READY‡ limitado |
| Registrar push + recibir cortes/handoff | `POST /portal/devices` + Expo notifications | READY |
| Nota de voz | `POST /portal/audio` + mic | READY |
| Ajustes: PIN, privacidad, borrar datos | set-pin, Linking, account/delete | READY |
| Historial multi-conversación | Un solo `conversacion_id` en JWT | NOT AVAILABLE |
| Lista “mis tickets” con timeline | — | BACKEND CHANGE REQUIRED |
| Mapa/lista incidentes NAS del barrio | — | BACKEND CHANGE REQUIRED |
| Catálogo servicios / multi-login selector UI | Solo por chat N1 | READY chat / REST: NOT AVAILABLE |
| Cambio Wi‑Fi con formulario nativo | Solo lenguaje natural → N1 | READY chat / REST: NOT AVAILABLE |
| Descargar adjuntos del hilo | media_url inbox | BACKEND CHANGE REQUIRED |
| TTS / audio-out del bot | — | NOT AVAILABLE |

### Lectura práctica para priorizar vNext

**Sin backend nuevo (alto valor):** enriquecer Home con campos `abonado.*` ya en JSON; cablear push y audio; menú de atajos que disparan mensajes N1 (saldo, OV, “no tengo internet”); banners desde `contexto` (outage, encuesta, handoff); consumo defensivo de `bcm_*`/`pppoe_*`/`uisp_*` si existen.

**Exige backend (no inventar en app):** status planta on-demand, mis tickets, outages públicos, lista de servicios, OV links tipados, media portal, refresh padrón explícito.

---

## Conservación

Este documento no modifica contratos. Cualquier pantalla vNext que dependa de claves `contexto.*` de planta debe tolerar ausencia y no asumir frescura — eso es side-channel del N1, no API de producto.
