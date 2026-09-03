#!/usr/bin/env bash
# Deploy hardening producción — Operations Hub
# Uso (en el server):
#   cd /opt/operations-hub && sudo bash scripts/deploy-hardening-prod.sh
#
# Qué hace:
#   1) Backup Postgres Data Estate
#   2) git pull
#   3) Parchea .env (agrega vars nuevas sin tocar secretos existentes)
#   4) pip + build frontend
#   5) restart systemd
#   6) /health + /ready + smoke Fase 1
#   7) Recuerda rollback si smoke falla
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/operations-hub}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/ops-hub}"
ENV_FILE="$APP_ROOT/.env"
API_UNIT="${API_UNIT:-operations-hub-api}"
FE_UNIT="${FE_UNIT:-operations-hub-frontend}"

red() { printf '\033[31m%s\033[0m\n' "$*"; }
grn() { printf '\033[32m%s\033[0m\n' "$*"; }
ylw() { printf '\033[33m%s\033[0m\n' "$*"; }

if [[ "$(id -u)" -ne 0 ]]; then
  red "Corré con sudo: sudo bash $0"
  exit 1
fi

if [[ ! -d "$APP_ROOT" ]]; then
  red "No existe $APP_ROOT"
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  red "No existe $ENV_FILE"
  exit 1
fi

cd "$APP_ROOT"
APP_USER="$(stat -c '%U' "$APP_ROOT")"
ylw "==> App root: $APP_ROOT (user=$APP_USER)"

# ── helpers .env ────────────────────────────────────────────────────────────
env_get() {
  local key="$1"
  grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d= -f2- || true
}

env_set() {
  local key="$1"
  local val="$2"
  local tmp
  tmp="$(mktemp)"
  if grep -qE "^${key}=" "$ENV_FILE"; then
    # reemplaza la última ocurrencia de la clave
    awk -v k="$key" -v v="$val" '
      BEGIN { done=0 }
      {
        if ($0 ~ "^" k "=") { last=NR }
        lines[NR]=$0
      }
      END {
        for (i=1; i<=NR; i++) {
          if (i==last) print k "=" v
          else print lines[i]
        }
        if (!last) print k "=" v
      }
    ' "$ENV_FILE" >"$tmp"
    mv "$tmp" "$ENV_FILE"
  else
    printf '\n%s=%s\n' "$key" "$val" >>"$ENV_FILE"
    rm -f "$tmp"
  fi
}

env_set_if_empty() {
  local key="$1"
  local val="$2"
  local cur
  cur="$(env_get "$key")"
  if [[ -z "$cur" ]]; then
    env_set "$key" "$val"
    ylw "    + $key (nuevo)"
  else
    grn "    = $key (ya existía, no se toca)"
  fi
}

# ── 1) Backup ───────────────────────────────────────────────────────────────
ylw "==> 1/6 Backup Data Estate"
mkdir -p "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="$BACKUP_DIR/ops_hub_estate_${STAMP}.dump"

# NO hacer "source .env": valores con espacios sin comillas rompen el script
# (ej. COOP_NOMBRE=Operador Prueba → bash intenta ejecutar "Prueba").
DB_URL="$(env_get DATABASE_URL)"
PG_USER="$(env_get POSTGRES_USER)"
PG_PASS="$(env_get POSTGRES_PASSWORD)"
PG_DB="$(env_get POSTGRES_DB)"
if [[ -z "$DB_URL" && -n "$PG_USER" && -n "$PG_DB" ]]; then
  DB_URL="postgresql://${PG_USER}:${PG_PASS}@127.0.0.1:5432/${PG_DB}"
fi
if [[ -z "$DB_URL" ]]; then
  red "No hay DATABASE_URL ni POSTGRES_* en .env"
  exit 1
fi
PG_URL="${DB_URL/postgresql+psycopg:\/\//postgresql:\/\/}"
PG_URL="${PG_URL/postgresql+psycopg2:\/\//postgresql:\/\/}"

if command -v pg_dump >/dev/null 2>&1; then
  pg_dump --format=custom --file="$BACKUP_FILE" "$PG_URL"
  ln -sfn "$(basename "$BACKUP_FILE")" "$BACKUP_DIR/ops_hub_estate_latest.dump"
  grn "    Backup OK: $BACKUP_FILE"
else
  red "pg_dump no encontrado — aborto (no deploy sin backup)"
  exit 1
fi

# ── 2) git pull ─────────────────────────────────────────────────────────────
ylw "==> 2/6 git pull"
sudo -u "$APP_USER" git -C "$APP_ROOT" fetch origin
sudo -u "$APP_USER" git -C "$APP_ROOT" pull --ff-only origin main
grn "    $(sudo -u "$APP_USER" git -C "$APP_ROOT" rev-parse --short HEAD)"

# ── 3) Parche .env ──────────────────────────────────────────────────────────
ylw "==> 3/6 Parche .env (seguro)"
cp -a "$ENV_FILE" "${ENV_FILE}.bak.${STAMP}"
grn "    Copia: ${ENV_FILE}.bak.${STAMP}"

