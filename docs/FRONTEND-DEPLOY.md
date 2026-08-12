# Frontend Next.js — despliegue productivo

El frontend **Next.js** es la consola principal. Producción canónica: **servidor propio** (`ibot.ecolan.com`) con nginx + systemd.

> **UX Batán:** la operación de red/NAS es [`/incidentes`](../frontend/src/app/(dashboard)/incidentes). La ruta `/red` (telemetría demo JSC) fue retirada; no forma parte de la UI operativa.

## Arquitectura (producción nativa)

```
Nginx (HTTPS)
  /        → Next.js :3000
  /api     → FastAPI :8000  →  PostgreSQL (Supabase / local)
                              →  Groq / LLM
```

Ver [DEPLOY.md](../DEPLOY.md) y `deploy/nginx/operations-hub.conf`.

---

## Desarrollo local

```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```

Backend en `http://localhost:8000` con `CORS_ORIGINS=http://localhost:3000`.

---

## Servidor propio (canónico)

```bash
cd frontend && npm ci && npm run build
sudo systemctl restart operations-hub-frontend
sudo nginx -t && sudo systemctl reload nginx
```

Variables en el unit / `.env` del host:

| Variable | Valor |
|----------|-------|
| `NEXT_PUBLIC_API_URL` | `https://ibot.ecolan.com` (o URL pública de la API) |

En la API: `CORS_ORIGINS` debe incluir el origen del frontend.

---

## Checklist post-deploy

- [ ] Login en `/login` con usuario cooperativa
- [ ] Chat en `/soporte` responde
- [ ] Inbox / tickets persisten tras F5
- [ ] Incidentes masivos (`/incidentes`) refleja NAS
- [ ] Admin ve múltiples tenants
- [ ] Sin errores CORS en consola del browser
