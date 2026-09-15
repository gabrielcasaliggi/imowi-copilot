# Eko App — estado actual (`mobile/`)

Informe de solo lectura (2026-09-15). Base para rediseño incremental **Eko App vNext**.  
No describe cambios de backend ni otra arquitectura frontend fuera de Expo.

**Alcance analizado:** árbol `mobile/` (~1.090 LOC TS/TSX de app) + contrato con `/api/v1/portal/*` y `GET /api/v1/public/branding`.

---

## 1. Estructura completa de `mobile/`

```
mobile/
├── App.tsx                 # Root: boot + Auth | Chat
├── index.ts                # registerRootComponent(App)
├── app.json                # Expo config (nombre EKO-Asistente, package coop.batan.soporte)
├── eas.json                # profiles development / preview (APK) / production (AAB)
├── package.json            # expo ~54, RN 0.81, scripts start|android|ios|lint
├── package-lock.json
├── babel.config.js
├── tsconfig.json           # strict, extends expo/tsconfig.base
├── .env.example            # EXPO_PUBLIC_API_URL, EXPO_PUBLIC_ORG_SLUG
├── .gitignore
├── README.md               # ops Play Store / EAS / endpoints
├── assets/
│   ├── icon.png
│   ├── adaptive-icon.png
│   └── splash.png
└── src/
    ├── api.ts              # cliente HTTP portal
    ├── config.ts           # API_BASE, ORG_SLUG, X-Canal, PRIVACY_URL
    ├── session.ts          # SecureStore token/conv/dni
    ├── theme.ts            # colors + Branding defaults
    ├── types.ts            # AuthPayload, Inbox*
    ├── push.ts             # stub vacío (sin FCM)
    ├── MessageText.tsx     # links clickeables en burbujas
    └── screens/
        ├── AuthScreen.tsx  # DNI+PIN | OTP primera vez
        └── ChatScreen.tsx  # chat + PIN setup + CSAT + salir/borrar
```

**No hay:** `expo-router`, carpetas `components/`, `hooks/`, `context/`, `navigation/`, `__tests__/`, ni assets de tipografía.

**Empaquetado:** `name` npm `soporte-batan`, display `EKO-Asistente`, `version` 1.0.3 / Android `versionCode` 5, scheme `soportebatan`, dark UI, `newArchEnabled: false`, sin plugins Expo.

---

## 2. Navegación actual

No hay librería de navegación.

Flujo en `App.tsx` (máquina de estados implícita):

```
booting (spinner)
  → sin sesión válida → AuthScreen
  → con token + conversacion → ChatScreen
       └─ sub-estado local showPin → pantalla “Creá un PIN” (mismo ChatScreen)
```

- Auth interna: tabs `pin` | `dni` + step `auth` | `otp` (estado local en `AuthScreen`).
- Salir / delete account → `clearSession()` + vuelve a Auth.
- Sin deep links, sin tabs, sin stack, sin historial de pantallas.

---

## 3. Pantallas existentes

| Pantalla | Archivo | Responsabilidad |
|----------|---------|-----------------|
| Boot | `App.tsx` | Carga branding + sesión SecureStore; valida con `GET conversations/{id}` |
| Auth | `AuthScreen.tsx` | DNI+PIN, primera vez (OTP email), link privacidad |
| Chat | `ChatScreen.tsx` | Header Eko, banners handoff, FlatList mensajes, composer, estrellas CSAT |
| Set PIN (overlay) | dentro de `ChatScreen` | Si `has_pin === false` post-OTP |
| (stub) Push | `push.ts` | No-op documentado |

---

## 4. Componentes reutilizables

| Pieza | Tipo | Uso |
|-------|------|-----|
| `MessageText` | único componente UI compartido | Parsea URLs en texto y abre con `Linking` |
| Estilos / botones / inputs | **no** extraídos | Duplicados StyleSheet en Auth y Chat |
| Avatar Eko | `require("../../assets/icon.png")` inline | Header + burbujas bot |

No hay design-system de componentes (Button, Input, Banner, Bubble, etc.).

---

## 5. Design system existente

Archivo: `src/theme.ts`.

**Tokens de color (hardcoded):**