# Forzar flags de hardening
env_set "APP_ENV" "production"
env_set "DISABLE_DEMO_USERS" "true"
env_set "ENABLE_DEMO_RESET" "false"
env_set "ENABLE_LEGACY_API" "false"
env_set "ENABLE_API_DOCS" "false"
env_set "AUTH_TOKEN_HOURS" "12"
env_set "PORTAL_TOKEN_HOURS" "4"
env_set "CONSOLE_JWT_AUD" "ops-hub-console"
env_set "PORTAL_JWT_AUD" "ops-hub-portal"
env_set "PORTAL_AUTH_MODE" "dni_otp"
# Guest: no forzar true (piloto puede pedirlo; default seguro es false)
# Solo setear si falta la clave
if ! grep -qE '^PORTAL_ALLOW_GUEST=' "$ENV_FILE"; then
  env_set "PORTAL_ALLOW_GUEST" "false"
fi
env_set "PUBLIC_URL" "https://ibot.ecolan.com"
env_set "PORTAL_DOMAIN" "soporte.ecolan.com"
env_set "CORS_ORIGINS" "https://ibot.ecolan.com,https://soporte.ecolan.com"

# PORTAL_AUTH_SECRET: generar solo si falta
PORTAL_SEC="$(env_get PORTAL_AUTH_SECRET)"
AUTH_SEC="$(env_get AUTH_SECRET)"
if [[ -z "$PORTAL_SEC" || "$PORTAL_SEC" == "$AUTH_SEC" ]]; then
  NEW_PORTAL="$(openssl rand -hex 32)"
  env_set "PORTAL_AUTH_SECRET" "$NEW_PORTAL"
  ylw "    + PORTAL_AUTH_SECRET generado (distinto de AUTH_SECRET)"
else
  grn "    = PORTAL_AUTH_SECRET ya OK"
fi

# OTP / rate-limit defaults si faltan
env_set_if_empty "OTP_LENGTH" "6"
env_set_if_empty "OTP_TTL_MINUTES" "10"
env_set_if_empty "OTP_MAX_ATTEMPTS" "5"
env_set_if_empty "AUTH_LOGIN_MAX_FAILURES" "5"
env_set_if_empty "AUTH_LOGIN_WINDOW_MINUTES" "15"
env_set_if_empty "AUTH_LOCKOUT_MINUTES" "30"

chown "$APP_USER:$APP_USER" "$ENV_FILE"
chmod 600 "$ENV_FILE"

if ! grep -qE '^SMTP_HOST=.+' "$ENV_FILE"; then
  ylw "    ! SMTP_HOST no configurado — invites/OTP por mail no funcionarán hasta completarlo"
fi

# ── 4) deps + build ─────────────────────────────────────────────────────────
ylw "==> 4/6 Backend deps + frontend build"
if [[ ! -x "$APP_ROOT/.venv/bin/pip" ]]; then
  red "No hay $APP_ROOT/.venv — crealo antes o revisá el instalador"
  exit 1
fi
sudo -u "$APP_USER" "$APP_ROOT/.venv/bin/pip" install -r "$APP_ROOT/requirements.txt"

if [[ ! -d "$APP_ROOT/frontend" ]]; then
  red "No existe $APP_ROOT/frontend"
  exit 1
fi
sudo -u "$APP_USER" bash -lc "cd '$APP_ROOT/frontend' && npm ci && npm run build"

# ── 5) restart ──────────────────────────────────────────────────────────────
ylw "==> 5/7 Restart systemd"
unit_exists() {
  local u="$1"
  systemctl cat "${u}.service" >/dev/null 2>&1 \
    || systemctl cat "$u" >/dev/null 2>&1 \
    || [[ -f "/etc/systemd/system/${u}.service" ]] \
    || [[ -f "/lib/systemd/system/${u}.service" ]]
}

if unit_exists "$API_UNIT"; then
  systemctl restart "${API_UNIT}.service" 2>/dev/null || systemctl restart "$API_UNIT"
else
  red "Unit $API_UNIT no encontrado. Units disponibles:"
  systemctl list-units --type=service --all | grep -iE 'operat|ops|hub|uvicorn|next' || true
  exit 1
fi

if unit_exists "$FE_UNIT"; then
  systemctl restart "${FE_UNIT}.service" 2>/dev/null || systemctl restart "$FE_UNIT"
else
  ylw "    Unit $FE_UNIT no encontrado — reiniciá el frontend a mano si aplica"
fi

# Nginx: solo reload si el conf del repo está enlazado (no fuerza overwrite)
if command -v nginx >/dev/null 2>&1; then
  if nginx -t 2>/dev/null; then
    systemctl reload nginx || true
  fi
fi

sleep 2
if systemctl is-active --quiet "${API_UNIT}.service" 2>/dev/null \
  || systemctl is-active --quiet "$API_UNIT"; then
  grn "    $API_UNIT active"
else
  red "    $API_UNIT NO active"
  journalctl -u "$API_UNIT" -n 40 --no-pager
  exit 1
