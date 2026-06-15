# Frontend Next.js — despliegue productivo

El frontend **Next.js** es la consola principal. La UI estática (`index.html` + Netlify) queda como legacy.

## Arquitectura

```
Vercel / Netlify          Render                 Supabase
(Next.js)        ──►      (FastAPI /api/v1)  ──►  (Postgres)
NEXT_PUBLIC_API_URL       DATABASE_URL
```

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

## Vercel (recomendado)

1. Importar repo → **Root Directory:** `frontend`
2. Framework: Next.js (auto-detectado)
3. Variables de entorno:

| Variable | Valor |
|----------|-------|
| `NEXT_PUBLIC_API_URL` | `https://tu-api.onrender.com` |

4. Deploy
5. En Render, agregar URL de Vercel a `CORS_ORIGINS`:

```env
CORS_ORIGINS=https://tu-app.vercel.app
```

`vercel.json` en `frontend/` ya define build estándar.

---

## Netlify (alternativa)

1. **Base directory:** `frontend`
2. **Build command:** `npm run build`
3. **Publish directory:** `.next` no aplica — usar plugin Next.js de Netlify o:

```toml
# netlify.toml en frontend/ (opcional)
[build]
  base = "frontend"
  command = "npm run build"
  publish = ".next"
```

4. Variable: `NEXT_PUBLIC_API_URL=https://tu-api.onrender.com`

---

## Checklist post-deploy

- [ ] Login en `/login` con usuario cooperativa
- [ ] Chat en `/soporte` responde
- [ ] Tickets persisten tras F5
- [ ] Admin ve múltiples tenants
- [ ] Sin errores CORS en consola del browser

---

## Legacy (no usar para piloto)

| Componente | Variable | Rutas |
|------------|----------|-------|
| Netlify estático raíz | `IMOWI_API_URL` | `/api/chat` legacy |

Usar solo si necesitás la UI antigua en `index.html`.
