# Anexo B — Consulta técnica H-APP-0b (2026-10)

**Fecha:** 2026-10-08 · **Rama:** `main` (`ea400fa`) · **Complementa:** `docs/AUDIT-APP-PORTAL-2026-10.md`
**Alcance:** solo lectura. No se modificó código, no se leyó `.env`, no se llamó a ninguna API ni equipo. Los archivos del motor de Eko (`app/services/*`, `app/domain/*`) se leyeron para citar su comportamiento, sin modificarlos. Los valores por defecto que se citan son los escritos en el código (`os.getenv(..., "<default>")`), no los de producción.

---

## A. Invitado (`PORTAL_ALLOW_GUEST`)

### A.1 Dónde se lee

| Qué | Archivo:línea |
|---|---|
| Lectura de la variable | `app/config.py:68` |
| Default si no está definida: `true` salvo `APP_ENV` en `production`/`prod` | `app/config.py:69-70` |
| Valores aceptados como verdadero: `1`, `true`, `yes`, `on` | `app/config.py:72-77` |
| Aviso de arranque si queda en `true` en producción | `app/config.py:596-597` |
| Único uso funcional: `POST /api/v1/portal/session` responde 401 si es `false` | `app/api/v1/portal.py:670-674` |
| Plantilla del servidor la deja en `false` | `.env.server.example:50` (solo nombre/plantilla; no es el `.env` real) |

### A.2 Qué canales afecta

| Canal | ¿Depende de `PORTAL_ALLOW_GUEST`? | Evidencia |
|---|---|---|
| Portal web | **Sí**. El botón “No soy abonado / consulta general” llama a `POST /portal/session` | `frontend/src/app/portal/page.tsx:220-231` (`onGuest`), `:449-456` (botón) |
| App móvil | **No en la práctica**. El cliente de la app no tiene ninguna llamada a `/portal/session` (`mobile/src/api.ts`). El endpoint aceptaría `X-Canal: app` (`normalizar_canal_portal` solo admite `web`/`app`, `app/domain/canales.py:5-12`), pero la app nunca lo usa | `mobile/src/api.ts` |
| WhatsApp | **No**. El webhook entra por `procesar_mensaje_entrante` sin pasar por `/portal/session` | `app/api/v1/whatsapp.py:251` |
| Telegram | **No**. Mismo camino que WhatsApp | `app/api/v1/telegram.py:168` |

En WhatsApp y Telegram, el remitente no identificado se maneja en el motor, **sin ninguna flag**:
- `app/services/canal_abonado.py:6408-6512`: si no hay abonado se intenta identificar por DNI en el texto. Si el DNI no aparece en el padrón, se deriva como visitante (`_derivar_visitante`, `:6433`, motivo `dni_no_encontrado`). Tras 3 intentos con DNI ilegible, también (`:6443-6458`).
- En canales externos (`enviar_externo(canal)`, `app/domain/canales.py:19-21`: todo lo que no es `web`/`app`), primero se pide el DNI una vez (`canal_abonado.py:6472`) y después se deriva como visitante (`:6504-6511`, motivo `visitante_sin_cuenta`).
- Las únicas condiciones de los webhooks son de transporte: verify token y firma (`whatsapp.py:299-321`, `WHATSAPP_VERIFY_TOKEN` / `WHATSAPP_APP_SECRET`), secret token (`telegram.py:107-110`, `TELEGRAM_WEBHOOK_SECRET`) y org por defecto (`WHATSAPP_DEFAULT_ORG_SLUG`, `TELEGRAM_DEFAULT_ORG_SLUG`).

### A.3 Qué ve el usuario con la flag en `false`

