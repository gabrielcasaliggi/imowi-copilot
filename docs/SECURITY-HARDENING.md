# Deploy y hardening — Operations Hub (ibot.ecolan.com)

## Identidades

| Superficie | Login | JWT |
|---|---|---|
| Consola | email + password (invite) | `typ=console` + `AUTH_SECRET` |
| Portal abonado | DNI → BillTrack RO → OTP email (o PIN) | `typ=portal` + `PORTAL_AUTH_SECRET` |

Nunca mezclar tokens. BillTrack es **solo lectura**.

## Defaults de producción (Fase B)

| Variable | Default en `APP_ENV=production` | Notas |
|---|---|---|
| `PORTAL_ALLOW_GUEST` | `false` | Guest anónimo bloqueado; solo DNI+OTP |
| `ENABLE_API_DOCS` | `false` | Sin `/docs`, `/redoc`, `/openapi.json` |
| `ENABLE_LEGACY_API` | `false` | Sin `/api/chat` ni UI HTML legacy en `/` |
| `WHATSAPP_APP_SECRET` | (requerido si hay WA) | Valida `X-Hub-Signature-256` en el webhook |

### Cookies HttpOnly (Fase B cierre)

| Cookie | Path | Uso |
|---|---|---|
| `ops_console_token` | `/api` | JWT consola (`typ=console`) |
| `ops_portal_token` | `/api` | JWT portal (`typ=portal`) |

- `HttpOnly` + `SameSite=Lax` + `Secure` en production.
- Dual-path: si hay `Authorization: Bearer` se usa; si no, la cookie.
- El FE sigue pudiendo guardar token en `localStorage`/`sessionStorage` como fallback (dev / clients viejos).
- `CORS_ORIGINS` debe ser explícito (ej. `https://ibot.ecolan.com`) para enviar cookies cross-origin; en nginx same-origin con `/api` proxy es lo ideal.

## Deploy seguro (producción)

1. **Backup** Data Estate: `sudo bash scripts/backup-estate.sh`
2. `cd /opt/ops-hub` (o ruta del repo) && `git pull`
3. Backend: `.venv/bin/pip install -r requirements.txt` → reiniciar API
   - `sudo systemctl restart operations-hub-api`
   - Migraciones aditivas corren al boot (`migrate_schema`); Alembic baseline: `alembic stamp head` en DB existentes
4. Frontend: `cd frontend && npm ci && npm run build && sudo systemctl restart operations-hub-frontend`
5. Nginx: `sudo nginx -t && sudo systemctl reload nginx`
6. Verificar: `./scripts/verify-production.sh https://ibot.ecolan.com`

### Checklist post-deploy

- [ ] `curl -fsS https://ibot.ecolan.com/health` → ok
- [ ] `curl -fsS https://ibot.ecolan.com/ready` → `ready: true` (503 si DB caída)
- [ ] Login demo (`admin`/`admin`) **falla** (`DISABLE_DEMO_USERS=true`)
- [ ] Invite → set password → login OK
- [ ] Portal: DNI + OTP (SMTP) emite JWT; token consola no abre `/api/v1/portal/messages`
- [ ] Guest `/api/v1/portal/session` → **401** (si `PORTAL_ALLOW_GUEST=false`)
- [ ] `/docs` → **404**
- [ ] HSTS presente: `curl -sI https://ibot.ecolan.com | grep -i strict-transport`
- [ ] `/api/listar-tickets` sin token → 401
- [ ] WhatsApp: `WHATSAPP_APP_SECRET` seteado; POST sin firma → 403
- [ ] Cron alerta: `sudo bash scripts/install-ready-alert-cron.sh`

## WhatsApp HMAC

Meta firma el body con el App Secret. En production, si falta el secret el webhook responde **503**.
Con secret configurado, se exige header `X-Hub-Signature-256: sha256=<hmac>`.

## Rotación de secretos

1. Generar nuevos: `openssl rand -hex 32`
2. Opciones:
   - **Ventana de re-login**: setear `AUTH_SECRET` / `PORTAL_AUTH_SECRET` nuevos → todos los JWT previos dejan de validar (usuarios reingresan).
   - Portal y consola son independientes: podés rotar uno sin el otro.
3. Tras rotar `AUTH_SECRET`, también rotá `DNI_PEPPER` solo si entendés que invalidará `dni_hash` locales (mejor dejar pepper estable).
4. Documentar en runbook interno la fecha de rotación.

## Backup / restore

```bash
# Backup
sudo bash scripts/backup-estate.sh /var/backups/ops-hub

# Restore en staging (recomendado)
sudo bash scripts/restore-estate.sh /var/backups/ops-hub/ops_hub_estate_latest.dump \
  --url 'postgresql://ops_hub:...@127.0.0.1/ops_hub_restore' --yes

# Restore sobre la DB de producción (peligroso)
# sudo bash scripts/restore-estate.sh /var/backups/ops-hub/ops_hub_estate_latest.dump \
#   --yes --i-understand-this-wipes-target
```

Cron sugerido:

```bash
sudo bash /opt/operations-hub/scripts/install-backup-cron.sh
sudo bash /opt/operations-hub/scripts/install-ready-alert-cron.sh
```

## Fail-fast de configuración (production)

Con `APP_ENV=production` la API **aborta el boot** si:

- `AUTH_SECRET` / `PORTAL_AUTH_SECRET` ausentes, débiles, iguales entre sí o con menos de 32 chars
- `DATABASE_URL` no es PostgreSQL
- `CORS_ORIGINS` es `*` o vacío
- usuarios demo activos / `ENABLE_DEMO_RESET=true`

Escape hatch temporal: `ALLOW_INSECURE_PROD=true` (solo rescate; loguea warning).

## Host hardening (runbook)

- UFW: allow 22/tcp (solo IP admin si es posible), 80/tcp, 443/tcp; deny resto.
- SSH por clave; desactivar password auth.
- Postgres Data Estate solo en `127.0.0.1`.
- Rol BillTrack: `GRANT SELECT` únicamente sobre vistas/tablas de padrón.
- Certbot + HSTS (ver `deploy/nginx/operations-hub.conf`).
- `/docs` y legacy deshabilitados por defaults de app (arriba); no hace falta restringir por nginx salvo override.

## Fuera de alcance (defaults seguros)

- SMS/WhatsApp OTP (costos proveedor) — Fase 4.
- WebAuthn — post–piloto.
- Escrituras a BillTrack — **prohibidas siempre**.