| Token | Hex | Uso |
|-------|-----|-----|
| `brand` / `brandDark` | `#2298A6` / `#1b7a86` | CTA, burbuja usuario, acentos |
| `bg` / `card` / `border` | `#0B1220` / `#111827` / `#1f2937` | Fondo dark |
| `text` / `muted` | `#F8FAFC` / `#94A3B8` | Tipografía |
| `userBubble` / `botBubble` / `botText` | brand / `#F1F5F9` / `#1E293B` | Chat |
| `danger` / `amber` / `online` | rojo / ámbar / verde | Errores, banners, status |

**Branding remoto** (`GET /api/v1/public/branding`) mapeado a:

`botDisplayName`, `botDisplayNameShort`, `orgHint`, `productDisplayName`, `assistantTagline`, `assistantIntro`.

Fallback local `defaultBranding` (Eko / Cooperativa Batán / Soporte Batán).

**Ausente:** tipografías custom, spacing scale, radius tokens compartidos, light mode, theming dinámico por color remoto (solo copy).

UI fija dark (`userInterfaceStyle: "dark"`, splash `#0B1220`).

---

## 6. Estado global

No hay Context, Redux, Zustand ni React Query.

Estado en `App.tsx` (lifted):

- `branding`, `booting`, `token`, `needPin`, `conv`, `mensajes`

Estado local en pantallas:

- Auth: mode/step/dni/pin/otp/challenge/busy/error
- Chat: conv/mensajes/texto/busy/error/pin/showPin + polling

Props drilling: `token`, `branding`, `conv`, `mensajes`, callbacks `onAuthed` / `onExit` / `onNeedPin`.

---

## 7. API client utilizado

`src/api.ts` — `fetch` nativo + helper `postJson`.

- Base: `config.API_BASE`
- Header fijo: `X-Canal: app` (`CANAL_HEADER`)
- Auth: `Authorization: Bearer <portal_token>` cuando aplica
- Errores: clase `ApiError` (message + status); `parseError` lee `detail` FastAPI
- Branding: try/catch → defaults (nunca lanza)
- Audio: `FormData` multipart a `/portal/audio` (implementado, **sin UI**)

No usa el `api-client` del frontend Next.js (código paralelo, tipos similares).

---

## 8. Endpoints consumidos

### Usados en runtime UI

| Método | Path | Dónde |
|--------|------|-------|
| GET | `/api/v1/public/branding` | boot App |
| POST | `/api/v1/portal/auth/start` | Auth primera vez |
| POST | `/api/v1/portal/auth/verify` | Auth OTP |
| POST | `/api/v1/portal/auth/login-pin` | Auth PIN |
| POST | `/api/v1/portal/auth/set-pin` | Chat post-OTP |
| POST | `/api/v1/portal/messages` | enviar texto |
| GET | `/api/v1/portal/conversations/{id}` | boot + poll handoff |
| POST | `/api/v1/portal/account/delete` | Eliminar datos |

Todos los POST/GET autenticados llevan `X-Canal: app`. En auth, el backend mete `canal=app` en el JWT; en `messages`/`audio` usa canal del JWT (`_canal_desde_request(None, payload)`).

### Implementados en client pero no cableados a UI

| Método | Path | Notas |
|--------|------|-------|
| POST | `/api/v1/portal/devices` | `api.registerDevice` + stub `registerPush` |
| POST | `/api/v1/portal/audio` | `api.sendAudio` sin micrófono / deps |

### Disponibles en backend portal y no usados por la app

| Path | Uso típico web |
|------|----------------|
| POST `/portal/session` | guest / cookie web |
| POST `/portal/logout` | cookie HttpOnly |
| DELETE `/portal/devices` | unregister push |

---

## 9. Tipos / interfaces

`src/types.ts`:

```ts
InboxAbonado      // id, dni, telefono_e164, nombre, servicio, estado
InboxConversation // id, canal, canal_display?, estado, ticket_id, contexto?, abonado?
InboxMessage      // id, conversacion_id, direccion, autor, texto, created_at
AuthPayload       // portal_token, org_slug, abonado_identificado, has_pin?, conversacion, mensajes, contact_masked?
```

`theme.Branding` — copy de producto (no colores).