| Superficie | Comportamiento |
|---|---|
| Portal web | El botón de invitado **se sigue mostrando**: no hay ningún dato del backend que lo oculte, y `/public/branding` no expone la flag (`app/api/v1/branding.py:20-26`). Al tocarlo, el backend devuelve 401 con el detalle `"Iniciá sesión con DNI y verificación. Usá /api/v1/portal/auth/start"`. Como la llamada usa `skipAuth: true`, `api-client.ts:107-117` muestra ese texto literal, que el portal pinta en `portal/page.tsx:645-647`. **Resultado: el abonado ve un mensaje con una ruta de API.** |
| App móvil | Sin cambio: la app no tiene modo invitado. |
| WhatsApp / Telegram | Sin cambio (A.2). |

### A.4 Propuesta mínima (no implementada)

Hoy la flag **ya** apaga el invitado solo en los canales propios (portal y, en teoría, app) y no toca WhatsApp ni Telegram. El cambio mínimo es:

1. **Configuración**: en producción, `PORTAL_ALLOW_GUEST=false` explícito o la variable sin definir (con `APP_ENV=production` el default ya es `false`). No hace falta tocar backend ni motor.
2. **UI del portal**: dejar de mostrar el botón cuando la flag está apagada. Opciones de menor a mayor alcance:
   - (a) Exponer un booleano de solo lectura (por ejemplo `portal_allow_guest`) en `GET /api/v1/public/branding` (`app/api/v1/branding.py`, que no es parte del motor de Eko) y condicionar el botón y la leyenda de `portal/page.tsx:449-459`.
   - (b) Una variable de build `NEXT_PUBLIC_*` en el frontend. Tiene un riesgo: puede desalinearse de la flag del backend.
3. **Mensaje de error**: reemplazar el detalle 401 que expone `/api/v1/portal/auth/start` por un texto para el abonado (en `portal.py:672-673` o capturándolo en `onGuest`).
4. **App**: nada que cambiar.

### A.5 Tests y scripts que tocan el invitado

| Archivo:línea | Qué prueba | Con la flag en `false` |
|---|---|---|
| `tests/test_auth_hardening.py:96` `test_portal_guest_sets_httponly_cookie` | Cookie HttpOnly del invitado | Depende del default `true` |
| `tests/test_auth_hardening.py:109` `test_portal_guest_no_identifica_por_dni` | El invitado no se identifica por DNI | Depende del default `true` |
| `tests/test_auth_hardening.py:119` `test_portal_guest_bloqueado_cuando_allow_guest_false` | 401 con la flag en `false` (monkeypatch) | Es el test de la flag |
| `tests/test_portal_abonado.py:50` `test_portal_session_guest` | Sesión invitado | Depende del default `true` |
| `tests/test_portal_abonado.py:162` `test_portal_guest_mensaje_deuda_no_500` | Mensaje de deuda como invitado | Depende del default `true` |
| `tests/test_qa_n1_anti_ticket.py:30` `_guest_portal()` | Helper; **definido pero sin llamadas** en el archivo | — |
| `tests/test_qa_n1_anti_ticket.py:1214` `test_visitante_portal_deriva_sin_ticket_n2` | El visitante del portal se deriva sin ticket N2 | Depende del default `true` |
| `tests/conftest.py:12` | `APP_ENV=development` → la flag queda en `true` en los tests | — |
| `scripts/verify-production.sh:59-68` | Reporta el HTTP del invitado (espera 401 en prod endurecida) | — |
| `scripts/fase1-smoke-batan.sh:89,118` | Smoke que **usa** el invitado | Falla o queda inválido |
| `qa_bot/smoke_fase_c.py:50-62`, `qa_bot/runner_api.py`, `qa_bot/run_qa.py` | Smoke de UI y API con el CTA de visitante | Falla con aviso explícito |

Docs relacionados: `docs/SECURITY-HARDENING.md:16,52`, `docs/FASE-C.md:37`, `docs/FASE-1-BATAN.md:55`.

---

## B. Oficina Virtual: modo `authenticated` o `public`

### B.1 Dónde se decide

