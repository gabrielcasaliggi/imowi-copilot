# imowi Operations Hub — Frontend Next.js

Consola operativa principal (canónica). Ver [docs/FRONTEND-DEPLOY.md](../docs/FRONTEND-DEPLOY.md) para producción.

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

## Producción (Vercel)

1. Root directory: `frontend`
2. `NEXT_PUBLIC_API_URL=https://tu-api.onrender.com`
3. En Render: `CORS_ORIGINS=https://tu-app.vercel.app`

## Credenciales demo

| Usuario | Contraseña | Rol |
|---------|------------|-----|
| `admin` | `admin` | NOC imowi |
| `batan` | `batan` | Cooperativa Batán |
| `viamonte` | `viamonte` | Cooperativa Viamonte |

En producción las contraseñas vienen del seed (`ADMIN_PASSWORD`, etc. en Render).

## Legacy

La UI en `index.html` (Netlify + `IMOWI_API_URL`) está deprecada. Usar este frontend para el piloto.
