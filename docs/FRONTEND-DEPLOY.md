# Frontend Next.js — despliegue productivo

El frontend **Next.js** sirve consola y portal. Producción: **servidor propio** con nginx + systemd.

- Consola: `ibot.ecolan.com`
- Portal abonado: `soporte.ecolan.com`

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
| `NEXT_PUBLIC_API_URL` | vacío (nginx proxifica `/api` en cada host) |
| `NEXT_PUBLIC_CONSOLE_HOST` | `ibot.ecolan.com` |
| `NEXT_PUBLIC_PORTAL_HOST` | `soporte.ecolan.com` |

En la API: `CORS_ORIGINS=https://ibot.ecolan.com,https://soporte.ecolan.com`.

---

## Checklist post-deploy

- [ ] Login en `/login` con usuario cooperativa
- [ ] Chat en `/soporte` responde
- [ ] Inbox / tickets persisten tras F5
- [ ] Incidentes masivos (`/incidentes`) refleja NAS
- [ ] Admin ve múltiples tenants
- [ ] Sin errores CORS en consola del browser