| Paso | Archivo:línea |
|---|---|
| Endpoint | `app/api/v1/portal.py:1102-1117` → `evaluar_ov_links_portal` |
| Agregado de los 3 links (`pay`, `invoice`, `payment_slip`) | `app/services/portal_ov_links.py:35-38`, `:66-` |
| Decisión por link | `app/services/ov_handoff.py:298-412` (`resolve_handoff`) |
| `authenticated` del payload = **los 3** links en modo autenticado | `app/services/portal_ov_links.py:147` |
| Si no, `status="partial"` / `mode="public"` / hint “ahí vas a identificarte” | `portal_ov_links.py:158-167`, texto en `:28-31` |

Lógica de `resolve_handoff` (`ov_handoff.py`):
1. Intent fuera de la allowlist → `failed`, sin URL (`:308-318`).
2. Sin abonado, abonado ambiguo (varias cuentas por teléfono) o sin DNI válido → `public` (`:325-351`; `identity_reason` en `:153-165`).
3. Con `handoff_v2` activo → `POST /ov/handoff` a JSAT (`request_ov_handoff`, `:215-284`; exige además `ov_configurado`: `enabled` + `api_url` + `user` + `password`, `app/services/ov_batan.py:106-113`):
   - `OK` y host en la allowlist (`ov.batan.coop` + host de `public_url`, `:177-198`) → **`authenticated`** con `handoff_url` y `expires_in` (default 60 s, `:65`).
   - Host no permitido → `public` (`:367-380`).
   - Error de JSAT → `public` (o `failed` si el destino está prohibido) (`:388-401`).
4. Sin `handoff_v2` → **`public`** siempre (`:403-412`).

URL pública: `{public_url}/#/{destino}`, con destinos `pagar`, `my` (factura) y `talon-de-pago` (`ov_batan.py:72-80`, `ov_handoff.py:38-47`).

### B.2 Configuración (solo nombres) y defaults

| Config | Default en código | Archivo:línea |
|---|---|---|
| `OV_HANDOFF_V2` | `false` | `app/config.py:325` |
| `OV_BATAN_ENABLED` | `false` | `app/config.py:314` |
| `OV_BATAN_PUBLIC_URL` | `https://ov.batan.coop` | `app/config.py:308-311` |
| `OV_BATAN_API_URL`, `OV_BATAN_API_USER`, `OV_BATAN_API_PASSWORD`, `OV_BATAN_TIMEOUT` | URL de API / vacíos / 20 s | `app/config.py:304-313,321` |
| Override por Admin (DB): `ov_batan.handoff_v2`, `public_url`, `enabled`, etc. | Se mezcla sobre el env; si la env `OV_HANDOFF_V2` es `true`, **gana** | `app/services/platform_settings.py:499-545`; UI en `frontend/src/components/admin/PlatformSettingsPanel.tsx:95,163,221` (pestaña “Oficina Virtual”) |
| Nota de producto en el default | “POST /ov/handoff (handoff_v2) queda off hasta que JSAT lo publique” | `platform_settings.py:172-177`; docstring `ov_handoff.py:3-9`, comentario `:403-404` |

**Default efectivo: `public`.** El valor real de producción depende del `.env` y de la configuración guardada en la DB desde Admin, así que **no se puede determinar leyendo el código**.

### B.3 Qué pasa al tocar “Pagar”

| Modo | Qué recibe la app | Qué pasa |
|---|---|---|
| `authenticated` | `url` = `handoff_url` de JSAT; `authenticated: true`; `status: "ready"` | `Linking.openURL` (`mobile/src/ui/BalanceCard.tsx:51-53`) abre la OV con la sesión que crea JSAT. Sin el aviso de identificación (`BalanceCard.tsx:89`). **Riesgo:** el TTL por defecto es 60 s y el payload del portal no expone `expires_in` (`portal_ov_links.py:138-145`); el link se genera al cargar Inicio (vía `customer-summary`), así que puede estar vencido cuando se toca. |
| `public` | `url` = `https://…/#/pagar`; `authenticated: false`; `status: "partial"` | Se abre la OV pública en el navegador. La app muestra “Estos accesos abren la oficina virtual. Ahí vas a identificarte (DNI o usuario); no es una sesión ya abierta.” (`BalanceCard.tsx:89-93`). El abonado se identifica de nuevo en la OV. |
| `failed` / `unavailable` | `url: null`, `available: false` | No se muestra el botón. Aparece “No pudimos obtener el acceso ahora.” (`BalanceCard.tsx:104-108`) y queda “Resolver con Eko”. |