Respuestas parciales tipadas inline en `api.ts` (auth start, send, conversation, audio, devices).

**Huecos:** `contexto` es `Record<string, unknown>` (CSAT usa `encuesta_pendiente`); no hay tipos de error estructurado más allá de `ApiError`; sin shared package con FE.

---

## 10. Manejo de autenticación

1. **Primera vez:** DNI → `auth/start` (OTP email) → `auth/verify` → `AuthPayload` + `saveSession`.
2. **Recurrente:** DNI + PIN → `login-pin` → misma sesión.
3. **Persistencia:** SecureStore `portal_token`, `conv_id`, opcional `dni_hint`.
4. **Boot:** si hay sesión → `GET conversations/{id}`; fallo → `clearSession` → Auth.
5. **Canal:** header `X-Canal: app` en auth → JWT con `canal=app` → bandeja marca hilo **App**.
6. **PIN opcional:** tras OTP si `has_pin === false`, Chat fuerza UI de set-pin (omitible).
7. **Salir:** limpia token/conv (ver §12: DNI hint no se borra).
8. **Eliminar datos:** `account/delete` + exit (Play Store compliance).

No cookie; no refresh token; expiración JWT → fallo en boot o en send (send **no** fuerza logout automático ante 401).

---

## 11. Manejo de errores

| Capa | Comportamiento |
|------|----------------|
| `api.ts` | HTTP !ok → `ApiError`; branding falla soft |
| Auth / Chat | `err.message` en Text rojo; busy flag |
| Boot | catch → clearSession |
| Poll chat | catch vacío (silencioso) |
| Send | rollback mensaje optimista `local-*`, restaura texto |
| Links | `Linking.openURL(...).catch(() => {})` |
| Delete | Alert + error en pantalla |

No hay: cola offline, retry backoff, toast global, distinción UX 401 vs 503 vs 422, telemetría client-side.

---

## 12. Persistencia / caché

| Dato | Dónde | Notas |
|------|-------|-------|
| JWT portal | SecureStore | clave `portal_token` |
| ID conversación | SecureStore | `conv_id` |
| DNI hint | SecureStore | se guarda; **no se usa** para prefill Auth; **no se borra** en `clearSession` |
| Mensajes | solo memoria | cada send/poll reemplaza lista desde API |
| Branding | memoria | se pide en cada cold start |

Sin AsyncStorage de historial, sin cache de imágenes HTTP, sin SQLite.

---

## 13. Push notifications

- Backend listo: `POST/DELETE /portal/devices` + `PortalDevice` + `app_push`.
- App: `push.ts` es stub (comentario: crasheaba Samsung sin `google-services.json`).
- `api.registerDevice` existe; **nadie llama** `registerPush` ni `registerDevice`.
- README: push vuelve con Firebase + `expo-notifications`.
- Dependencias: **sin** `expo-notifications` / FCM en `package.json`.

---

## 14. Voice / Whisper / TTS

| Pieza | Estado en app |
|-------|----------------|
| Grabación mic | No hay UI ni deps (`expo-av` / etc.) |
| `POST /portal/audio` | Client `sendAudio` listo (m4a FormData) |
| Whisper (backend) | Transcribe si disponible; fallback mensaje |
| TTS respuesta | Backend WA/voz; app **solo texto** |

README: voz deshabilitada en APK preview a propósito.

---

## 15. Dependencias principales

**Runtime (`package.json`):**

- `expo` ~54.0.0
- `react` 19.1.0 / `react-native` 0.81.5
- `expo-secure-store`, `expo-constants`, `expo-status-bar`
- `react-native-safe-area-context`

**Dev:** TypeScript ~5.9, `@types/react`, `babel-preset-expo`.

**No instaladas (relevantes para vNext):** navegación, notificaciones, audio, image picker, testing library, eslint RN, reanimated, fonts.

CI: job `mobile` → `npm ci` + `npm run lint` (`tsc --noEmit`).

---

## 16. Tests existentes

- **0** tests unitarios/e2e en `mobile/`.
- Sensor único: typecheck CI.
- Contrato portal tipado/testeado en **frontend** (`api-client.contract.test.ts`), no compartido con mobile.

---

## 17. Deuda técnica evidente

