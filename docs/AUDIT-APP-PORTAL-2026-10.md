# Auditoría de solo lectura — App móvil, Portal y Panel (2026-10)

**Fecha:** 2026-10-08 · **Rama:** `main` (`ea400fa`) · **Tag de referencia Eko:** `eko-estable-2026-10`
**Alcance:** inventario de hechos para rediseñar `mobile/`, el portal (`frontend/src/app/portal`) y el panel (`frontend/src/app/(dashboard)`). No se modificó código. No se leyó ningún `.env`. Los servicios de Eko (`app/services/*`) se citan solo como origen de datos de un endpoint.

**Método:** lectura de archivos y extracción de rutas de FastAPI por AST (decoradores `@router.<método>` en `app/api/v1/*.py`, `app/routers/*.py` y `main.py`). Los conteos de uso del front salen de `grep` sobre `api.<método>(` / `.<método>(`.

> Aviso: `mobile/CURRENT_STATE.md` (2026-09-15) dice que no hay navegación, hooks ni componentes. **Está desactualizado**: hoy existen `src/navigation/`, `src/hooks/` y `src/ui/` (ver §1). `mobile/README.md` tampoco lista los endpoints de tickets, conectividad, facturas ni resumen.

---

## 1. App móvil (Expo) — `mobile/`

### 1.1 Identidad y versiones

| Dato | Valor | Archivo |
|---|---|---|
| Nombre visible | `EKO-Asistente` | `mobile/app.json` |
| Paquete npm / slug | `soporte-batan` | `mobile/package.json`, `mobile/app.json` |
| Versión | `1.0.6`; Android `versionCode` 15 | `mobile/app.json` |
| Bundle / package | `coop.batan.soporte` (iOS y Android) | `mobile/app.json` |
| Expo SDK | `expo ~54.0.0` | `mobile/package.json` |
| React Native / React | `0.81.5` / `19.1.0` | `mobile/package.json` |
| New Architecture | `newArchEnabled: false` | `mobile/app.json` |
| Tema del sistema | `userInterfaceStyle: "dark"` (fijo) | `mobile/app.json` |
| Orientación | `portrait`; `supportsTablet: false` | `mobile/app.json` |
| Plugins | `expo-notifications` (canal `eko`), `expo-av` (permiso de micrófono) | `mobile/app.json` |
| Scheme | `soportebatan` (no hay manejo de deep links por URL en el código) | `mobile/app.json` |

### 1.2 Librerías

| Uso | Librería | Nota |
|---|---|---|
| UI | Solo primitivas de React Native + `react-native-safe-area-context` | No hay kit de UI externo; los componentes propios están en `src/ui/` |
| Navegación | **Ninguna** | Pestañas hechas a mano en `src/navigation/AppShell.tsx` |
| Estado | **Ninguna** (sin Context, Redux, Zustand ni React Query) | Hooks propios en `src/hooks/` + estado elevado a `App.tsx` |
| Almacenamiento seguro | `expo-secure-store` | `src/session.ts` |
| Push | `expo-notifications` | `src/push.ts`, `src/pushIncidente.ts` |
| Voz | `expo-av` | `src/hooks/useVoiceRecorder.ts`, `src/ui/VoiceRecorder.tsx` |
| Config | `expo-constants` | `src/config.ts` |
| Tipografías | Ninguna personalizada (fuente del sistema) | `src/theme.ts` |

### 1.3 Estructura de carpetas

```
mobile/
├── App.tsx                 # raíz: arranque, sesión, PIN, push y AppShell
├── index.ts                # registerRootComponent
├── app.json · eas.json · babel.config.js · tsconfig.json
├── google-services.json    # (no leído)
├── assets/                 # icon.png, adaptive-icon.png, splash.png
├── scripts/                # verify-*.mjs (pruebas sin framework, §8)
└── src/
    ├── api.ts              # cliente HTTP (fetch)
    ├── config.ts           # API_BASE, ORG_SLUG, X-Canal, PRIVACY_URL
    ├── session.ts          # SecureStore: token, conv_id, pista de DNI
    ├── errors.ts           # formatUserError / isAuthExpired
    ├── theme.ts            # tokens (colores, espaciado, radios, tipografía, tamaños)
    ├── types.ts            # contratos de respuesta
    ├── present.ts · invoicesView.ts   # helpers de presentación / view-model de facturas
    ├── push.ts · pushIncidente.ts     # registro y parseo de push
    ├── navigation/AppShell.tsx
    ├── hooks/   (11)       # useSession, useConversation, useTickets, useConnectivity,
    │                       # useCustomerSummary, useInvoices, useCreateClaim, useVoiceRecorder,
    │                       # useOvLinks*, useServices*   (* sin uso, ver §9)
    ├── screens/ (5)        # Auth, Home, Chat, Activity, Account
    └── ui/      (27)       # componentes reutilizables
```

### 1.4 Navegación

Sin librería. Máquina de estados en `App.tsx`:

```
booting (spinner)
 ├─ error de arranque sin sesión → pantalla “Sin conexión” (Reintentar / Ingresar de nuevo)
 ├─ sin sesión → AuthScreen
 ├─ pinGate (has_pin === false tras OTP) → PinSetup a pantalla completa
 └─ con sesión → AppShell (4 pestañas)
```

Pestañas en `src/navigation/AppShell.tsx` (`TABS`): **Inicio** (`home`), **Eko** (`eko`), **Actividad** (`activity`), **Cuenta** (`account`). Las cuatro vistas se montan superpuestas y se ocultan con `display: "none"`; Chat y Actividad solo se montan cuando están activas. Un push puede cambiar la pestaña y enfocar un ticket (`applyIntentNavigation` en `App.tsx`).

### 1.5 Pantallas