Tests: `tests/test_ov_handoff.py` (por ejemplo `:151` `test_ov3_14_authenticated_only_jsat_v2`, `:174` `test_ov3_15_16_public_not_ready`, `:301` `test_ov3_23_legacy_tsid_no_es_authenticated`) y `tests/test_portal_ov_links.py` (`:102` ready, `:138` partial, `:180` público sin credenciales, `:202` unavailable).

---

## C. Notas del agente al abonado

### C.1 Qué las habilita

Una nota visible para el abonado es un `TicketEvent` con `tipo="nota"` y `visible_cliente="Sí"`, que crea `emit_ticket_customer_note` (`app/services/eko_ticket_proactive.py:173-240`). Hay **dos caminos** con condiciones distintas:

| Camino | Condición | Archivo:línea |
|---|---|---|
| **Agente desde la API de consola**: `POST /api/v1/tickets/{id}/events` con `interno: false` | Sesión de consola del tenant (`get_tenant_context`); el ticket debe existir en la org. **No depende de ninguna flag del runtime** (`agent_authorized=True`). Se audita con `log_audit(accion="ticket_nota")` | `app/api/v1/tickets.py:399-450` (rama `else`, `:426-439`) |
| **Eko (N1) por chat** (acción `ticket_customer_note`) | `ACTION_RUNTIME_ENABLED=true` (default `false`) **y** `ticket_customer_note` en `ACTION_RUNTIME_ACTIONS` (está en el set por defecto si la variable está vacía). Además, el ticket tiene que pertenecer al abonado | Gate: `app/services/eko_action_bridge.py:35-43`; defaults: `app/config.py:194-226`; ejecución: `app/services/eko_action_runtime.py:1283-1372` |

**En la consola actual (UI) el agente no puede crear notas visibles:** las tres llamadas de `SupportSidebar` usan `addTicketNote(d, true)`, es decir `interno=true` → `nota_interna`, `visible_cliente="No"` (`frontend/src/components/soporte/SupportSidebar.tsx:726,772,807`; default `interno = true` en `frontend/src/contexts/AppContext.tsx:522`). El camino “agente → abonado” existe en la API pero no en la UI.

Con `ACTION_RUNTIME_ENABLED=true`, el camino N1 permite que **el abonado** agregue una nota a su propio ticket desde el chat (autor abonado: “Self-note → no push”, `eko_ticket_proactive.py:191`). Esto corrige en parte el “no hay endpoint para que el abonado responda” del inventario principal (§5.4): no hay endpoint REST, pero sí hay un camino conversacional condicionado por la flag.

### C.2 Dónde se ven en la app

- Backend: `GET /api/v1/portal/tickets/{id}` devuelve `eventos` filtrados por `is_portal_customer_event` (`app/api/v1/portal.py:1160`, `_portal_ticket_eventos_out`). Ese filtro deja pasar `visible_cliente` ∈ {sí, si, yes, true, 1} y `tipo` ∈ {`creacion`, `nota`, `sla_breach`}, más `actualizacion` solo si el estado es `Cerrado` (`eko_ticket_proactive.py:63,85-95`). Máximo 800 caracteres, título fijo “Actualización” (`:64-65`).
- App: pestaña **Actividad**, detalle del reclamo, bloque **“Novedades”**: título (o “Actualización”), detalle y fecha de cada evento (`mobile/src/screens/ActivityScreen.tsx:185-200`).
- El portal web no muestra tickets.

---

## D. Wi‑Fi por integración

