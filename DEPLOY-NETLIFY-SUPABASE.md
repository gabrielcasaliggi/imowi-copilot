# Netlify + Supabase + Render (arquitectura recomendada)

## Por qué no solo Netlify

Netlify sirve **sitios estáticos**. Este Copilot necesita **FastAPI (Python)** en el servidor:

- LLM (Groq/Ollama)
- RAG sobre Markdown (~50k líneas)
- Auth JWT y lógica de tickets

```
┌─────────────┐     HTTPS      ┌──────────────────┐     ┌─────────────┐
│   Netlify   │ ─────────────► │  Render (API)    │ ──► │  Supabase   │
│ index.html  │  IMOWI_API_URL │  FastAPI         │     │ PostgreSQL  │
│  config.js  │                │                  │     │  tickets    │
└─────────────┘                └──────────────────┘     └─────────────┘
```

---

## 1. Supabase

1. Proyecto en [supabase.com](https://supabase.com)
2. SQL Editor → [supabase/schema.sql](./schema.sql) → Run
3. Settings → API:
   - **Project URL** → `SUPABASE_URL`
   - **service_role key** → `SUPABASE_SERVICE_KEY` (solo en Render, **nunca** en Netlify)

---

## 2. API en Render

1. Conectá el repo de GitHub
2. **Web Service** o Blueprint con [render.yaml](../render.yaml)
3. Variables de entorno:

```env
APP_ENV=production
AUTH_SECRET=<openssl rand -hex 32>
AI_BASE_URL=https://api.groq.com/openai/v1
AI_API_KEY=tu-clave-groq
AI_MODEL=llama-3.3-70b-versatile
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
CORS_ORIGINS=https://tu-app.netlify.app
ADMIN_PASSWORD=contraseña-segura
COOP_PASSWORD=contraseña-segura
```

4. Probá: `GET https://tu-api.onrender.com/health`

Debe responder `"supabase": true` y `"auth": "jwt"`.

---

## 3. Frontend en Netlify

1. Import from Git → mismo repositorio
2. `netlify.toml` ya define:
   - **Build:** `node scripts/generate-config.js`
   - **Publish:** `.`
3. Variable de entorno en Netlify:

```env
IMOWI_API_URL=https://tu-api.onrender.com
```

El build genera `config.js` con esa URL. **No** pongas claves de Groq ni Supabase en Netlify.

4. `.netlifyignore` excluye Python, KB y secrets del sitio estático.

---

## 4. Orden de puesta en marcha

1. Supabase + schema  
2. Push a GitHub  
3. Render con env (Supabase + Groq + AUTH_SECRET + CORS)  
4. Probar `/health` y login vía URL de la API  
5. Netlify con `IMOWI_API_URL`  
6. Probar flujo completo desde el dominio Netlify  

---

## 5. Auth

- **JWT stateless** — no depende de disco en Render (sin sesiones en JSON).
- Tokens válidos `AUTH_TOKEN_HOURS` (default 72 h).
- Usuarios configurables por `ADMIN_*`, `COOP_*` o `MOCK_USERS_JSON`.

---

## 6. Desarrollo local vs producción

| | Local | Producción |
|---|-------|------------|
| Frontend | `http://127.0.0.1:8000` (uvicorn sirve index.html) | Netlify |
| API | mismo puerto 8000 | Render |
| Tickets | JSON en `data/` o Supabase | Supabase |
| Auth | JWT con secret dev | `AUTH_SECRET` obligatorio |

---

## Migrar tickets JSON → Supabase

Insertá manualmente desde `data/tickets.json` en la tabla `tickets` (SQL Editor). Los IDs `JSC-xxxx` se respetan.