| Pantalla | Archivo | Qué hace | Hooks / datos |
|---|---|---|---|
| Arranque | `App.tsx` | Carga branding y sesión; valida la conversación | `useSession` → `api.branding`, `api.conversation` |
| Ingreso | `src/screens/AuthScreen.tsx` | Modo `pin` (DNI + PIN) o `dni` (primera vez: DNI → OTP); enlace a privacidad | `api.authStart`, `api.authVerify`, `api.loginPin` |
| Crear PIN (bloqueante) | `App.tsx` + `src/ui/PinSetup.tsx` | Se puede omitir | `api.setPin` |
| Inicio | `src/screens/HomeScreen.tsx` | Saludo, saldo + accesos a la OV, cabeceras de facturas, plan/estado, servicios, conectividad, formulario de reclamo, acciones rápidas, “Hablar con Eko” | `useCustomerSummary`, `useInvoices`, `useConnectivity`, `useCreateClaim` |
| Eko (chat) | `src/screens/ChatScreen.tsx` | Chat, avisos de derivación a agente, CSAT, voz | `useConversation` (`send`, `sendAudio`, consulta periódica) |
| Actividad | `src/screens/ActivityScreen.tsx` | Lista de reclamos y detalle con eventos; foco por push | `useTickets` (`listTickets`, `getTicket`) |
| Cuenta | `src/screens/AccountScreen.tsx` | Crear/cambiar PIN, privacidad, cerrar sesión, borrar datos | `api.setPin`, `api.deleteAccount` |

Componentes en `src/ui/`: `Avatar`, `Badge`, `BalanceCard`, `Banner`, `Button`, `Card`, `ChatComposer`, `ChatHeader`, `ConnectivityCard`, `CreateClaimForm`, `CsatBar`, `EmptyState`, `InvoiceHeadersSection`, `MessageBubble`, `MessageText`, `PinSetup`, `QuickAction`, `Screen`, `SectionHeader`, `ServiceCard`, `ServicesSection`, `StatusRow`, `TabGlyph`, `Text`, `TextField`, `TicketCard`, `VoiceRecorder`.

### 1.6 Autenticación

| Flujo | Pasos | Archivo |
|---|---|---|
| Primera vez | DNI → `POST /portal/auth/start` (OTP al contacto, se devuelve enmascarado) → OTP → `POST /portal/auth/verify` → si `has_pin === false`, pantalla Crear PIN → `POST /portal/auth/set-pin` | `AuthScreen.tsx`, `App.tsx` |
| Habitual | DNI + PIN → `POST /portal/auth/login-pin` | `AuthScreen.tsx` |
| Sesión | Respuesta `AuthPayload` (`portal_token`, `conversacion`, `mensajes`, `has_pin`). El token y `conv_id` se guardan en SecureStore; la pista de DNI se conserva al cerrar sesión | `src/session.ts` |
| Expiración | `isAuthExpired(err)` → `onExit` → vuelve a Auth | `src/errors.ts`, hooks |
| Borrar datos | `POST /portal/account/delete` | `AccountScreen.tsx` |

Modo de OTP del backend: `PORTAL_AUTH_MODE` (por defecto `dni_otp`) en `app/config.py:66`.

### 1.7 Comunicación con el backend

- `src/api.ts`: `fetch` nativo con timeout de 25 s (60 s para audio); error tipado `ApiError(message, status)`; lee `detail` de FastAPI.
- Base: `EXPO_PUBLIC_API_URL` → `extra.apiUrl` → `https://ibot.ecolan.com` (`src/config.ts`). **La app apunta al host de la consola**, no a `soporte.ecolan.com`.
- Encabezados: `Authorization: Bearer <portal_token>` y `X-Canal: app` en todas las llamadas.
- Consulta periódica del chat: `setInterval` en `src/hooks/useConversation.ts:51`.
- Branding: `GET /api/v1/public/branding` con valores por defecto si falla (`defaultBranding` en `src/theme.ts`).

---

## 2. Portal web (Next.js) — `soporte.ecolan.com`

### 2.1 Stack

| Dato | Valor | Archivo |
|---|---|---|
| Next.js / React | `16.2.7` / `19.2.4` | `frontend/package.json` |
| Estilos | Tailwind CSS v4 (`@tailwindcss/postcss`) + CSS propio | `frontend/postcss.config.mjs`, `frontend/src/app/globals.css` |
| Router | App Router (`src/app/`) | — |
| Salida | `output: "standalone"` | `frontend/next.config.ts` |

El portal y el panel son **la misma aplicación Next.js**. La separación por host está en `src/middleware.ts` + `src/lib/public-hosts.ts`:
- En `soporte.ecolan.com`, `/` se reescribe a `/portal`; las rutas de consola redirigen (308) al host de consola.
- En `ibot.ecolan.com`, `/portal` y `/privacidad` redirigen al host del portal.
- Sin `NEXT_PUBLIC_CONSOLE_HOST` / `NEXT_PUBLIC_PORTAL_HOST` el middleware no interviene (un solo origen).

### 2.2 Rutas públicas

| Ruta | Archivo | Contenido |
|---|---|---|
| `/portal` (raíz en el host del portal) | `src/app/portal/page.tsx` (653 líneas, un solo componente) | Ingreso + chat con Eko |
| `/privacidad` | `src/app/privacidad/page.tsx` | Política de privacidad (enlazada desde la app y Play Store) |
| `/` | `src/app/page.tsx` | Redirección de servidor a `/login` (en el host del portal la reescribe el middleware) |

### 2.3 Componentes que usa el portal

`StatusBadge`, `ChatMessageBubble` / `ChatTypingIndicator` / `SendIcon`, `StarRatingInput` (CSAT), `ThemeToggle`, `EkoAvatar` (todos en `src/components/ui/`), `useStickToBottom` (`src/hooks/`), `getBranding` / `botEstadoLabel` / `portalAssistantLine` (`src/lib/brand.ts`).

### 2.4 Ingreso

Estados en `portal/page.tsx`: `step: "auth" | "otp" | "chat" | "pin-setup"`; `mode: "dni" | "pin" | "guest"`.