**Hallazgo que corrige el inventario principal (§5.4 d):** no hay endpoint REST de Wi‑Fi para la app, pero **sí existe escritura de Wi‑Fi en el código, vía BCM/TR‑069, y está cableada al chat de Eko** (`app/services/wifi_bcm.py`, llamada desde `app/services/canal_abonado.py:2150-2193`). Hoy el botón “Cambiar Wi‑Fi” de la app (`mobile/src/ui/ServicesSection.tsx:73-120`) abre ese flujo conversacional.

### D.1 Tabla capacidad × proveedor

Estados: **código** = existe en código · **doc** = documentada en el repo · **no** = no existe · **n/d** = no determinable leyendo el código.

| Capacidad | BCM (FTTH, Sopnet) | UISP (radio) | PPPoE / Radius | ACS / TR‑069 directo | BillTrack / JSC |
|---|---|---|---|---|---|
| Leer SSID | **no** (`EstadoOnuBcm` no tiene campo Wi‑Fi, `app/bcm/contract.py:35-53`); n/d si el JSON crudo (`raw`) lo trae | **no** (`EstadoCpeUisp`, `app/uisp/contract.py:13-30`) | **no** (`app/radius/client.py`: solo NAS/sesión PPP) | **no** (no hay cliente ACS/GenieACS en el repo) | **no** |
| Leer banda / canal | **no** | **no** | **no** | **no** | **no** |
| Leer clientes conectados | **no** | **no** | **no** | **no** | **no** |
| Leer estado del equipo (no Wi‑Fi) | **código**: online, serial, modelo, MAC, OLT, PON, rx/tx dBm, calidad óptica (`contract.py:35-53`; `GET /cliente/obtenerPorNumeroCliente`, `app/bcm/client.py:815-823`) | **código**: online, modelo, MAC, sitio, AP, señal dBm, uptime (`uisp/contract.py:13-30`; `GET /devices`, `uisp/client.py:241-252`) | **código**: sesión PPPoE, NAS, recursos del NAS (`radius/client.py:205-309`) | **no** | — |
| Cambiar clave Wi‑Fi | **código + doc**: `POST /tr/modificarWifiPasswordPorSerialNumber` y `…PorUserRadius`, por banda (`wifi=2` = 2.4 GHz, `wifi=5` = 5 GHz) o ambas (`app/bcm/client.py:1-9,901-944,991-998,1007-1050,1097-`); flujo de Eko `wifi_bcm._aplicar_password` (`app/services/wifi_bcm.py:723-752`) | **no** (cliente solo GET, `uisp/client.py:232-235`) | **no** | Solo a través de BCM (`/tr/*` de Sopnet); **no** hay acceso directo | **no** |
| Cambiar SSID | **código + doc**: `POST /tr/modificarWifiSSIDPorSerialNumber` y `…PorUserRadius` (`client.py:946-989,1052-1095,999-1006,1105-`); `wifi_bcm._aplicar_ssid` (`wifi_bcm.py:754-781`) | **no** | **no** | Solo vía BCM | **no** |
| Reiniciar equipo | **no** (no hay método ni endpoint; “reinicio” en el repo es una indicación al abonado: `docs/ENTRENAMIENTO-N1.md:67`, playbooks) | **no** | **no** | **no** | **no** |

Documentación del Wi‑Fi BCM: docstring de `app/bcm/client.py:1-9` y `app/services/wifi_bcm.py:1-19`; `docs/LOGS-SIN-SECRETOS.md` (incidente H28 y pendiente sobre params en la query); `docs/EKO-2.6-PRODUCT-CAPABILITY-GAP-DISCOVERY.md:57`; `docs/AUDIT-CONVERSACIONAL-2026-10.md:46,76`.

### D.2 Reglas actuales del flujo BCM (`app/services/wifi_bcm.py`)

