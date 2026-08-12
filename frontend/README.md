# Operations Hub — Frontend Next.js

Consola operativa principal (canónica). Ver [docs/FRONTEND-DEPLOY.md](../docs/FRONTEND-DEPLOY.md) y [DEPLOY.md](../DEPLOY.md) para producción en servidor propio (`ibot.ecolan.com`).

## Requisitos

- Node.js 20+
- Backend FastAPI en `http://localhost:8000`

## Desarrollo

```bash
cp .env.local.example .env.local
npm install
npm run dev
```

Abrir [http://localhost:3000](http://localhost:3000).

## Variables

| Variable | Descripción |
|----------|-------------|
| `NEXT_PUBLIC_API_URL` | URL pública del API FastAPI (sin barra final) |

## CORS (backend)

En `.env` del backend:

```env
CORS_ORIGINS=http://localhost:3000
```

## Credenciales demo

| Usuario | Contraseña | Rol |
|---------|------------|-----|
| `admin` | `admin` | NOC |
| `batan` | `batan` | Cooperativa Batán |
| `viamonte` | `viamonte` | Cooperativa Viamonte |

En producción las contraseñas vienen del seed (`ADMIN_PASSWORD`, etc.).