1. Push y voz documentados como producto pero stub/muertos en código.
2. `registerPush` / `sendAudio` / `registerDevice` dead code o semi-muerto.
3. `dni_hint` incompleto (no prefill, no clear al salir).
4. Sin logout forzado en 401 durante chat.
5. Polling 4s solo en handoff; en estado `bot` no hay sync si el agente actúa por otro canal (aceptable hoy).
6. Estilos y patterns Auth/Chat duplicados (~botón, input, error).
7. ChatScreen monolítico (~390 LOC) mezcla PIN, CSAT, header, composer, poll.
8. Tipos `Inbox*` duplicados conceptualmente vs `frontend/src/lib/types`.
9. Sin tests; refactor riesgoso.
10. `newArchEnabled: false`; plugins vacíos.
11. Header chat denso (Salir / Privacidad / Eliminar) poco escalable para UX.
12. Optimistic IDs `local-*` string; dependencia de replace total de lista.
13. `debug_otp` de auth start se auto-rellena en UI (útil en dev; riesgo si llega a prod mal configurado).

---

## 18. Código duplicado

| Qué | Dónde |
|-----|-------|
| Paleta + StyleSheet botón/input/error/link | `AuthScreen` ↔ `ChatScreen` |
| Safe area padding formula | ambas pantallas |
| Mapeo branding API → Branding | `api.branding` (parecido a `frontend/src/lib/brand.ts`) |
| Tipos Inbox / AuthPayload | `mobile/src/types` ↔ FE portal types |
| Flujo auth DNI/OTP/PIN + chat poll + CSAT | espejo funcional de `frontend/src/app/portal/page.tsx` (implementaciones separadas) |
| `estadoLabel` / banners handoff | lógica paralela portal web |

---

## 19. Qué debería conservarse

- Contrato **mismo motor N1** vía `/api/v1/portal/*` + `X-Canal: app` (no inventar bot paralelo).
- Flujo auth DNI+OTP / DNI+PIN + set-pin + account delete (compliance Play).
- SecureStore para JWT (no AsyncStorage en claro).
- Cliente `api.ts` delgado sobre `fetch` (adecuado al tamaño; evolucionar, no reemplazar stack).
- `MessageText` (links OV / deep-links en burbujas).
- Branding remoto con defaults locales.
- Optimistic send + refresh lista servidor.
- Polling en `espera_agente` / `con_agente`.
- CSAT por `contexto.encuesta_pendiente` enviando `"1"…"5"`.
- Identidad de producto: package `coop.batan.soporte`, EAS profiles, dark brand teal Batán.
- Superficie mínima: auth → chat (vNext puede **enriquecer**, no abandonar este eje).
- `tsc --noEmit` como sensor CI.

---

## 20. Qué debería refactorizarse (sin cambiar arquitectura FE)

Orden sugerido **dentro de Expo actual** (sin Next, sin nuevo framework):

1. Extraer UI kit mínimo (`Button`, `TextField`, `Banner`, `Bubble`) sobre `theme.ts`.
2. Partir `ChatScreen` (Header / MessageList / Composer / PinGate / CsatBar).
3. Capa sesión: clear completo de keys; prefill DNI; handler 401 → exit.
4. Activar push detrás de flag + Firebase cuando haya `google-services.json` (reusar `registerDevice`).
5. Voz detrás de flag + `expo-av` cableando `sendAudio` existente.
6. Tests smoke: `api` parseError / MessageText URLs / session roundtrip (mock SecureStore).
7. Alinear tipos con contrato FE (copiar contrato o generar desde OpenAPI futuro; sin monorepo obligatorio).
8. Navegación ligera solo si vNext suma pantallas reales (perfil, historial); hoy conditional render alcanza.

---

# A) Entregable

Este archivo es **`mobile/CURRENT_STATE.md`**.

---

# B) Lista priorizada de problemas