| Regla | Archivo:línea |
|---|---|
| Solo con abonado identificado; el motor devuelve `None` si no lo hay | `canal_abonado.py:2166-2167`, docstring `wifi_bcm.py:3-4` |
| Solo FTTH; si no hay servicio FTTH → guía local | `wifi_bcm.py:580-610` (`no_ftth`) |
| BCM tiene que estar habilitado y configurado (`BCM_ENABLED`, default `false`, o el override de Admin) | `app/services/conexion_bcm.py:25-40`, `app/config.py:290` |
| Equipo destino resuelto **solo** desde BillTrack/BCM del abonado (serial ONU, si no hay, login Radius); nunca desde un id pegado en el chat. Con varios servicios FTTH, el abonado elige | `wifi_bcm.py:5-9,580-721` |
| Misma clave o SSID en ambas bandas | `wifi_bcm.py:15-16` |
| Validación: clave WPA2 de 8–63 caracteres sin saltos ni tabs; SSID de 1–32 | `wifi_bcm.py:296-312` |
| **Confirmación explícita** antes de cada escritura (“sí/dale/confirmo”…); negativa o ambigua → no ejecuta | `wifi_bcm.py:248-293`; tests `tests/test_wifi_bcm.py:549,573` |
| Valor pendiente solo en memoria del proceso, TTL 300 s | `wifi_bcm.py:49,53-57,179-208` |
| Ejecución única concurrente (in‑flight 60 s) y **cooldown 30 s** | `wifi_bcm.py:50-51,210-238,793-813` |
| La clave no se guarda en `contexto` (lista de claves prohibidas) | `wifi_bcm.py:145-173`; test `tests/test_wifi_bcm.py:592` |

---

## E. Seguridad para cambiar nombre y clave de Wi‑Fi desde la app

| Mecanismo | ¿Existe hoy? | Dónde | ¿Reutilizable para Wi‑Fi desde la app? |
|---|---|---|---|
| Identidad del abonado por JWT portal (`identified`, `dni`, `abonado_id`) | Sí | `_portal_auth`, `_abonado_portal_identificado` (`app/api/v1/portal.py`) | Sí: es la misma base que usan `/portal/invoices`, `/portal/tickets`, etc. Nunca acepta un selector de identidad por query (`portal.py:1132-1140`) |
| Resolución del equipo solo desde el padrón del abonado | Sí | `wifi_bcm.resolver_destino_wifi_bcm` (`wifi_bcm.py:580-721`) | Sí, es independiente del canal |
| Re‑autenticación / step‑up (pedir PIN u OTP antes de una acción sensible) | **No** | No hay endpoint para verificar el PIN sobre una sesión abierta. `set-pin` cambia el PIN **sin pedir el actual ni un OTP** (`portal.py:633-655`) | No existe: habría que crearlo. Las piezas existen: `verify_pin` / `hash_pin` (`app/estate/security.py`, usadas en `portal.py:572,651`) y el OTP de `auth/start` |
| OTP | Sí, **solo por email**: 6 dígitos (`OTP_LENGTH`), TTL 10 min (`OTP_TTL_MINUTES`), máx. 5 intentos (`OTP_MAX_ATTEMPTS`); se guarda hasheado | `portal.py:396-427,453-470`; `app/config.py:140-142` | Parcial: el desafío está atado al login (`PortalOtpChallenge` por DNI). Para usarlo como step‑up habría que separarlo del flujo de ingreso |
| Bloqueo por intentos fallidos (login portal) | Sí: `AUTH_LOGIN_MAX_FAILURES` (5) en `AUTH_LOGIN_WINDOW_MINUTES` (15) → bloqueo `AUTH_LOCKOUT_MINUTES` (30), por actor + IP; respuesta 429 | `app/services/auth_security.py:26-118`; `portal.py:360-364,556-557`; `app/config.py:153-155` | Sí, la tabla es genérica por `superficie` |
| Límite de frecuencia del cambio de Wi‑Fi | Sí, pero **solo en memoria del proceso**: cooldown 30 s e in‑flight 60 s | `wifi_bcm.py:50-51,210-238` | Parcial: con `--workers 2` en systemd (`deploy/systemd/operations-hub-api.service:14`), cada worker tiene su propio estado. No sobrevive a reinicios |
| Confirmación explícita antes de escribir | Sí (texto conversacional) | `wifi_bcm.py:248-293` | Como patrón sí; en una pantalla sería un paso de confirmación de UI |
| Auditoría | **Parcial**. `log_audit` (tabla `AuditEvent`) existe y se usa, por ejemplo, para notas de ticket (`app/estate/audit.py:10-29`; `tickets.py:440-447`), y `record_login_event` para los ingresos. **El cambio de Wi‑Fi no escribe auditoría**: solo `logger.info` con estado, tipo de destino, destino truncado y bandas (`wifi_bcm.py:742-750,771-`) | — | Sí: `log_audit` es reutilizable tal cual |
| Redacción de secretos en logs | Sí. Filtro global que enmascara `password`/`clave`/`token`/`secret`/etc. en todas las líneas, trazas y Sentry (`app/log_redaction.py:35-150`, instalado en `main.py:54`); `redactar_params_sensibles` en BCM (`app/bcm/client.py:407-433`); política en `docs/LOGS-SIN-SECRETOS.md`; test `tests/test_log_redaction.py` | — | Sí |
| La clave Wi‑Fi viaja en la **query string** hacia BCM | Hecho (riesgo) | `_request_post` usa `http.post(url, params=params)` (`app/bcm/client.py:841-854`); documentado como pendiente en `docs/LOGS-SIN-SECRETOS.md` (“Pendiente”) | Condiciona: la clave puede quedar en logs de proxies o del lado de Sopnet, fuera del alcance del filtro local |
| La clave tipeada en el chat queda guardada como mensaje | Hecho (riesgo) | El mensaje entrante se guarda con `texto` crudo (`app/services/canal_abonado.py:5771-5778`); no se encontró enmascarado de la clave antes de guardar. Esos mensajes se ven en la Bandeja | Una pantalla dedicada con un endpoint propio evitaría que la clave pase por `MensajeCanal` |
| Revocación de sesión (denylist de JTI) | Sí | `auth_security.py:121-145` | Sí |

