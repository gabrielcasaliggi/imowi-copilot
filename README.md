# imowi NOC Copilot

Copilot de soporte para operadores de cooperativas: chat asistido por IA, RAG sobre base de conocimiento y gestión de tickets para el NOC.

## Arquitectura (producción)

```
Netlify (index.html)  ──HTTPS──►  Render (FastAPI)  ──►  Supabase (PostgreSQL)
                                         │
                                         └── Groq / LLM compatible OpenAI
```

| Componente | Dónde | Qué hace |
|------------|-------|----------|
| **Frontend** | Netlify | UI estática (`index.html`) |
| **API** | Render / Fly / Docker | Chat, RAG, tickets, auth JWT |
| **DB** | Supabase | Persistencia de tickets |
| **LLM** | Groq (u otro) | Respuestas del Copilot |

Guía paso a paso: [DEPLOY-NETLIFY-SUPABASE.md](./DEPLOY-NETLIFY-SUPABASE.md)

---

## Desarrollo local

### Requisitos

- Python 3.12+
- Ollama local **o** API key de Groq

### Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Editá .env con tu AI_API_KEY si usás Groq
```

### Ejecutar

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Abrí **http://127.0.0.1:8000** (no Live Server en otro puerto sin API).

### Login demo (local)

| Usuario | Contraseña | Rol |
|---------|------------|-----|
| `admin` | `admin` | Panel NOC |
| `coop_prueba` | `prueba` | Operador cooperativa |

En producción cambiá contraseñas vía variables `ADMIN_PASSWORD`, `COOP_PASSWORD`, etc.

---

## Variables de entorno (API)

| Variable | Obligatoria en prod | Descripción |
|----------|---------------------|-------------|
| `APP_ENV` | Sí → `production` | Activa validaciones de seguridad |
| `AUTH_SECRET` | Sí | Secreto JWT (`openssl rand -hex 32`) |
| `AI_BASE_URL` | Sí | URL del LLM |
| `AI_API_KEY` | Sí | Clave del proveedor |
| `AI_MODEL` | Sí | Modelo (ej. `llama-3.3-70b-versatile`) |
| `SUPABASE_URL` | Recomendado | Proyecto Supabase |
| `SUPABASE_SERVICE_KEY` | Recomendado | Service role (solo backend) |
| `CORS_ORIGINS` | Recomendado | URL Netlify, ej. `https://app.netlify.app` |

Frontend (Netlify build):

| Variable | Descripción |
|----------|-------------|
| `IMOWI_API_URL` | URL pública de la API, ej. `https://xxx.onrender.com` |

---

## Supabase

1. Creá proyecto en [supabase.com](https://supabase.com)
2. SQL Editor → ejecutá [supabase/schema.sql](./supabase/schema.sql)
3. Copiá **Project URL** y **service_role key** a las variables de Render

---

## Despliegue rápido

### 1. GitHub

```bash
git init
git add .
git commit -m "Initial commit — imowi NOC Copilot"
git remote add origin https://github.com/TU_ORG/Copilot-Tickets.git
git push -u origin main
```

### 2. API en Render

- New → **Web Service** → conectá el repo
- O importá [render.yaml](./render.yaml) (Blueprint)
- Variables: `AI_*`, `SUPABASE_*`, `AUTH_SECRET`, `CORS_ORIGINS`, contraseñas
- Probá: `https://tu-api.onrender.com/health`

### 3. Frontend en Netlify

- New site → Import from Git → mismo repo
- Build command: `node scripts/generate-config.js` (ya en `netlify.toml`)
- Publish directory: `.`
- Variable: `IMOWI_API_URL=https://tu-api.onrender.com`

### 4. CORS

En Render, configurá:

```env
CORS_ORIGINS=https://tu-sitio.netlify.app
```

---

## Docker (alternativa)

```bash
cp .env.example .env
docker compose up -d --build
# http://localhost:8000
```

---

## Estructura del proyecto

```
app/
  routers/          # Endpoints REST
  services/         # Chat, extracción, inferencia
  knowledge_rag.py  # RAG sobre Markdown
  tickets_store.py  # JSON local o delegación a Supabase
main.py             # FastAPI
index.html          # Frontend (también servido en local)
config.js           # URL API (Netlify build)
Base_de_Conocimiento_Tickets.md
supabase/schema.sql
```

---

## Licencia

Uso interno — demo imowi / Vertia.