| Modo | Endpoint | Nota |
|---|---|---|
| DNI + OTP | `POST /portal/auth/start` → `POST /portal/auth/verify` | Tras verificar sin PIN pasa a `pin-setup` |
| DNI + PIN | `POST /portal/auth/login-pin` | — |
| Invitado (“No soy abonado / consulta general”) | `POST /portal/session` con `org_slug: "coop-batan"` fijo en el código | El backend lo habilita con `PORTAL_ALLOW_GUEST`; si no se define, queda **apagado en production** (`app/config.py:68-72`) |
| Sesión | Cookie HttpOnly `ops_portal_token`; en `sessionStorage` solo `convId` (`ops_hub_portal_session`) | Comentario en `portal/page.tsx:23` |
| Salida | `POST /portal/logout` | — |

En desarrollo, el portal muestra un DNI de demostración en pantalla (`showDemo`, `portal/page.tsx:19-21,463`).

### 2.5 Relación con Eko

El portal es **solo chat**. Envía texto (`POST /portal/messages`) y consulta la conversación cada 4 s mientras está en `espera_agente` / `con_agente` (`portal/page.tsx:131-137`). La CSAT se manda como mensaje con el número (`api.portalSend(String(n))`). **El portal no usa** saldo, facturas, OV, servicios, conectividad, reclamos ni push: esas pantallas existen solo en la app.

---

## 3. Panel (consola) — `ibot.ecolan.com`

### 3.1 Estructura

- Layout: `src/app/(dashboard)/layout.tsx` → `AuthGuard` + `BrandSync` (aplica `tenantContext.brand_color` a `--brand`) + `AppHeader` + `SidebarNav`.
- Estado global: `src/contexts/AppContext.tsx` (908 líneas: sesión, tenant, permisos `can()`, tickets, KB, chat del agente, telemetría, notificaciones) y `ThemeContext.tsx`.
- Ingreso: `src/app/login/page.tsx` (`POST /api/login`), `change-password`, `invite` (alta por invitación).
- Navegación: `src/components/layout/SidebarNav.tsx`, en dos grupos con permisos RBAC.

### 3.2 Módulos

| Módulo (ruta) | Permiso en el menú | Página → componente | Qué hace (según el código) |
|---|---|---|---|
| **Bandeja** (`/inbox`) | ninguno | `inbox/page.tsx` → `components/inbox/InboxPanel.tsx` | Conversaciones de todos los canales (App, Portal, WA, Telegram); filtros por estado y “solo mías”; tomar, liberar, asignar, responder y cerrar con nota; simular entrante; aviso sonoro (`lib/inboxSound.ts`) |
| **Consola** (`/soporte`) | ninguno | `soporte/page.tsx` → `ChatPanel` / `NocBoard` + `SupportSidebar` + `AgentConsole` | Mesa del agente sobre el ticket tomado: hilo del canal, plantillas de respuesta, borrador KB. Admin sin ticket ve `NocBoard` (“Prioridad operativa”) y `AgentConsole` (chat con el asistente interno `POST /api/v1/chat`) |
| **Cola** (`/tickets`) | `tickets.queue.view` | `tickets/page.tsx` → `TicketQueuePanel` o `SupervisorBoard`, + `AgentsTeamPanel`, `AgentSelfPanel` | Cola de tickets (filtros, tomar, reasignar, cierre masivo); el supervisor ve “Operación en vivo”; equipo y métricas propias |
| **Incidentes masivos** (`/incidentes`) | `outages.manage` | `incidentes/page.tsx` → `components/incidentes/IncidentesMasivosPanel.tsx` | Anunciar y resolver cortes; lista de NAS y su estado |
| **Conocimiento** (`/conocimiento`) | `kb.publish` | `conocimiento/page.tsx` → `components/kb/KnowledgeBasePanel.tsx` + `KbReviewTray.tsx` | Artículos (alta/baja), bandeja de revisión de contribuciones (aprobar/rechazar) |
| **Estadísticas** (`/estadisticas`) | `stats.global` / `stats.bot` / `stats.agents` / `stats.self` | `estadisticas/page.tsx` → `components/stats/StatsDashboard.tsx` | Ver §3.3 |
| **Administración** (`/admin`) | `orgs.manage` (y la página exige `isAdmin`) | `admin/page.tsx` → `components/admin/AdminPanel.tsx` | Pestañas: Cooperativas, Seguridad, Config (`PlatformSettingsPanel`: API IA, WhatsApp, Telegram, BillTrack, UISP, BCM, Oficina Virtual, Data Estate, Conocimiento, Playbooks), IA/LLM (`LlmMetricsPanel`), Roles |

Elementos comunes: `PendingTasksBell` (consulta periódica de bandeja y KB), `AvailabilityControl` (`PATCH /me/availability`), `ThemeToggle`.

### 3.3 Estadísticas: qué muestra y de dónde sale

| Bloque en `StatsDashboard.tsx` | Endpoint | Origen backend |
|---|---|---|
| Mi actividad (claims, cierres, chats activos, tickets abiertos/cerrados, % resolución) | `GET /api/v1/analytics/me` | `app/api/v1/analytics.py:me_analytics` |
| Satisfacción CSAT (total, promedio, Bot N1 vs Agentes, distribución) | `GET /api/v1/analytics/csat` | `app/services/encuesta_satisfaccion.build_csat_analytics` |
| Canal en vivo (en espera, con agente, bot, handoffs, cierres con nota, 1.ª respuesta) | `GET /api/v1/analytics/ops` | `app/estate/ops_analytics.build_ops_analytics` sobre `ConversacionCanal`, `MensajeCanal`, `Ticket`, `User`, `Organization` |
| Tickets N1/N2 (creados, cerrados, abiertos, % resolución, SLA vencido, breach al cierre), series, backlog | `GET /api/v1/analytics/ops` + `GET /api/v1/analytics/tickets` | `repo.ticket_stats` (`app/estate/repository.py`) |
| Equipo | `/analytics/ops` (y `AgentsTeamPanel` usa `/analytics/agents`) | `repo.agent_performance` |
| “Avanzado — lectura ejecutiva all-time (ilustrativo)” | `GET /api/v1/analytics/executive` | `app/estate/executive_analytics.py`: ranking de riesgo, evolución semanal, **horas ahorradas y escalaciones evitadas “estimadas”** |
| Exportar CSV | `GET /api/v1/analytics/export` | `analytics.py:export_analytics_csv` (requiere `reports.export` en el front) |