fi

# ── 6) checks ───────────────────────────────────────────────────────────────
ylw "==> 6/7 Checks liveness + readiness"
HEALTH="$(curl -fsS --max-time 10 http://127.0.0.1:8000/health || true)"
if echo "$HEALTH" | grep -q '"status"'; then
  grn "    health local OK: $HEALTH"
else
  red "    health local falló"
  journalctl -u "$API_UNIT" -n 60 --no-pager
  exit 1
fi

READY_CODE="$(curl -s -o /tmp/oh_ready.json -w '%{http_code}' --max-time 10 http://127.0.0.1:8000/ready || echo 000)"
READY_BODY="$(cat /tmp/oh_ready.json 2>/dev/null || true)"
if [[ "$READY_CODE" == "200" ]] && echo "$READY_BODY" | grep -q '"ready"[[:space:]]*:[[:space:]]*true'; then
  grn "    ready local OK: $READY_BODY"
else
  red "    /ready falló (HTTP $READY_CODE): $READY_BODY"
  journalctl -u "$API_UNIT" -n 60 --no-pager
  exit 1
fi

DEMO_CODE="$(curl -s -o /tmp/oh_login.json -w '%{http_code}' -X POST http://127.0.0.1:8000/api/login \
  -H 'Content-Type: application/json' \
  -d '{"usuario":"admin","password":"admin"}' || true)"
if [[ "$DEMO_CODE" == "401" || "$DEMO_CODE" == "429" ]]; then
  grn "    demo admin/admin rechazado (HTTP $DEMO_CODE) — OK"
else
  ylw "    demo login HTTP $DEMO_CODE (esperado 401). Body:"
  cat /tmp/oh_login.json 2>/dev/null || true
  echo
fi

LEGACY_CODE="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/api/listar-tickets || true)"
if [[ "$LEGACY_CODE" == "401" ]]; then
  grn "    /api/listar-tickets sin token → 401 OK"
else
  ylw "    /api/listar-tickets → HTTP $LEGACY_CODE (esperado 401)"
fi

# ── 7) smoke Fase 1 ─────────────────────────────────────────────────────────
ylw "==> 7/7 Smoke Fase 1 (local)"
SMOKE="$APP_ROOT/scripts/fase1-smoke-batan.sh"
if [[ -x "$SMOKE" || -f "$SMOKE" ]]; then
  chmod +x "$SMOKE" || true
  if sudo -u "$APP_USER" bash "$SMOKE" "http://127.0.0.1:8000"; then
    grn "    fase1-smoke OK"
  else
    red "    fase1-smoke FALLÓ — deploy incompleto"
    ylw "Rollback sugerido:"
    echo "  sudo -u $APP_USER git -C $APP_ROOT checkout HEAD~1"
    echo "  sudo cp ${ENV_FILE}.bak.${STAMP} $ENV_FILE"
    echo "  sudo systemctl restart $API_UNIT $FE_UNIT"
    echo "  # DB solo si hace falta: sudo bash $APP_ROOT/scripts/restore-estate.sh $BACKUP_FILE --yes --i-understand-this-wipes-target"
    exit 1
  fi
else
  ylw "    smoke script ausente — skipeado"
fi

echo
grn "=== DEPLOY HARDENING OK ==="
echo "Backup:     $BACKUP_FILE"
echo "Commit:     $(sudo -u "$APP_USER" git -C "$APP_ROOT" rev-parse --short HEAD)"
echo "Env backup: ${ENV_FILE}.bak.${STAMP}"
echo
ylw "Próximos pasos manuales:"
echo "  1) Listar usuarios DB (login real, no demo):"
echo "       cd $APP_ROOT && sudo -u $APP_USER .venv/bin/python -c \"from app.estate.database import get_session_factory; from app.estate.models import User; db=get_session_factory()(); [print(u.email,u.rol,u.activo) for u in db.query(User).all()]\""
echo "  2) Completar SMTP_* en .env si querés invites/OTP mail, luego: systemctl restart $API_UNIT"
echo "  3) Alertas /ready: sudo bash $APP_ROOT/scripts/install-ready-alert-cron.sh"
echo "  4) Drill restore mensual: sudo bash $APP_ROOT/scripts/restore-estate.sh $BACKUP_DIR/ops_hub_estate_latest.dump --url 'postgresql://.../staging' --yes"
echo "  5) Probar https://ibot.ecolan.com/ready y login consola con email de DB"
echo
ylw "Rollback rápido si hace falta:"
echo "  sudo -u $APP_USER git -C $APP_ROOT checkout HEAD~1"
echo "  sudo cp ${ENV_FILE}.bak.${STAMP} $ENV_FILE"
echo "  sudo systemctl restart $API_UNIT $FE_UNIT"
echo "  # Restore DB solo si hubo corrupción (cuidado):"
echo "  # sudo bash $APP_ROOT/scripts/restore-estate.sh $BACKUP_FILE --yes --i-understand-this-wipes-target"
