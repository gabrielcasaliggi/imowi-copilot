# Producción con Supabase PostgreSQL (Data Estate completo)

En producción el **Data Estate** (organizaciones, usuarios, tickets, casos de conversación, KB, telemetría, eventos) persiste en **PostgreSQL de Supabase**, no en SQLite ni en disco de Render.

```
┌─────────────────┐     HTTPS      ┌──────────────────┐     ┌─────────────────────┐
│  Frontend       │ ─────────────► │  Render (API)    │ ──► │  Supabase Postgres  │
│  Next.js/Vercel │                │  FastAPI         │     │  Data Estate        │
└─────────────────┘                └──────────────────┘     └─────────────────────┘
```

Al arrancar la API, SQLAlchemy crea las tablas (`create_all`) y ejecuta el seed si la base está vacía.

---

## 1. Crear proyecto Supabase

1. [supabase.com](https://supabase.com) → New project.
2. Guardá la contraseña de la base (`postgres`).
3. **Settings → Database → Connection string**:
   - Modo **URI**
   - **Transaction pooler** (puerto `6543`) — recomendado para Render
   - Copiá la URL; reemplazá `[YOUR-PASSWORD]` por la contraseña real (URL-encode si tiene caracteres especiales).

Ejemplo:

```env
DATABASE_URL=postgresql://postgres.abcdefgh:miClaveSegura@aws-0-sa-east-1.pooler.supabase.com:6543/postgres
DATABASE_SSLMODE=require
```

> No hace falta ejecutar `supabase/schema.sql` manualmente: el esquema legacy de `tickets` era para el mirror REST. El estate usa tablas `tickets_estate`, `organizations`, etc., creadas al iniciar la API.

---

## 2. Variables en Render

En el Web Service de la API:

| Variable | Obligatoria | Descripción |
|----------|-------------|-------------|
| `APP_ENV` | Sí | `production` |
| `DATABASE_URL` | Sí | URI Postgres de Supabase (pooler 6543) |
| `DATABASE_SSLMODE` | Recomendado | `require` (default) |
| `AUTH_SECRET` | Sí | `openssl rand -hex 32` |
| `AI_BASE_URL` | Sí | p. ej. Groq |
| `AI_API_KEY` | Sí | clave del proveedor LLM |
| `AI_MODEL` | Sí | modelo |
| `CORS_ORIGINS` | Sí | URL del frontend |
| `ADMIN_PASSWORD` / `COOP_PASSWORD` | Sí | contraseñas fuertes para seed |
| `SUPABASE_URL` | Opcional | solo si usás mirror REST legacy |
| `SUPABASE_SERVICE_KEY` | Opcional | idem |

[render.yaml](../render.yaml) ya incluye `DATABASE_URL` y `DATABASE_SSLMODE`.

**No necesitás disco persistente en Render** si `DATABASE_URL` apunta a Supabase.

---

## 3. Primer deploy

1. Push a GitHub.
2. Render → conectar repo → configurar env (sobre todo `DATABASE_URL`).
3. Deploy. En logs deberías ver:
   - `Data Estate [postgresql+psycopg://postgres.***@...]`
   - `seeded: true` en la primera ejecución.
4. Verificar:

```bash
./scripts/verify-production.sh https://tu-api.onrender.com
curl https://tu-api.onrender.com/health
```

Respuesta esperada:

```json
{
  "status": "ok",
  "database": "postgresql",
  "estate": true,
  "estate_seeded": true,
  ...
}
```

5. Login con el usuario admin del seed (`ADMIN_USER` / `ADMIN_PASSWORD`).

---

## 4. Frontend

En Vercel/Netlify/local:

```env
NEXT_PUBLIC_API_URL=https://tu-api.onrender.com
```

`CORS_ORIGINS` en la API debe incluir la URL exacta del frontend.

---

## 5. Desarrollo local

Por defecto sigue usando SQLite:

```env
DATABASE_URL=sqlite:///./data/estate.db
```

Para probar contra Supabase desde tu máquina, pegá la misma `DATABASE_URL` del proyecto (pooler o direct `5432`).

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Los tests usan SQLite en memoria y no requieren Postgres.

---

## 6. Migraciones

Cambios de columnas nuevas se aplican en startup vía `app/estate/migrate.py` (compatible SQLite y PostgreSQL con `ADD COLUMN IF NOT EXISTS`).

Para cambios de esquema mayores, preferí migraciones explícitas o Alembic en el futuro.

---

## 7. Mirror REST legacy (`tickets_store`)

Si `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` están configurados, los tickets del flujo legacy también se espejan a la tabla `tickets` vía API REST. Con el estate en el mismo Postgres, **el mirror es opcional**: la fuente de verdad es `tickets_estate` en `DATABASE_URL`.