Todos los datos salen de PostgreSQL (Data Estate). Filtro por rango `desde`/`hasta`.

---

## 4. Diseño actual

### 4.1 Tokens

| Token | App (`mobile/src/theme.ts`) | Web (`frontend/src/app/globals.css`) |
|---|---|---|
| Marca | `brand #2298A6`, `brandDark #1b7a86` | `--brand #2298A6`, `--brand-dark #1A7985` (sobrescrito en el panel por `tenantContext.brand_color`) |
| Fondo oscuro | `bg #0B1220`, `card #111827`, `surface #0F172A`, `tabBar #0E1626` | `--background #020617`, `--ecolan-dark #0D1B2A`, superficies `rgba(15,23,42,…)` |
| Texto | `text #F8FAFC`, `muted #94A3B8` | `--foreground #e2e8f0`, `--text-muted #94a3b8`, `--text-dim #64748b` |
| Estados | `danger #F87171`, `amber #FBBF24`, `online #22C55E` | Clases Tailwind (`amber-400`, `emerald`, etc.) |
| Tema claro | **No existe** | `html[data-theme="light"]`: `--background #F4F7F6`, tarjetas blancas, **escala slate invertida** (`--color-slate-50…950`) |
| Tipografía | Del sistema; escala en `typography` (11 variantes, 12–28 px) | `--font-sans: ui-sans-serif, system-ui`; `--font-mono` |
| Espaciado | `xs 4 · sm 8 · md 12 · lg 16 · xl 24 · xxl 32` | Escala de Tailwind (sin tokens propios) |
| Radios | `sm 10 · md 14 · lg 16 · xl 20 · full 999` | Clases `rounded-xl` / `rounded-2xl`; `.enterprise-panel` 1rem |
| Tamaños | `hit 44`, `tab 52`, avatares 28/36/88 | — |
| Ancho máximo | `layout.maxContent 480` | Panel `max-w-[1600px]` |

### 4.2 Claro / oscuro

- App: solo oscuro (`userInterfaceStyle: "dark"`, `StatusBar light-content`).
- Web: oscuro por defecto; script en `src/app/layout.tsx` lee `localStorage['ops-hub-theme']`; `ThemeToggle` en `AppHeader`, `/login` y `/portal`. El claro funciona invirtiendo la escala slate y con reglas por clase (`globals.css:449+`).

### 4.3 Componentes repetidos y duplicaciones

| Concepto | App | Web | Comparten código |
|---|---|---|---|
| Burbuja de chat + links | `ui/MessageBubble.tsx`, `ui/MessageText.tsx` | `components/ui/ChatMessageBubble.tsx` (`linkifyText`, `renderMessageBody`) | No |
| CSAT | `ui/CsatBar.tsx` | `ui/StarRatingInput.tsx` | No |
| Avatar Eko | `ui/Avatar.tsx` (`assets/icon.png`) | `ui/EkoAvatar.tsx` (`public/eko-avatar.png`) | No |
| Botón / campo | `ui/Button.tsx`, `ui/TextField.tsx` | `ui/forms.tsx` (`Button`, `TextField`, `inputCls`) | No |
| Badge de estado | `ui/Badge.tsx` | `ui/StatusBadge.tsx` | No |
| Estado vacío | `ui/EmptyState.tsx` | `EmptyState` local en `StatsDashboard.tsx` | No |
| Cliente API + `ApiError` | `src/api.ts` | `src/lib/api-client.ts` | No (tipos duplicados en `mobile/src/types.ts` y `frontend/src/lib/types.ts`) |
| Branding | `theme.defaultBranding` + `api.branding()` | `lib/brand.ts` (`fetch` propio) + `api.publicBranding()` en `Providers.tsx` | No (dos llamadas al mismo endpoint en el web) |
| Flujo de ingreso del abonado | `AuthScreen.tsx` + `PinSetup.tsx` | Bloques en `portal/page.tsx` | No |
| Tokens de color | `theme.ts` (hex) | `globals.css` (variables CSS) + 40 hex sueltos en `.tsx` | No |

No hay paquete compartido entre `mobile/` y `frontend/`.

---

## 5. API

Backend: **143 rutas** en total (`app/api/v1/*` con prefijo `/api/v1`, `app/routers/*` con `/api/*`, `main.py`). Las rutas de `app/routers/tickets_router.py` y `chat_router.py` solo se montan con `ENABLE_LEGACY_API` (`main.py:196-199`).

Tipos de sesión (`app/api/v1/portal.py`, `deps.py`):
- **Portal**: `_portal_auth` → JWT `typ=portal` por `Bearer` o cookie.
- **Consola**: `get_tenant_context` / `obtener_usuario_requerido` / `requiere_admin` / `require_permiso(...)`.
- **Pública**: sin dependencia de sesión.

### 5.1 App móvil (19 endpoints)