| Prio | Problema | Impacto | Esfuerzo relativo |
|:----:|----------|---------|-------------------|
| P0 | Push documentado / backend listo pero stub; sin registro de device | Cortes NAS / handoff no llegan al móvil | Medio (FCM + cablear) |
| P0 | Sin tests; ChatScreen monolítico | Rediseño UI frágil | Bajo–medio |
| P1 | Voz en README/API client sin UI ni deps | Paridad portal incompleta | Medio |
| P1 | Sesión: DNI hint huérfano; 401 en send no cierra sesión | UX/seguridad menor | Bajo |
| P1 | Header acciones (Salir/Privacidad/Eliminar) poco usable | Fricción abonado | Bajo (UI) |
| P2 | Design system = solo colors; estilos duplicados | Inconsistencia en rediseño incremental | Bajo |
| P2 | Tipos/contrato no compartidos con FE | Drift portal web vs app | Bajo |
| P2 | Dead code `sendAudio`/`registerDevice`/`push` stub | Confusión para agentes | Bajo |
| P3 | Sin offline / retry | Fallas red rurales | Medio |
| P3 | `debug_otp` auto-fill | Riesgo config | Bajo |
| P3 | New Architecture off / sin plugins | Deuda Expo a medio plazo | Bajo |

---

# C) Propuesta de migración incremental — Eko App vNext

Principio: **mismo backend portal**, mismo canal `app`, misma identidad de paquete. Rediseño visual y de módulos **por capas**, sin big-bang.

### Fase 0 — Baseline (sin UX nueva)

- Congelar este `CURRENT_STATE.md` como contrato de conservación.
- Añadir 2–3 tests smoke (MessageText, session clear keys, api error parse) + mantener `tsc`.
- Checklist manual: login PIN, OTP, send, handoff poll, CSAT, delete account, deep-link OV en burbuja.

### Fase 1 — Fundaciones UI (conservar pantallas)

- Extraer tokens (spacing/radius) + componentes presentacionales reutilizando colores actuales.
- Split ChatScreen / AuthScreen sin cambiar flujos ni API.
- Arreglar sesión (clear DNI, 401 → logout, prefill DNI opcional).
- Criterio done: typecheck + smoke auth/chat iguales funcionalmente.

### Fase 2 — Rediseño visual Auth + Chat (vNext look)

- Nueva composición visual (marca Eko, tipografía, atmósfera) **sobre** los mismos estados.
- Reordenar acciones de cuenta (menú “⋯” / pantalla Ajustes mínima) sin nuevas rutas de negocio.
- Criterio done: captura flujo real + mismos endpoints.

### Fase 3 — Capacidades ya contratadas

- **Push:** Firebase + `expo-notifications` → `registerPush` real → `api.registerDevice`; unregister en salir/delete.
- **Voz:** mic → `sendAudio`; feature flag si Whisper caído.
- Criterio done: device aparece en estate; audio crea turno N1; bandeja sigue `canal=app`.

### Fase 4 — Extensiones de producto (solo si el brief lo pide)

- Pantalla Ajustes / Privacidad in-app (hoy Linking externo).
- Indicador “Eko escribiendo” si el API expone señal (hoy busy local post-send).
- Historial / reabrir conversación: **requiere** contrato backend nuevo → fuera de este informe hasta brief.

### Fuera de alcance explícito de esta migración

- Cambiar a otro framework o a WebView del portal.
- Duplicar lógica N1 en el cliente.
- Modificar FastAPI salvo bugs de contrato descubiertos en Fase 3.
- Multi-tenant white-label en la app (ORG_SLUG sigue build-time).

### Criterios de aceptación globales vNext

1. Auth y chat siguen en `/api/v1/portal/*` con `X-Canal: app`.
2. Package `coop.batan.soporte` y EAS profiles intactos.
3. `npm run lint` (tsc) verde en CI.
4. Paridad mínima con portal web: PIN/OTP, mensajes, handoff visible, CSAT, delete account, links OV.
5. Push/voz: o bien funcionan E2E, o el README deja de anunciarlos como activos.

---

## Mapa rápido app ↔ backend

```
[AuthScreen] --X-Canal:app--> auth/start|verify|login-pin
       |                              |
       v                              v
  SecureStore <----- portal_token + conversacion (JWT canal=app)
       |
[ChatScreen] --Bearer--> messages | conversations | set-pin | account/delete
       |                 (devices/audio: client listo, UI no)
       v
  procesar_mensaje_entrante(..., canal=app)  →  bandeja "App"
```
