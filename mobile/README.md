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

## APK de producción (sin tienda todavía)

```bash
cd mobile
npx expo install expo-dev-client
# Cuenta Expo + EAS:
npx eas-cli login
npx eas-cli build -p android --profile preview
```

El `.apk` se instala en los celulares de la cooperativa. Play Store / App Store es el paso siguiente (cuenta Google Play + Apple Developer).

## Variables

| Variable | Default |
|---|---|
| `EXPO_PUBLIC_API_URL` | `https://ibot.ecolan.com` |
| `EXPO_PUBLIC_ORG_SLUG` | `coop-batan` |
