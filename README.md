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
| **DB** | Supabase PostgreSQL | Data Estate completo (`DATABASE_URL`) |
| **LLM** | Groq (u otro) | Respuestas del Copilot |

Guía paso a paso: [docs/PRODUCCION-SUPABASE.md](./docs/PRODUCCION-SUPABASE.md) (recomendado) · [DEPLOY-NETLIFY-SUPABASE.md](./DEPLOY-NETLIFY-SUPABASE.md) (legacy UI estática)

---

## Desarrollo local

### Requisitos

- Python 3.12+
- Ollama local **o** API key de Groq

### Instalación

```bash
bash scripts/setup-dev.sh
```

Si `python3 -m venv` falla en Ubuntu/Debian, instalá primero:

```bash
sudo apt update && sudo apt install -y python3.14-venv
```

El script crea `.venv`, instala `requirements-dev.txt` y copia `.env.example` a `.env`
si todavía no existe.

### Ejecutar

```bash
./run.sh
```

Abrí **http://127.0.0.1:8000** (UI legacy) o el frontend Next.js (recomendado):

```bash
cd frontend
cp .env.local.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000
npm install
npm run dev
```

Frontend en **http://localhost:3000**. Agregar `http://localhost:3000` en `CORS_ORIGINS` del `.env` del backend.

### Validación local

```bash
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/ruff format .
```

### Login local (réplica operativa)

| Usuario | Contraseña | Rol |
|---------|------------|-----|
| `batan` | `batan` | Operador Cooperativa Batán |
| `viamonte` | `viamonte` | Operador Cooperativa Viamonte |
| `admin` | `admin` | NOC imowi — vista global |

Guía de uso operativo: [docs/USO-LOCAL-PRODUCTIVO.md](./docs/USO-LOCAL-PRODUCTIVO.md)

En producción cambiá contraseñas vía variables `ADMIN_PASSWORD`, `COOP_PASSWORD`, etc.

---

## Variables de entorno (API)

| Variable | Obligatoria en prod | Descripción |
|----------|---------------------|-------------|
| `APP_ENV` | Sí → `production` | Activa validaciones de seguridad |
| `DATABASE_URL` | Sí | PostgreSQL Supabase (pooler `:6543`) |
| `DATABASE_SSLMODE` | Recomendado | `require` (default) |
| `AUTH_SECRET` | Sí | Secreto JWT (`openssl rand -hex 32`) |
| `AI_BASE_URL` | Sí | URL del LLM |
| `AI_API_KEY` | Sí | Clave del proveedor |
| `AI_MODEL` | Sí | Modelo (ej. `llama-3.3-70b-versatile`) |
| `SUPABASE_URL` | Opcional | Mirror REST legacy de tickets |
| `SUPABASE_SERVICE_KEY` | Opcional | Service role (solo backend) |
| `CORS_ORIGINS` | Recomendado | URL del frontend |

Frontend (Netlify build):

| Variable | Descripción |
|----------|-------------|
| `IMOWI_API_URL` | URL pública de la API, ej. `https://xxx.onrender.com` |

---

## Supabase (producción)

1. Creá proyecto en [supabase.com](https://supabase.com)
2. **Settings → Database → Connection string** → URI (Transaction pooler) → `DATABASE_URL` en Render
3. Al primer arranque la API crea tablas y ejecuta seed automáticamente

Detalle: [docs/PRODUCCION-SUPABASE.md](./docs/PRODUCCION-SUPABASE.md)

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
