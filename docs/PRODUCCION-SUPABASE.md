# Producción con PostgreSQL (Data Estate)

En producción el **Data Estate** persiste en **PostgreSQL** (Supabase u otro proveedor), no en SQLite.

```
┌──────────────────┐     HTTPS      ┌──────────────────┐     ┌─────────────────────┐
│  Nginx           │ ─────────────► │  FastAPI :8000   │ ──► │  PostgreSQL         │
│  (reverse proxy) │                │  (systemd)       │     │  Data Estate        │
└──────────────────┘                └──────────────────┘     └─────────────────────┘
          │
          ▼
┌──────────────────┐
│  Next.js :3000   │
│  (systemd)       │
└──────────────────┘
```

Al arrancar la API, `aplicar_schema` crea tablas solo si el estate está vacío; si ya hay `tickets_estate` en production no corre `create_all`. El seed corre si la base está vacía.

---

## 1. Crear proyecto PostgreSQL

Opciones: Supabase, un Postgres dedicado en el mismo VPS, u otro proveedor managed.

### Con Supabase

1. [supabase.com](https://supabase.com) → New project.
2. Guardá la contraseña de la base (`postgres`).
3. **Settings → Database → Connection string**:
   - Modo **URI**
   - **Transaction pooler** (puerto `6543`) — recomendado para conexiones desde el backend
   - Copiá la URL; reemplazá `[YOUR-PASSWORD]`.

Ejemplo:

```env
DATABASE_URL=postgresql://postgres.abcdefgh:miClaveSegura@aws-0-sa-east-1.pooler.supabase.com:6543/postgres
DATABASE_SSLMODE=require
```

---

## 2. Variables en el servidor

En `.env` del backend (`/opt/operations-hub/.env`):

| Variable | Obligatoria | Descripción |
|----------|-------------|-------------|
| `APP_ENV` | Sí | `production` |
| `DATABASE_URL` | Sí | URI Postgres |
| `DATABASE_SSLMODE` | Recomendado | `require` (default) |
| `AUTH_SECRET` | Sí | `openssl rand -hex 32` |
| `PORTAL_AUTH_SECRET` | Sí | `openssl rand -hex 32` (distinto de AUTH_SECRET) |
| `AI_BASE_URL` | Sí | endpoint LLM |
| `AI_API_KEY` | Sí | clave del proveedor LLM |
| `AI_MODEL` | Sí | modelo |
| `CORS_ORIGINS` | Sí | `https://ibot.ecolan.com,https://soporte.ecolan.com` |
| `ADMIN_PASSWORD` / `COOP_PASSWORD` | Sí | contraseñas fuertes para seed |

---

## 3. Deploy

1. Push a GitHub → CI verde.
2. En el servidor: `bash scripts/install-server.sh --domain ibot.ecolan.com --portal-domain soporte.ecolan.com`.
3. Verificar:

```bash
curl https://ibot.ecolan.com/api/health
```

Respuesta esperada:

```json
{
  "status": "ok",
  "database": "postgresql",
  "estate": true,
  "estate_seeded": true
}
```

4. Login con el usuario admin del seed.

---

## 4. Frontend

El frontend se configura con variables de entorno en `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=https://ibot.ecolan.com/api
NEXT_PUBLIC_CONSOLE_HOST=ibot.ecolan.com
NEXT_PUBLIC_PORTAL_HOST=soporte.ecolan.com
```

`CORS_ORIGINS` en la API debe incluir ambos dominios.

---

## 5. Desarrollo local

Por defecto sigue usando SQLite:

```env
DATABASE_URL=sqlite:///./data/estate.db
```

Para probar contra Postgres, pegá la misma `DATABASE_URL` del proyecto.

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Los tests usan SQLite en memoria y no requieren Postgres.

---

## 6. Migraciones

Cambios de columnas nuevas se aplican en startup vía `app/estate/migrate.py` (compatible SQLite y PostgreSQL con `ADD COLUMN IF NOT EXISTS`).

Para cambios de esquema mayores, usar Alembic (`alembic upgrade head`).

---

## 7. Mirror REST legacy (`tickets_store`)

Si `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` están configurados, los tickets del flujo legacy también se espejan a la tabla `tickets` vía API REST. Con el estate en el mismo Postgres, **el mirror es opcional**: la fuente de verdad es `tickets_estate` en `DATABASE_URL`.