| Método | Ruta | Para qué | Sesión | Uso en la app |
|---|---|---|---|---|
| GET | `/api/v1/public/branding` | Textos de marca | No | `useSession` |
| POST | `/api/v1/portal/auth/start` | Pedir OTP por DNI | No | `AuthScreen` |
| POST | `/api/v1/portal/auth/verify` | Validar OTP | No | `AuthScreen` |
| POST | `/api/v1/portal/auth/login-pin` | Ingreso con DNI + PIN | No | `AuthScreen` |
| POST | `/api/v1/portal/auth/set-pin` | Crear/cambiar PIN | Portal | `App.tsx`, `AccountScreen` |
| POST | `/api/v1/portal/account/delete` | Borrar datos de la app | Portal | `AccountScreen` |
| POST | `/api/v1/portal/messages` | Mensaje a Eko | Portal | `useConversation` |
| GET | `/api/v1/portal/conversations/{conv_id}` | Conversación + mensajes | Portal | `useSession`, `useConversation` |
| POST | `/api/v1/portal/audio` | Mensaje de voz | Portal | `useConversation` |
| POST | `/api/v1/portal/devices` | Registrar token de push | Portal | `push.ts` |
| DELETE | `/api/v1/portal/devices` | Dar de baja token de push | Portal | `push.ts` |
| GET | `/api/v1/portal/customer-summary` | Resumen: cliente, cuenta, servicios, saldo + OV, conectividad, tickets | Portal | `useCustomerSummary` (Inicio) |
| GET | `/api/v1/portal/invoices` | Cabeceras de facturas | Portal | `useInvoices` (Inicio) |
| GET | `/api/v1/portal/connectivity` | Estado de conexión (`?service_id=`) | Portal | `useConnectivity` (Inicio) |
| GET | `/api/v1/portal/tickets` | Lista de reclamos | Portal | `useTickets` |
| GET | `/api/v1/portal/tickets/{ticket_id}` | Detalle + eventos visibles | Portal | `useTickets` |
| POST | `/api/v1/portal/tickets` | Crear reclamo (`motivo`, `descripcion`) | Portal | `useCreateClaim` |
| GET | `/api/v1/portal/ov-links` | Links de la Oficina Virtual | Portal | Cliente definido; **hook `useOvLinks` sin uso** (los links llegan dentro de `customer-summary`) |
| GET | `/api/v1/portal/services` | Catálogo de servicios | Portal | Cliente definido; **hook `useServices` sin uso** (llegan dentro de `customer-summary`) |

### 5.2 Portal web (9 endpoints)

| Método | Ruta | Para qué | Sesión |
|---|---|---|---|
| GET | `/api/v1/public/branding` | Marca (`Providers.tsx` y `lib/brand.ts`) | No |
| POST | `/api/v1/portal/auth/start` | OTP | No |
| POST | `/api/v1/portal/auth/verify` | Validar OTP | No |
| POST | `/api/v1/portal/auth/login-pin` | DNI + PIN | No |
| POST | `/api/v1/portal/auth/set-pin` | Crear PIN | Portal |
| POST | `/api/v1/portal/session` | Sesión de invitado | No |
| POST | `/api/v1/portal/messages` | Mensaje a Eko (también CSAT) | Portal |
| GET | `/api/v1/portal/conversations/{conv_id}` | Consulta periódica | Portal |
| POST | `/api/v1/portal/logout` | Borrar cookie | No |

### 5.3 Panel (84 endpoints consumidos desde `frontend/src/lib/api-client.ts`)

Todos exigen sesión de consola, salvo los indicados como públicos.

| Área | Método y ruta | Permiso backend | Consumidor |
|---|---|---|---|
| Ingreso | `POST /api/login` (pública), `POST /api/logout`, `GET /api/me` | usuario | `AppContext` |
| Sesión/tenant | `GET /api/v1/tenants`, `GET /api/v1/session/context` | usuario / tenant | `AppContext` |
| Cuenta | `POST /api/v1/auth/change-password`, `PATCH /api/v1/me/availability` | usuario / `agent.availability` | `change-password`, `AvailabilityControl` |
| Invitaciones | `GET /api/v1/auth/invites`, `GET /api/v1/auth/invite/{token}` (pública), `POST /api/v1/auth/invite/accept` (pública), `GET /api/v1/auth/login-events` | `users.manage` / admin | `AdminPanel`, `invite/page` |
| Chat asistente interno | `POST /api/v1/chat` | tenant | `AppContext` |
| Tickets (13) | `GET /tickets`, `GET/PUT /tickets/{id}`, `POST /tickets/{id}/claim`, `POST /tickets/{id}/reassign`, `POST /tickets/bulk-close`, `GET /tickets/{id}/conversation`, `POST /tickets/{id}/events`, `GET /tickets/{id}/kb-draft`, `POST /tickets/{id}/publish-kb`, `GET /tickets/{id}/explain-escalation`, `GET /tickets/notifications`, `PUT /tickets/notifications/{id}/read` | tenant (`publish-kb`: proponente KB) | `AppContext`, `TicketQueuePanel`, `SupervisorBoard`, `ChatPanel`, `SupportSidebar`, `InboxPanel` |
| Bandeja (9) | `GET /inbox/conversations`, `GET /inbox/conversations/{id}`, `GET …/messages/{msg_id}/media`, `POST …/{id}/claim`, `…/release`, `…/messages`, `…/close`, `…/assign`, `POST /inbox/simulate` | tenant | `InboxPanel`, `ChatPanel`, `PendingTasksBell`, `ChatMessageBubble` (media) |
| Cortes (5) | `GET /nas`, `GET /nas/{shortname}/health`, `GET/POST /outages`, `PATCH /outages/{id}/resolve` | `outages.manage` | `IncidentesMasivosPanel` |
| KB (7) | `GET/POST /kb`, `DELETE /kb/{id}`, `GET/POST /kb/contributions`, `POST …/{id}/approve`, `POST …/{id}/reject` | tenant / revisor / proponente | `AppContext`, `KbReviewTray`, `PendingTasksBell` |
| Plantillas | `GET /response-templates` | tenant | `SupportSidebar` |
| Analytics (7) | `GET /analytics/tickets`, `/executive`, `/agents`, `/ops`, `/me`, `/csat`, `/export` | tenant (el front filtra por `stats.*`) | `StatsDashboard`, `AgentSelfPanel`, `AgentsTeamPanel` |
| Telemetría | `GET /telemetry`, `POST /telemetry/simulate` | tenant / `require_telemetry` | `AppContext` |
| Usuarios de la org | `GET/POST /org/users`, `PATCH /org/users/{id}` | tenant / `users.manage_agents` | `AgentsTeamPanel` |
| Admin (22) | `GET/POST /admin/organizations`, `DELETE /admin/organizations/{slug}`, `GET /admin/organizations/{slug}/users`, `PATCH …/users/{id}`, `POST …/users/{id}/reset-password`, `POST …/invites`, `GET /admin/audit`, `GET/PUT /admin/settings`, `POST /admin/settings/test-{ai,whatsapp,telegram,database,billtrack,uisp,bcm,ov-batan}`, `POST /admin/settings/telegram-webhook`, `POST /admin/playbooks/convert`, `GET /metrics/llm` | admin | `AdminPanel`, `PlatformSettingsPanel`, `LlmMetricsPanel`, `PlaybooksConsole` |
| RBAC | `GET /rbac/roles`, `GET /rbac/permissions` | usuario / admin | `AdminPanel` |
| Marca | `GET /api/v1/public/branding` | pública | `Providers` |

