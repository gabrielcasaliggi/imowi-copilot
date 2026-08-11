# Fase 1 — Batán / Ecolan (producción operable)

Objetivo: subir confiabilidad del despliegue **único** (`ibot.ecolan.com`) antes de pensar en multi-ISP.

Multi-tenant / white-label / billing: **fuera de esta fase**.

---

## Checklist en servidor

### A. Deploy del código

```bash
cd /opt/operations-hub
# Recomendado (backup → pull → build → restart → /ready → smoke):
sudo bash scripts/deploy-hardening-prod.sh

# O manual:
sudo bash scripts/backup-estate.sh
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart operations-hub-api
sleep 3
curl -fsS https://ibot.ecolan.com/health | python3 -m json.tool
curl -fsS https://ibot.ecolan.com/ready | python3 -m json.tool
```

Health (liveness) debe incluir:

- `"status": "ok"`
- `"demo_reset_enabled": false` (en production)
- `"sentry_configured": true` si cargaste `SENTRY_DSN`
- `"ready": "/ready"`

`/ready` (readiness) debe ser HTTP 200 con `"ready": true`. Si la DB cae → **503** (systemd puede seguir “active”).

En `APP_ENV=production` la API **no arranca** si faltan secretos ≥32, Postgres, CORS explícito, o hay demos/reset activos. Escape hatch de emergencia: `ALLOW_INSECURE_PROD=true` (solo rescate).

### B. Parche `.env` (una vez)

```bash
sudo nano /opt/operations-hub/.env
```

Asegurá (valores entre comillas si tienen espacios/`@`/`<>`):

```bash
APP_ENV=production
DISABLE_DEMO_USERS=true
ENABLE_DEMO_RESET=false
ENABLE_LEGACY_API=false
ENABLE_API_DOCS=false
# Guest: true solo si el piloto lo necesita; false es más estricto
# PORTAL_ALLOW_GUEST=false

# Comillas obligatorias si hay espacios:
SMTP_FROM="Soporte Batán <noreply@tudominio.com>"

# Observabilidad (recomendado)
# SENTRY_DSN=https://...@sentry.io/...
# SENTRY_TRACES_SAMPLE_RATE=0.1

# WhatsApp (cuando activen el número)
# WHATSAPP_TOKEN=...
# WHATSAPP_PHONE_NUMBER_ID=...
# WHATSAPP_APP_SECRET=...
# WHATSAPP_VERIFY_TOKEN=...
# WHATSAPP_DEFAULT_ORG_SLUG=coop-batan
```

Reiniciá API tras editar `.env`.

### C. Backup diario + alerta /ready + drill restore

```bash
sudo bash /opt/operations-hub/scripts/install-backup-cron.sh
sudo bash /opt/operations-hub/scripts/backup-estate.sh
ls -lh /var/backups/ops-hub/

# Alerta cada 2 min (webhook/email opcional en /etc/default/operations-hub-alert)
sudo bash /opt/operations-hub/scripts/install-ready-alert-cron.sh
sudo bash /opt/operations-hub/scripts/alert-ready.sh

# Drill mensual en staging (NO producción):
# sudo bash scripts/restore-estate.sh /var/backups/ops-hub/ops_hub_estate_latest.dump \
#   --url 'postgresql://user:pass@127.0.0.1:5432/ops_hub_staging' --yes
```

### D. Smoke Fase 1

```bash
cd /opt/operations-hub
chmod +x scripts/fase1-smoke-batan.sh scripts/install-backup-cron.sh scripts/backup-estate.sh

# Mínimo
./scripts/fase1-smoke-batan.sh https://ibot.ecolan.com

# Completo (login + anti-ticket + QR)
VERIFY_USER='tu@email' VERIFY_PASSWORD='...' \
  ./scripts/fase1-smoke-batan.sh https://ibot.ecolan.com
```

También: `./scripts/verify-production.sh https://ibot.ecolan.com`

---

## Qué cambió en código (Fase 1)

| Cambio | Efecto |
|--------|--------|
| `ENABLE_DEMO_RESET` off en prod | `POST /api/v1/demo/reset` → 403 |
| Reset exige admin/supervisor | Menos wipe accidental |
| Backup `.env` seguro | No ejecuta `batan.coop` como comando |
| Cron installer | Backup diario automático |
| `/health` → `sentry_configured`, `demo_reset_enabled` | Visibilidad ops |
| `/ready` 200/503 | Readiness real (DB) |
| Fail-fast boot prod | No arranca con secretos/CORS/demos inseguros |
| `restore-estate.sh` + alerta cron | RTO y detección de caída |
| Warnings boot | Sentry vacío, WA incompleto |
| Smoke `fase1-smoke-batan.sh` | Anti-ticket + QR + webhook WA + /ready |

---

## Checklist WhatsApp prod

- [ ] Token + phone number id
- [ ] App secret (HMAC) — POST sin firma → 403/503
- [ ] Verify token = Meta
- [ ] `WHATSAPP_DEFAULT_ORG_SLUG=coop-batan`
- [ ] Mensaje real de prueba
- [ ] Admin → test WhatsApp OK

Ver `docs/FASE-C.md` § checklist WA.

---

## Smoke manual portal (5 min)

1. Invitado → “Quiero un operador” → **sin** ticket  
2. `*agente*` → sí ticket  
3. “Me cortaron por falta de pago” → menciona **QR Fiserv**  
4. “En el living anda bien, lejos no” → **no** cierra como resuelto  

---

## Definition of Done (Fase 1)

- [ ] Backup cron instalado y dump reciente en `/var/backups/ops-hub`
- [ ] Cron `/ready` instalado (`install-ready-alert-cron.sh`)
- [ ] Drill restore en staging al menos 1 vez (`restore-estate.sh`)
- [ ] `demo_reset_enabled: false` en health prod
- [ ] `curl -fsS …/ready` → `ready: true`
- [ ] `fase1-smoke-batan.sh` en verde
- [ ] SMTP_FROM entre comillas (sin error al backup)
- [ ] Sentry DSN cargado **o** riesgo aceptado documentado
- [ ] WhatsApp: operativo **o** explícitamente “próximo sprint” con HMAC listo cuando haya token
- [ ] 1 semana de operación estable con agentes Batán

Cuando todo esté checked → abrir Fase 2 (white-label / 2º cliente).
