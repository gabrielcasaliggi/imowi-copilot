# Soporte Batán (Operations Hub)

Consola de soporte para **Cooperativa Batán**: portal web del abonado (bot N1 → agente), bandeja de agentes, tickets N2, base de conocimiento e IA.

- Abonados: [`/portal`](./docs/PORTAL-ABONADO.md) y app nativa [`mobile/`](./mobile/README.md)  
- Agentes/admin: login consola  
- Roles y permisos (diseño): [`docs/RBAC-ROLES-PERMISOS.md`](./docs/RBAC-ROLES-PERMISOS.md)  
- WhatsApp Meta: fase posterior  

Las APIs legacy de telemetría/JSC pueden existir en el backend pero **no forman parte de la UI operativa**.

## Arquitectura (producción)

```
Nginx (HTTPS)  ──►  Next.js :3000   (consola + portal)
               ──►  FastAPI :8000   ──►  PostgreSQL (Supabase / local)
                                    ──►  Groq / LLM compatible OpenAI
App nativa (Expo) ──► FastAPI /api/v1/portal/*  (canal=app, mismo Eko)
```

| Componente | Dónde | Qué hace |
|------------|-------|----------|
| **Frontend** | Next.js + systemd (nginx) | Consola ops + portal abonado |
| **App abonado** | `mobile/` (Expo) | Eko en el smartphone: chat, voz, push |
| **API** | FastAPI + systemd | Chat, RAG, tickets, auth JWT |
| **DB** | PostgreSQL (Supabase u host) | Data Estate completo (`DATABASE_URL`) |
| **LLM** | Groq (u otro) | Respuestas del Copilot |

Prod actual: `https://ibot.ecolan.com`. Guía: [DEPLOY.md](./DEPLOY.md) · [docs/FRONTEND-DEPLOY.md](./docs/FRONTEND-DEPLOY.md) · [docs/PRODUCCION-SUPABASE.md](./docs/PRODUCCION-SUPABASE.md)

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

API en **http://127.0.0.1:8000**. Frontend Next.js (recomendado):

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
| `admin` | `admin` | Administrador — plataforma |
| `supervisor` | `supervisor` | Supervisor Batán |
| `ejecutivo` | `ejecutivo` | Ejecutivo Batán |
| `batan` | `batan` | Agente Batán |
| `viamonte` | `viamonte` | Agente Viamonte |

Roles y permisos: [docs/RBAC-ROLES-PERMISOS.md](./docs/RBAC-ROLES-PERMISOS.md)

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

Frontend (`frontend/.env.local`):

| Variable | Descripción |
|----------|-------------|
| `NEXT_PUBLIC_API_URL` | URL pública de la API, ej. `https://ibot.ecolan.com` |

---

## Supabase (producción)

1. Creá proyecto en [supabase.com](https://supabase.com)
2. **Settings → Database → Connection string** → URI (Transaction pooler) → `DATABASE_URL`
3. Al primer arranque la API crea tablas y ejecuta seed automáticamente

Detalle: [docs/PRODUCCION-SUPABASE.md](./docs/PRODUCCION-SUPABASE.md) · despliegue nativo: [DEPLOY.md](./DEPLOY.md)

---

## Docker (alternativa)

```bash
cp .env.example .env
docker compose -f deploy/docker-compose.yml --env-file .env up -d --build
```

---

## Estructura del proyecto

```
app/                # FastAPI (API v1, agents, estate, services)
frontend/           # Next.js (consola + portal)
deploy/             # nginx + systemd + docker-compose
main.py             # Entrypoint FastAPI
Base_de_Conocimiento_Tickets.md
```

---

## Licencia

Uso interno — demo Vertia.