Métodos definidos en `api-client.ts` **sin consumidor**: `createAdminUser`, `createInvite`, `demoEscenarios`, `demoEvento`, `demoMetricas`, `demoReset`, `importUsersCsv`, `inboxAbonados`, `inboxMarkRead`, `prioritizedTickets`, `resetUserPassword`, `updateOrganization`.

Totales: **112 filas de endpoint por superficie** (19 + 9 + 84); **104 endpoints únicos** consumidos por al menos una superficie (branding y 6 endpoints de portal se repiten entre app y portal) sobre 143 rutas del backend.

### 5.4 Cobertura por capacidad

| Capacidad | Estado | Lo que hay | Lo que falta (según el código) |
|---|---|---|---|
| **(a) Factura y pagos** | **Existe parcial** | `GET /portal/customer-summary` (dominio `billing`: `balance.amount/currency/as_of/freshness` + `ov`), `GET /portal/invoices` (cabeceras: `invoice_number`, `full_type`, `amount`, `issued_at`, `status`), `GET /portal/ov-links` (`pay`, `invoice`, `payment_slip`). Solo en la app | Pago dentro de la app (no hay endpoint de pago); PDF de factura; vencimiento (el tipo dice “Sin vencimiento ni cuenta”, `mobile/src/types.ts:302`; `scripts/verify-invoices.mjs` verifica que no se agreguen pago, PDF ni vencimiento); historial de pagos; nada de esto en el portal web |
| **(b) Estado del servicio** | **Existe** (app) / **no existe** (portal web) | `GET /portal/connectivity` (`status`, `freshness`, `access_technology`, `incident`, `actions`, `needs_service_selection`, `reason_code`; TTL `PORTAL_CONNECTIVITY_TTL_SEC`), `customer-summary?connectivity=summary\|probe`, `GET /portal/services`; push de incidente que refresca la tarjeta | UI en el portal web; historial de estado |
| **(c) Reclamos con seguimiento** | **Existe** (app) / **no existe** (portal web) | `GET/POST /portal/tickets`, `GET /portal/tickets/{id}` con `eventos` filtrados por `is_portal_customer_event`; push `tipo=ticket` (`created/updated/resolved/sla_breached`, `src/pushIncidente.ts`) | Que el abonado responda o agregue información a un ticket existente (no hay endpoint portal); adjuntos; UI en el portal web |
| **(d) Wi‑Fi** | **No existe** | El botón “Cambiar Wi‑Fi” (`mobile/src/ui/ServicesSection.tsx:73-120`) abre Eko con un texto fijo | Cualquier endpoint de lectura o cambio de Wi‑Fi (no hay rutas que mencionen wifi/SSID en `app/api`) |
| **(d) Avisos** | **Existe parcial** | Push por Expo (`app/services/app_push.py` → `exp.host`), registro/baja en `/portal/devices`; eventos de incidente y ticket | Bandeja o historial de avisos en la app; preferencias u opt‑out por tipo (no hay endpoint); avisos en el portal web |

---

## 6. Pagos: cómo funcionan hoy

1. Inicio de la app → `useCustomerSummary` → `billing.balance` y `billing.ov` (`mobile/src/screens/HomeScreen.tsx`).
2. `BalanceCard` (`mobile/src/ui/BalanceCard.tsx`) muestra “Cuenta al día”, “Saldo a favor” o “Saldo pendiente” y un botón por cada link disponible: **Pagar** (`pay`), **Ver factura** (`invoice`), **Talón de pago** (`payment_slip`). “Pagar” es el botón principal si hay deuda.
3. Cada botón ejecuta `Linking.openURL(url)` → **abre la Oficina Virtual externa** en el navegador. Si `authenticated !== true`, se avisa que el abonado se identifica en la OV.
4. Backend: `app/services/portal_ov_links.py` → `ov_handoff.resolve_handoff` con modos `authenticated` / `public` / `failed`. El docstring dice: “Handoff de producto = hash público verificado (`ov.batan.coop/#/…`). El cliente se identifica en la OV.” No cachea links. Variables relacionadas: `OV_BATAN_PUBLIC_URL`, `OV_BATAN_API_URL`, `OV_BATAN_ENABLED`, `OV_HANDOFF_V2`.
5. También hay un botón “Resolver con Eko / Consultar con Eko” que manda un texto al chat.
6. **No hay integración de pago** (no hay endpoint de cobro, checkout ni confirmación). El portal web no muestra saldo ni botones de pago.

---

## 7. Deploy y build

