# App abonado — Soporte Batán (Eko)

Cliente nativo (Android / iOS) del **mismo motor N1** que el portal web. No hay bot aparte: auth DNI+OTP/PIN y chat contra `https://ibot.ecolan.com`.

> **APK preview:** sin push FCM ni micrófono nativo (crasheaban en Samsung sin `google-services.json`). Chat, links OV y safe area sí. Push/voz vuelven con Firebase configurado.

## Qué usa

| Pieza | Endpoint |
|---|---|
| Branding | `GET /api/v1/public/branding` |
| Login | `/api/v1/portal/auth/start\|verify\|login-pin\|set-pin` |
| Chat | `POST /api/v1/portal/messages` (`X-Canal: app`) |
| Voz (deshabilitado en APK) | `POST /api/v1/portal/audio` |
| Push (deshabilitado en APK) | `POST /api/v1/portal/devices` |

La bandeja de agentes muestra el hilo como **App**. Un corte NAS dispara push a los dispositivos registrados.

## Desarrollo

```bash
cd mobile
cp .env.example .env
# EXPO_PUBLIC_API_URL=https://ibot.ecolan.com
# o tu API local, p.ej. http://192.168.0.10:8000
npm install
npx expo start
```

Escaneá el QR con Expo Go. En un emulador Android: `a`. El JWT se guarda en SecureStore.

## APK (sin Play Store, sin dejar la PC encendida)

Hace falta una cuenta gratis en [expo.dev](https://expo.dev/signup). El build corre en la nube de Expo (~10–20 min) y te deja un `.apk` para instalar a mano.

```bash
cd /home/gabriel/Documentos/Vertia/Copilot-Tickets/mobile

# 1) Entrar a Expo (abre el navegador o pide usuario)
npx eas-cli login

# 2) Vincular el proyecto (solo la primera vez: Create a new project)
npx eas-cli init --non-interactive || npx eas-cli init

# 3) Generar APK de preview, apuntado a ibot.ecolan.com
npx eas-cli build -p android --profile preview
```

Cuando termine, Expo muestra un link. Descargá el `.apk` al celular y abrilo (puede pedir “instalar apps desconocidas”).

La primera vez EAS genera un keystore de Android; dejalo que lo guarde él (no lo pierdas: sirve para actualizar la app después).

Play Store / App Store es el paso siguiente, no hace falta para usarla en la cooperativa.

### Build nativa del tema claro/oscuro (H-APP-1, 1.0.7 / versionCode 16)

Expo Go no alcanza para probar esto: `userInterfaceStyle: "automatic"`, el splash claro/oscuro, las fuentes Manrope embebidas (plugin `expo-font`) y `expo-system-ui` solo entran en una build nativa. Mismos pasos de arriba (`npx eas-cli build -p android --profile preview`). Antes de lanzarla:

```bash
node ../scripts/design-tokens.mjs --check     # splash de app.json = bg de design/tokens.json
node --test ../design/contrast.test.mjs
npm run lint
```

Después de instalar: cambiar el modo del teléfono con la app abierta (Cuenta → Apariencia → Sistema), probar Claro y Oscuro fijos, cerrar y reabrir (la elección persiste) y mirar el splash en ambos modos.

## Play Store (Android)

Play Store **no acepta APK**: hay que subir un **AAB** de producción. El primer envío va a **prueba interna**; la ficha pública se completa después.

### 1. Cuenta de desarrollador

1. Entrá a [Google Play Console](https://play.google.com/console/signup) con la cuenta de Google de la cooperativa (no una personal si se puede evitar).
2. Pagá la inscripción única (USD 25) y verificá identidad / organización.
3. **Crear app**:
   - Nombre: `EKO-Asistente`
   - Idioma: español (Argentina)
   - Tipo: aplicación
   - Gratis
   - Declaraciones de políticas: aceptá las que apliquen (no es app para niños; no es tienda).
4. El **nombre de paquete** tiene que ser exactamente `coop.batan.soporte`.

### 2. Construir el AAB

```bash
cd /home/gabriel/Documentos/Vertia/Copilot-Tickets/mobile
npx eas-cli login
npx eas-cli build -p android --profile production
```

Cuando termine, descargá el `.aab` desde [expo.dev](https://expo.dev).

### 3. Subir el bundle (primera vez, a mano)

En Play Console → la app → **Prueba** → **Prueba interna** → **Crear versión nueva** → subí el AAB.

Completá lo mínimo para que deje de estar en borrador:

| Campo | Texto sugerido |
|---|---|
| Título (máx. 30) | `EKO-Asistente` |
| Descripción breve (máx. 80) | `Soporte de Cooperativa Batán: consultá a Eko desde el celular.` |
| Descripción completa | Ver más abajo |
| Categoría | Herramientas / Comunicación |
| Correo de contacto | `admin@ecolan.com` |
| Política de privacidad | `https://soporte.ecolan.com/privacidad` |
| Eliminación de cuenta | En la app: **Eliminar datos**. Web: la misma URL, sección «Cómo borrar tus datos». |

Descripción completa (podés pegarla):

```
EKO-Asistente es el canal de soporte de Cooperativa Batán.

Iniciá sesión con tu DNI y un código al email o con tu PIN. Escribile a Eko (o mandá un audio) sobre internet, móvil o tu factura. Si hace falta, un agente de la cooperativa toma el chat.

No reemplaza WhatsApp de un día para el otro: es el canal propio, sin costo por mensaje de Meta.

Desarrollado para socios de Cooperativa Batán / Ecolan.
```

Recursos gráficos que pide Play:

- Ícono: ya está en `mobile/assets/icon.png` (1024×1024).
- Feature graphic 1024×500 (obligatorio).
- Al menos 2 capturas del teléfono (login + chat). Sacalas del emulador o del celular.

### 4. Formulario de seguridad de datos

- Recopila DNI, identificadores de cuenta (PIN hash), mensajes de soporte, audio si el socio graba, token de dispositivo si hay push.
- Finalidad: funcionalidad de la app (soporte).
- Cifrado en tránsito: sí (HTTPS).
- ¿Se venden? No.
- ¿Obligatorios para usar la app? DNI sí; micrófono no.
- ID de publicidad: no (está bloqueado en el AAB).

Clasificación de contenido: utilidad / comunicación, sin contenido para menores como público objetivo.

### 5. Envíos siguientes (EAS Submit)

Cuando la app ya exista en Play Console y tengas una [cuenta de servicio](https://expo.fyi/creating-google-service-account) invitadas con permiso de releases:

```bash
cd /home/gabriel/Documentos/Vertia/Copilot-Tickets/mobile
npx eas-cli submit -p android --profile production --latest
```

Eso deja un **borrador** en pista interna. En Play Console lo revisás y lo pasás a producción cuando la ficha esté completa.

### 6. Deploy de la política

`/privacidad` vive en el portal público (`https://soporte.ecolan.com/privacidad`). Tiene que responder **antes** de mandar a revisión, si no Google marca el link como inválido.

## Variables

| Variable | Default |
|---|---|
| `EXPO_PUBLIC_API_URL` | `https://ibot.ecolan.com` |
| `EXPO_PUBLIC_ORG_SLUG` | `coop-batan` |