---

## Correcciones al inventario principal

Este anexo no modifica `docs/AUDIT-APP-PORTAL-2026-10.md`. Quedan por corregir allí:

1. §5.4 (d) Wi‑Fi: “**No existe**” → “**Existe parcial**: escritura de clave y SSID vía BCM/TR‑069 solo para FTTH y solo por chat con Eko; no hay endpoint REST ni lectura de Wi‑Fi”.
2. §5.4 (c) Reclamos: el abonado puede agregar una nota a su ticket por chat si `ACTION_RUNTIME_ENABLED=true` (C.1). No hay endpoint REST.
3. §9 punto 14: lo mismo sobre Wi‑Fi y notas.

---

## Preguntas abiertas

1. Valor real en producción de `PORTAL_ALLOW_GUEST`, `OV_HANDOFF_V2` / `ov_batan.handoff_v2` (DB), `BCM_ENABLED` / config BCM de Admin y `ACTION_RUNTIME_ENABLED`. Están en el `.env` y en la configuración guardada en la DB; no se leyeron.
2. ¿JSAT ya publica `POST /ov/handoff`? El código dice que no (`platform_settings.py:175`), sin fecha.
3. ¿La API de BCM/Sopnet acepta los params de `/tr/*` en el body o la autenticación por header? Está pendiente en `docs/LOGS-SIN-SECRETOS.md`.
4. ¿El JSON crudo de BCM (`raw` de `obtenerPorNumeroCliente`) trae SSID o datos de Wi‑Fi? No se puede saber sin una respuesta real o la documentación de Sopnet.
5. ¿La consola debe permitir notas visibles al abonado? La API lo permite y la UI no lo ofrece (C.1).