| Superficie | Cómo se publica | Archivos |
|---|---|---|
| Backend | `git pull` → `pip install -r requirements.txt` → `systemctl restart operations-hub-api` (uvicorn, 2 workers, 127.0.0.1:8000); migraciones al arrancar | `DEPLOY.md`, `deploy/systemd/operations-hub-api.service`, `Dockerfile` |
| Portal + panel | `cd frontend && npm ci && npm run build` → `systemctl restart operations-hub-frontend` (`npm run start`, :3000) → `nginx -t && reload` | `DEPLOY.md`, `docs/FRONTEND-DEPLOY.md`, `deploy/systemd/operations-hub-frontend.service`, `deploy/nginx/operations-hub.conf` (un `server` para ambos hosts; `/api`, `/health`, `/ready`, `/docs` → API; `/` → Next) |
| Alternativas presentes | `docker-compose.yml` + `deploy/nginx.conf`; `frontend/Dockerfile` (standalone, Node 20); `frontend/vercel.json` | — |
| App | EAS Build en la nube: `preview` → APK; `production` → AAB (`autoIncrement`); `eas submit` → pista interna de Play, borrador | `mobile/eas.json`, `mobile/README.md` |
| CI | `.github/workflows/ci.yml`: backend (ruff + pytest), frontend (`npm test` + build), smoke E2E login → bandeja. **No hay job de mobile** | — |

### Variables de entorno (solo nombres)

| Superficie | Variables |
|---|---|
| App | `EXPO_PUBLIC_API_URL`, `EXPO_PUBLIC_ORG_SLUG` (en `eas.json`, `.env.example`; fallback `app.json › extra.apiUrl/orgSlug/privacyUrl`) |
| Frontend | `NEXT_PUBLIC_API_URL` (vacío en prod), `NEXT_PUBLIC_CONSOLE_HOST`, `NEXT_PUBLIC_PORTAL_HOST`, `NEXT_PUBLIC_APP_ENV`, `NEXT_PUBLIC_BOT_DISPLAY_NAME`, `NEXT_PUBLIC_BOT_DISPLAY_NAME_SHORT`, `NEXT_PUBLIC_PRODUCT_DISPLAY_NAME`, `NEXT_PUBLIC_ASSISTANT_TAGLINE`, `API_PROXY_TARGET` (dev), `PORT`, `NODE_ENV`, `HOSTNAME` |
| Backend, lo que afecta a las superficies | `CORS_ORIGINS`, `PUBLIC_URL`, `DOMAIN`, `PORTAL_DOMAIN`, `APP_ENV`, `AUTH_SECRET`, `PORTAL_AUTH_SECRET`, `AUTH_TOKEN_HOURS`, `PORTAL_TOKEN_HOURS`, `CONSOLE_JWT_AUD`, `PORTAL_JWT_AUD`, `PORTAL_AUTH_MODE`, `PORTAL_ALLOW_GUEST`, `OTP_LENGTH`, `OTP_TTL_MINUTES`, `OTP_MAX_ATTEMPTS`, `DNI_PEPPER`, `PORTAL_CONNECTIVITY_TTL_SEC`, `OV_BATAN_*`, `OV_HANDOFF_V2`, `BOT_DISPLAY_NAME`, `BOT_DISPLAY_NAME_SHORT`, `PRODUCT_DISPLAY_NAME`, `ASSISTANT_TAGLINE`, `TICKET_ID_PREFIX`, `ENABLE_LEGACY_API`, `ENABLE_API_DOCS`, `SMTP_*`, `SENTRY_DSN`, `WHISPER_*`, `TTS_*` |

Archivos de entorno presentes (no leídos): `.env`, `frontend/.env.local`, `mobile/.env`.

---

## 8. Accesibilidad y calidad

### 8.1 Contraste (WCAG, calculado con los tokens)

| Par | Ratio | AA texto normal (4.5) |
|---|---|---|
| App `text` / `bg` | 17.89 | Cumple |
| App `muted` / `bg` · `muted` / `card` | 7.30 · 6.92 | Cumple |
| App `brand` (texto) / `bg` | 5.45 | Cumple |
| **Blanco sobre `brand #2298A6`** (botones primarios en app y web; burbuja del usuario en la app) | **3.44** | **No cumple** (solo alcanza AA para texto grande) |
| Web oscuro `slate-500` / fondo | 4.24 | No cumple |
| Web claro `--text-muted` / fondo | 4.41 | No cumple |
| Web claro `brand` (texto) / blanco | 3.44 | No cumple |

### 8.2 Tamaños de fuente

- App: escala de 11 a 28 px; los textos más chicos usan 11–12 px. No se usa `allowFontScaling` ni `maxFontSizeMultiplier` (se respeta el tamaño del sistema por defecto, sin probar ni limitar).
- Web: **255 usos** de `text-[9px]`, `text-[10px]` o `text-[11px]` en `.tsx` (por ejemplo, la leyenda de invitado en `portal/page.tsx:457` y los badges del menú).

### 8.3 Lectores de pantalla

- App: 82 props `accessibility*` en 18 archivos (pestañas con `accessibilityRole="tab"` y `accessibilityState`; `accessibilityHint` en las acciones).
- Web: 62 atributos `aria-*` / `role=` en 17 de 53 archivos `.tsx`; `AuthGuard` usa `role="status"` + `aria-live`; foco visible global (`globals.css`, `:focus-visible`). Portal: labels con `htmlFor` en los campos y `aria-selected` en el selector de modo, pero los botones de modo no declaran `role="tab"`.

### 8.4 Estados vacíos y de error

- App: `EmptyState`, `Banner` (tonos warning/ok con Reintentar), pantalla “Sin conexión” en el arranque, mensajes de `formatUserError`. Cada dominio de `customer-summary` trae `status` (`ok/empty/stale/unavailable/not_available/omitted/partial`), y Inicio no inventa `$0` si falla la facturación (`HomeScreen.tsx`).
- Web: textos “Cargando…”, `EmptyState` local en Estadísticas, `Toast`, errores de la API con mensajes en español (timeout 45 s con mensaje de “cold start”, `api-client.ts:96`).

### 8.5 Pruebas existentes

