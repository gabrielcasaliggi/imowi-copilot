# Despliegue — Operations Hub

Ver también: [docs/SECURITY-HARDENING.md](docs/SECURITY-HARDENING.md) (auth dual, backup, rotación de secretos).

## Producción nativa (ibot.ecolan.com)

Marca abonado: **Soporte Batán** / asistente **Eco**. Dominio futuro recomendado: `soporte.batan.coop` (ver [docs/ECO-VOICE.md](docs/ECO-VOICE.md)); no migrar DNS en este paso.

```bash
# 1) Backup
sudo bash scripts/backup-estate.sh

# 2) Código
cd /ruta/al/repo && git pull

# 3) Backend
source .venv/bin/activate
pip install -r requirements.txt
# Migraciones: create_all + migrate_schema al reiniciar;
# esquema versionado (baseline): alembic stamp head  (ver docs/QA-PILOTO.md / alembic/)
sudo systemctl restart operations-hub-api

# 4) Frontend
cd frontend && npm ci && npm run build
sudo systemctl restart operations-hub-frontend   # ajustar unit

# 5) Nginx
sudo nginx -t && sudo systemctl reload nginx
```

Plantilla env: `.env.server.example` (`DISABLE_DEMO_USERS`, `SMTP_*`, `PORTAL_AUTH_SECRET`, `BILLTRACK_LOOKUP_*`).

### Checklist

- [ ] Health OK
- [ ] Demo users desactivados
- [ ] Invite + change-password OK
- [ ] Portal DNI+OTP OK (BillTrack RO)
- [ ] HSTS / headers seguridad
- [ ] Legacy `/api/listar-tickets` requiere auth

---

## Qué persiste hoy

| Dato | Ubicación | Notas |
|------|-----------|--------|
| Data Estate | PostgreSQL (`DATABASE_URL`) | tickets, users, portal links, audit |
| BillTrack | Postgres externo RO | padrón — sin writes |
| Base conocimiento | `Base_de_Conocimiento_Tickets.md` | solo lectura en image |

---

## Opción: Docker (VPS o local)

```bash
cp .env.example .env
docker compose up -d --build
```

---

## VPS (sin Docker)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.server.example .env   # producción
# editar secretos

uvicorn main:app --host 127.0.0.1 --port 8000
```

Usá **systemd** + **nginx** con HTTPS (Let's Encrypt). Ver `deploy/nginx/operations-hub.conf`.

---

## Checklist seguridad (resumen)

- [ ] `AUTH_SECRET` y `PORTAL_AUTH_SECRET` distintos y fuertes
- [ ] `DISABLE_DEMO_USERS=true` en production
- [ ] SMTP configurado para invites/OTP
- [ ] BillTrack: usuario solo SELECT + `BILLTRACK_LOOKUP_SQL`
- [ ] Backup diario Data Estate
- [ ] UFW 22/80/443; SSH por clave
