# App abonado — Soporte Batán (Eko)

Cliente nativo (Android / iOS) del **mismo motor N1** que el portal web. No hay bot aparte: auth DNI+OTP/PIN, chat, voz y push contra `https://ibot.ecolan.com`.

## Qué usa

| Pieza | Endpoint |
|---|---|
| Branding | `GET /api/v1/public/branding` |
| Login | `/api/v1/portal/auth/start\|verify\|login-pin\|set-pin` |
| Chat | `POST /api/v1/portal/messages` (`X-Canal: app`) |
| Voz | `POST /api/v1/portal/audio` |
| Push | `POST /api/v1/portal/devices` |

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

## Variables

| Variable | Default |
|---|---|
| `EXPO_PUBLIC_API_URL` | `https://ibot.ecolan.com` |
| `EXPO_PUBLIC_ORG_SLUG` | `coop-batan` |