| Superficie | Pruebas | Cómo corren |
|---|---|---|
| App | `scripts/verify-{push-incidente,create-claim,services,customer-summary,invoices}.mjs` (transpilan TS y validan view-models; **no hay Jest ni renderizado RN**); `npm run lint` = `tsc --noEmit` | Manual (no están en CI) |
| Portal / panel | `src/lib/api-client.contract.test.ts`, `src/lib/public-hosts.test.ts` (`tsx --test`); `npm run lint` (eslint); smoke E2E login → bandeja en CI | CI |
| Endpoints del abonado (backend) | `tests/test_portal_{abonado,connectivity,customer_summary,invoices_2_8,ov_links,relogin_ticket,services,tickets}.py`, `test_ov_{batan_links,handoff,intencion}.py` (191 archivos en `tests/` en total) | CI (pytest) |

No hay pruebas de UI del portal (`portal/page.tsx`) ni pruebas visuales o de accesibilidad automatizadas en ninguna superficie.

---

## 9. Riesgos y deuda técnica que condicionan un rediseño

1. **Portal web y app no están a la par**: el portal es solo chat (`portal/page.tsx`); Inicio, Actividad, facturas, OV, conectividad y push existen solo en la app. Rediseñar ambos exige construir esas vistas en el web sobre los mismos endpoints `/portal/*`.
2. **Sin código compartido** entre `mobile/` y `frontend/`: dos clientes API, dos sets de tipos y componentes de chat/CSAT/avatar/botón duplicados (§4.3). Cualquier cambio de contrato se hace dos veces.
3. **Tokens divergentes**: fondos distintos (`#0B1220` en la app y `#020617` en el web), `brand-dark` distinto (`#1b7a86` y `#1A7985`), 40 hex sueltos en `.tsx`, tema claro solo en web y basado en invertir la escala slate (cualquier `slate-*` nuevo se invierte sin aviso).
4. **Contraste del color de marca**: blanco sobre `#2298A6` = 3.44:1 en todos los CTA principales.
5. **Archivos grandes en una sola pieza**: `portal/page.tsx` (653), `AppContext.tsx` (908), `InboxPanel.tsx` (949), `SupportSidebar.tsx` (967), `PlatformSettingsPanel.tsx` (1340), `api-client.ts` (1589).
6. **App sin navegación ni manejo de estado estándar**: pestañas propias con vistas superpuestas, estado elevado y props en cadena (`App.tsx` → `AppShell` → pantallas); el `scheme` está declarado pero no hay deep links.
7. **Mobile fuera de CI** y sin tests de renderizado.
8. **Documentación desactualizada**: `mobile/CURRENT_STATE.md` y la tabla de endpoints de `mobile/README.md` no reflejan el código actual. `mobile/README.md` dice que el APK de preview no tiene push ni micrófono; hoy el código registra push y graba voz (falta verificar en el build real).
9. **Código muerto**: hooks `useOvLinks` y `useServices` en la app; 12 métodos sin uso en `api-client.ts` (§5.3); endpoints `/demo/*` consumidos solo por métodos sin uso.
10. **La app apunta al host de la consola** (`ibot.ecolan.com`) y `PRIVACY_URL` cae por defecto en `ibot.ecolan.com/privacidad`, que el middleware redirige al portal. Mover el API del abonado de host afecta a builds ya publicados.
11. **`org_slug` fijo** (`"coop-batan"`) en `portal/page.tsx` (invitado) y por defecto en la app: el multi-tenant del lado del abonado depende de esto.
12. **Polling**: el chat en la app y en el portal (4 s), la bandeja, la campana, el supervisor y las métricas LLM usan `setInterval`; no hay WebSocket ni SSE.
13. **El panel puede cambiar el color de marca en tiempo de ejecución** (`BrandSync` → `tenantContext.brand_color`); el portal y la app no lo usan.
14. **Límites de contrato que el rediseño no puede cruzar sin backend**: facturas sin vencimiento ni PDF, pago solo por OV externa, sin Wi‑Fi, sin preferencias de avisos, sin respuesta del abonado en un ticket. `ticket_customer_note` existe en el código y en el default (`app/config.py:199`), pero según `CLAUDE.md` puede estar apagada en producción.
15. **Eko congelado**: el chat, los textos de Eko y los journeys salen del backend (`/portal/messages`); el rediseño solo puede cambiar cómo se muestran, no el contenido.

---

## Preguntas abiertas

1. **¿El portal web debe igualar a la app** (Inicio, Actividad, facturas, conectividad) o sigue siendo solo chat? El código no lo indica.
2. **¿`PORTAL_ALLOW_GUEST` está activo en producción?** El código lo apaga por defecto en `production`, pero el botón de invitado del portal se muestra siempre; no se puede saber leyendo el repo (el valor está en `.env`, que no se leyó).
3. **¿Qué devuelve hoy `ov-links` en producción**: `authenticated` o `public`? Define si “Pagar” abre una sesión ya iniciada o pide identificarse de nuevo. Depende de `OV_HANDOFF_V2` / `OV_BATAN_*` en el servidor.
4. **¿El build publicado (`versionCode` 15) incluye push y voz?** `mobile/README.md` dice que el APK de preview no los tiene; el código sí los implementa. Falta la evidencia del build real y de Firebase.
5. **¿`ticket_customer_note` está encendida en producción?** Cambia si en Actividad aparecen notas del agente para el abonado.
6. ¿Hay manual de marca de la cooperativa (tipografía, paleta, logos)? En el repo solo están `#2298A6`, `#0D1B2A`, `#F4F7F6` y los PNG de `frontend/public/` y `mobile/assets/`.
7. ¿Qué cooperativas usan el panel y con qué `brand_color`? Define si el rediseño debe aceptar colores por tenant.
8. ¿La app necesita tema claro? Hoy está fijada en oscuro.
9. ¿“Estadísticas → Avanzado (ilustrativo)” con horas ahorradas “estimadas” debe seguir visible? La fórmula está en `app/estate/executive_analytics.py`; no está claro si negocio la valida.
10. ¿Se mantienen `frontend/vercel.json` y `docker-compose.yml` como formas de deploy, o solo la de systemd + nginx de `DEPLOY.md`?
