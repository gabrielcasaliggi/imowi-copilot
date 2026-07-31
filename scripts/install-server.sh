#!/usr/bin/env bash
# Instala Operations Hub de forma NATIVA en Ubuntu 24.04 (servidor dedicado).
#
# Sin Docker. Instala y configura:
#   - PostgreSQL (Data Estate)
#   - Python venv + FastAPI (systemd)
#   - Node.js + Next.js (systemd)
#   - Nginx (reverse proxy :80)
#   - Opcional: HTTPS con Let's Encrypt (ibot.ecolan.com)
#
# El LLM vive en otro servidor — configurá AI_* en .env o en Admin Hub.
#
# Uso (repo completo en el servidor, con sudo):
#   cd /opt/operations-hub
#   sudo bash scripts/install-server.sh --domain ibot.ecolan.com --email admin@ecolan.com
#
# Si el DNS aún no apunta, instalá sin HTTPS y después:
#   sudo bash scripts/enable-https.sh --email admin@ecolan.com
#
# Opciones:
#   --domain NAME        Dominio (default: ibot.ecolan.com)
#   --email EMAIL        Email Let's Encrypt (activa HTTPS al final)
#   --public-url URL     Sobrescribe URL pública (default https://DOMINIO)
#   --app-user USER      Usuario de servicios (default: SUDO_USER o opshub)
#   --migrate            Migrar datos al final
#   --skip-https         No emitir certificado (solo HTTP)
#   --skip-node          No instalar Node
#   --skip-firewall      No tocar UFW
#
# Variante Docker: bash scripts/install-server-docker.sh

set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]}"
if command -v readlink >/dev/null 2>&1; then
  SCRIPT_PATH="$(readlink -f "$SCRIPT_PATH" 2>/dev/null || realpath "$SCRIPT_PATH" 2>/dev/null || echo "$SCRIPT_PATH")"
fi
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"

resolve_root() {
  local candidate
  for candidate in \
    "$SCRIPT_DIR/.." \
    "$PWD" \
    "$PWD/.." \
    "$(dirname "$SCRIPT_DIR")"
  do
    candidate="$(cd "$candidate" 2>/dev/null && pwd || true)"
    [[ -n "$candidate" ]] || continue
    if [[ -f "$candidate/main.py" && -f "$candidate/requirements.txt" ]]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

ROOT="$(resolve_root || true)"
if [[ -z "${ROOT}" ]]; then
  cat >&2 <<EOF
ERROR: no encontré el repositorio de Operations Hub.

Necesitás la raíz del repo (archivos main.py y requirements.txt).

  git clone <url> /opt/operations-hub
  cd /opt/operations-hub
  sudo bash scripts/install-server.sh --domain ibot.ecolan.com --email admin@ecolan.com

Rutas buscadas desde: $SCRIPT_DIR (cwd: $PWD)
EOF
  exit 1
fi

cd "$ROOT"

ENV_FILE="$ROOT/.env"
ENV_EXAMPLE="$ROOT/.env.server.example"
NGINX_SRC="$ROOT/deploy/nginx/operations-hub.conf"
UNIT_API_SRC="$ROOT/deploy/systemd/operations-hub-api.service"
UNIT_FE_SRC="$ROOT/deploy/systemd/operations-hub-frontend.service"

PUBLIC_URL=""
DOMAIN="ibot.ecolan.com"
LETSENCRYPT_EMAIL=""
APP_USER=""
DO_MIGRATE=0
SKIP_NODE=0
SKIP_FIREWALL=0
SKIP_HTTPS=0
HTTP_PORT="80"

usage() {
  sed -n '2,32p' "$0" | sed 's/^# \?//'
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --public-url) PUBLIC_URL="${2:?}"; shift 2 ;;
    --domain) DOMAIN="${2:?}"; shift 2 ;;
    --email) LETSENCRYPT_EMAIL="${2:?}"; shift 2 ;;
    --app-user) APP_USER="${2:?}"; shift 2 ;;
    --http-port) HTTP_PORT="${2:?}"; shift 2 ;;
    --migrate) DO_MIGRATE=1; shift ;;
    --skip-node) SKIP_NODE=1; shift ;;
    --skip-firewall) SKIP_FIREWALL=1; shift ;;
    --skip-https) SKIP_HTTPS=1; shift ;;
    -h|--help) usage ;;
    *) echo "Opción desconocida: $1" >&2; usage ;;
  esac
done

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

need_root() {
  [[ "${EUID}" -eq 0 ]] || die "Ejecutá con sudo: sudo bash scripts/install-server.sh --domain ibot.ecolan.com --email admin@ecolan.com"
}

detect_public_ip() {
  local ip=""
  ip="$(curl -4 -fsS --max-time 5 https://ifconfig.me 2>/dev/null || true)"
  [[ -z "$ip" ]] && ip="$(curl -4 -fsS --max-time 5 https://api.ipify.org 2>/dev/null || true)"
  echo "$ip"
}

ensure_app_user() {
  if [[ -z "$APP_USER" ]]; then
    if [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
      APP_USER="$SUDO_USER"
    else
      APP_USER="opshub"
    fi
  fi

  if ! id "$APP_USER" >/dev/null 2>&1; then
    log "Creando usuario del sistema: $APP_USER"
    useradd --system --create-home --shell /bin/bash "$APP_USER"
  fi

  log "Usuario de servicios: $APP_USER"
  chown -R "$APP_USER:$APP_USER" "$ROOT"
}

install_system_packages() {
  log "Instalando paquetes del sistema"
  apt-get update -y
  DEBIAN_FRONTEND=noninteractive apt-get install -y \
    ca-certificates curl gnupg openssl python3 python3-venv python3-pip \
    postgresql postgresql-contrib nginx ufw build-essential libpq-dev
}

install_nodejs() {
  if [[ "$SKIP_NODE" -eq 1 ]]; then
    command -v node >/dev/null 2>&1 || die "Node no instalado y usaste --skip-node"
    log "Node existente: $(node -v)"
    return 0
  fi

  if command -v node >/dev/null 2>&1; then
    local major
    major="$(node -v | sed 's/^v//' | cut -d. -f1)"
    if [[ "$major" -ge 20 ]]; then
      log "Node OK: $(node -v)"
      return 0
    fi
    log "Node $(node -v) es viejo; instalando Node 20"
  fi

  log "Instalando Node.js 20 (NodeSource)"
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  DEBIAN_FRONTEND=noninteractive apt-get install -y nodejs
  node -v
  npm -v
}

configure_firewall() {
  [[ "$SKIP_FIREWALL" -eq 1 ]] && return 0
  log "Configurando UFW (SSH + HTTP ${HTTP_PORT} + HTTPS 443)"
  ufw allow OpenSSH >/dev/null 2>&1 || ufw allow 22/tcp >/dev/null 2>&1 || true
  ufw allow "${HTTP_PORT}/tcp" >/dev/null 2>&1 || true
  ufw allow 443/tcp >/dev/null 2>&1 || true
  if ufw status 2>/dev/null | grep -qi "Status: inactive"; then
    echo "y" | ufw enable || true
  fi
  ufw status || true
}

ensure_env() {
  if [[ ! -f "$ENV_FILE" ]]; then
    [[ -f "$ENV_EXAMPLE" ]] || die "Falta $ENV_EXAMPLE"
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    log "Creado .env desde .env.server.example"
  else
    log "Usando .env existente"
  fi

  DOMAIN="${DOMAIN:-ibot.ecolan.com}"

  if [[ -z "$PUBLIC_URL" ]]; then
    PUBLIC_URL="$(grep -E '^PUBLIC_URL=' "$ENV_FILE" | head -1 | cut -d= -f2- || true)"
    PUBLIC_URL="${PUBLIC_URL//$'\r'/}"
  fi

  # Preferir HTTPS + dominio salvo que el usuario pase --public-url explícito
  if [[ -z "$PUBLIC_URL" || "$PUBLIC_URL" == *"TU_IP_PUBLICA"* || "$PUBLIC_URL" == *"ibot.ecolan.com"* ]]; then
    if [[ "$SKIP_HTTPS" -eq 1 ]]; then
      PUBLIC_URL="http://${DOMAIN}"
    else
      PUBLIC_URL="https://${DOMAIN}"
    fi
  fi
  PUBLIC_URL="${PUBLIC_URL%/}"

  if [[ -z "$LETSENCRYPT_EMAIL" ]]; then
    LETSENCRYPT_EMAIL="$(grep -E '^LETSENCRYPT_EMAIL=' "$ENV_FILE" | head -1 | cut -d= -f2- || true)"
  fi

  if ! grep -qE '^AUTH_SECRET=.+' "$ENV_FILE" || grep -qE '^AUTH_SECRET=$' "$ENV_FILE"; then
    local secret
    secret="$(openssl rand -hex 32)"
    if grep -qE '^AUTH_SECRET=' "$ENV_FILE"; then
      sed -i "s|^AUTH_SECRET=.*|AUTH_SECRET=${secret}|" "$ENV_FILE"
    else
      echo "AUTH_SECRET=${secret}" >> "$ENV_FILE"
    fi
    log "AUTH_SECRET generado"
  fi

  if grep -qE 'POSTGRES_PASSWORD=CAMBIAR_PASSWORD_FUERTE' "$ENV_FILE" || ! grep -qE '^POSTGRES_PASSWORD=.+' "$ENV_FILE"; then
    local pw
    pw="$(openssl rand -base64 24 | tr -d '/+=' | head -c 28)"
    if grep -qE '^POSTGRES_PASSWORD=' "$ENV_FILE"; then
      sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${pw}|" "$ENV_FILE"
    else
      echo "POSTGRES_PASSWORD=${pw}" >> "$ENV_FILE"
    fi
    log "POSTGRES_PASSWORD generado"
  fi

  if grep -qE 'ADMIN_PASSWORD=CAMBIAR_ADMIN' "$ENV_FILE"; then
    sed -i "s|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=admin-cambiar|" "$ENV_FILE"
    log "ADMIN_PASSWORD temporal: admin-cambiar"
  fi

  local pg_user pg_pass pg_db
  pg_user="$(grep -E '^POSTGRES_USER=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
  pg_pass="$(grep -E '^POSTGRES_PASSWORD=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
  pg_db="$(grep -E '^POSTGRES_DB=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
  pg_user="${pg_user:-ops_hub}"
  pg_db="${pg_db:-ops_hub}"

  local db_url="postgresql://${pg_user}:${pg_pass}@127.0.0.1:5432/${pg_db}"

  set_env_key() {
    local key="$1" val="$2"
    if grep -qE "^${key}=" "$ENV_FILE"; then
      sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
    else
      echo "${key}=${val}" >> "$ENV_FILE"
    fi
  }

  set_env_key "DOMAIN" "$DOMAIN"
  set_env_key "PUBLIC_URL" "$PUBLIC_URL"
  set_env_key "CORS_ORIGINS" "$PUBLIC_URL"
  set_env_key "HTTP_PORT" "$HTTP_PORT"
  set_env_key "APP_ENV" "production"
  set_env_key "DATABASE_URL" "$db_url"
  set_env_key "DATABASE_SSLMODE" "disable"
  set_env_key "HOST" "127.0.0.1"
  set_env_key "PORT" "8000"
  set_env_key "DATA_DIR" "${ROOT}/data"
  if [[ -n "$LETSENCRYPT_EMAIL" ]]; then
    set_env_key "LETSENCRYPT_EMAIL" "$LETSENCRYPT_EMAIL"
  fi

  chown "$APP_USER:$APP_USER" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  log "PUBLIC_URL=${PUBLIC_URL}  DOMAIN=${DOMAIN}"
}

setup_postgres() {
  log "Configurando PostgreSQL"
  systemctl enable --now postgresql

  local pg_user pg_pass pg_db
  pg_user="$(grep -E '^POSTGRES_USER=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
  pg_pass="$(grep -E '^POSTGRES_PASSWORD=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
  pg_db="$(grep -E '^POSTGRES_DB=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
  pg_user="${pg_user:-ops_hub}"
  pg_db="${pg_db:-ops_hub}"

  # Crear rol + DB (idempotente). Password vía psql -v para escapar bien.
  local pg_pass_sql
  pg_pass_sql="${pg_pass//\'/\'\'}"

  if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${pg_user}'" | grep -q 1; then
    sudo -u postgres psql -v ON_ERROR_STOP=1 -c \
      "CREATE ROLE ${pg_user} LOGIN PASSWORD '${pg_pass_sql}';"
  else
    sudo -u postgres psql -v ON_ERROR_STOP=1 -c \
      "ALTER ROLE ${pg_user} WITH LOGIN PASSWORD '${pg_pass_sql}';"
  fi

  if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${pg_db}'" | grep -q 1; then
    sudo -u postgres psql -v ON_ERROR_STOP=1 -c \
      "CREATE DATABASE ${pg_db} OWNER ${pg_user};"
  fi

  sudo -u postgres psql -v ON_ERROR_STOP=1 -c \
    "GRANT ALL PRIVILEGES ON DATABASE ${pg_db} TO ${pg_user};"

  # Permisos en schema public (PG 15+)
  sudo -u postgres psql -d "$pg_db" -v ON_ERROR_STOP=1 -c \
    "GRANT ALL ON SCHEMA public TO ${pg_user}; ALTER SCHEMA public OWNER TO ${pg_user};"

  log "Postgres listo: db=${pg_db} user=${pg_user}"
}

setup_python_api() {
  log "Entorno Python + dependencias API"
  mkdir -p "$ROOT/data"
  chown -R "$APP_USER:$APP_USER" "$ROOT"

  sudo -u "$APP_USER" bash -c "
    set -euo pipefail
    cd '$ROOT'
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
  "
}

setup_frontend() {
  log "Instalando y buildeando frontend Next.js"
  sudo -u "$APP_USER" bash -c "
    set -euo pipefail
    cd '$ROOT/frontend'
    echo 'NEXT_PUBLIC_API_URL=$PUBLIC_URL' > .env.production
    echo 'NEXT_PUBLIC_API_URL=$PUBLIC_URL' > .env.local
    npm ci
    npm run build
  "
}

install_systemd_units() {
  log "Instalando unidades systemd"
  [[ -f "$UNIT_API_SRC" ]] || die "Falta $UNIT_API_SRC"
  [[ -f "$UNIT_FE_SRC" ]] || die "Falta $UNIT_FE_SRC"

  local api_unit fe_unit
  api_unit="$(sed -e "s|__APP_USER__|${APP_USER}|g" -e "s|__APP_ROOT__|${ROOT}|g" "$UNIT_API_SRC")"
  fe_unit="$(sed -e "s|__APP_USER__|${APP_USER}|g" -e "s|__APP_ROOT__|${ROOT}|g" "$UNIT_FE_SRC")"

  printf '%s\n' "$api_unit" > /etc/systemd/system/operations-hub-api.service
  printf '%s\n' "$fe_unit" > /etc/systemd/system/operations-hub-frontend.service

  systemctl daemon-reload
  systemctl enable operations-hub-api operations-hub-frontend
  systemctl restart operations-hub-api
  sleep 3
  systemctl restart operations-hub-frontend
}

setup_nginx() {
  log "Configurando Nginx (server_name ${DOMAIN})"
  [[ -f "$NGINX_SRC" ]] || die "Falta $NGINX_SRC"

  mkdir -p /var/www/html
  sed "s/server_name .*/server_name ${DOMAIN};/" "$NGINX_SRC" \
    > /etc/nginx/sites-available/operations-hub
  ln -sfn /etc/nginx/sites-available/operations-hub /etc/nginx/sites-enabled/operations-hub

  if [[ -f /etc/nginx/sites-enabled/default ]]; then
    rm -f /etc/nginx/sites-enabled/default
  fi

  if [[ "$HTTP_PORT" != "80" ]]; then
    sed -i "s/listen 80/listen ${HTTP_PORT}/g; s/listen \[::\]:80/listen [::]:${HTTP_PORT}/g" \
      /etc/nginx/sites-available/operations-hub
  fi

  nginx -t
  systemctl enable --now nginx
  systemctl reload nginx
}

maybe_enable_https() {
  if [[ "$SKIP_HTTPS" -eq 1 ]]; then
    log "HTTPS omitido (--skip-https). Cuando el DNS esté listo:"
    echo "  sudo bash scripts/enable-https.sh --domain ${DOMAIN} --email TU_EMAIL"
    return 0
  fi
  if [[ -z "$LETSENCRYPT_EMAIL" ]]; then
    log "Sin --email: se deja HTTP. Para HTTPS después:"
    echo "  sudo bash scripts/enable-https.sh --domain ${DOMAIN} --email admin@ecolan.com"
    return 0
  fi

  log "Activando HTTPS para ${DOMAIN}"
  if ! bash "$ROOT/scripts/enable-https.sh" \
      --domain "$DOMAIN" \
      --email "$LETSENCRYPT_EMAIL" \
      --rebuild-frontend; then
    log "HTTPS no se pudo emitir ahora (¿DNS aún no apunta?). El stack HTTP quedó OK."
    echo "  Reintentá: sudo bash scripts/enable-https.sh --domain ${DOMAIN} --email ${LETSENCRYPT_EMAIL}"
  else
    PUBLIC_URL="https://${DOMAIN}"
  fi
}

wait_health() {
  log "Esperando /health"
  local ok=0 i
  for i in $(seq 1 40); do
    if curl -fsS "http://127.0.0.1:${HTTP_PORT}/health" >/dev/null 2>&1; then
      ok=1
      break
    fi
    sleep 2
  done
  if [[ "$ok" -ne 1 ]]; then
    echo "--- status API ---"
    systemctl status operations-hub-api --no-pager || true
    echo "--- journal API ---"
    journalctl -u operations-hub-api -n 40 --no-pager || true
    die "La API no respondió en /health"
  fi
  curl -fsS "http://127.0.0.1:${HTTP_PORT}/health" | python3 -m json.tool || true
}

print_summary() {
  cat <<EOF

════════════════════════════════════════════════════════════
  Operations Hub instalado (nativo)
════════════════════════════════════════════════════════════

  Dominio:         ${DOMAIN}
  URL pública:     ${PUBLIC_URL}
  Health:          ${PUBLIC_URL}/health
  API docs:        ${PUBLIC_URL}/docs
  Frontend:        ${PUBLIC_URL}/

  Usuario app:     ${APP_USER}
  Repo:            ${ROOT}
  Admin seed:      ver ADMIN_USER / ADMIN_PASSWORD en .env

  LLM: editá AI_* en .env o Admin Hub, luego:
       sudo systemctl restart operations-hub-api

  DNS (si aún no):
       A  ibot.ecolan.com  →  IP de este servidor

  HTTPS (si faltó):
       sudo bash scripts/enable-https.sh --domain ${DOMAIN} --email admin@ecolan.com

  Servicios:
    sudo systemctl status operations-hub-api operations-hub-frontend nginx postgresql

  Migrar datos:
    export SUPABASE_DATABASE_URL='postgresql://...@db.xxx.supabase.co:5432/postgres'
    sudo bash scripts/migrate-data.sh --yes

════════════════════════════════════════════════════════════
EOF
}

main() {
  need_root
  [[ -f "$ROOT/main.py" ]] || die "Repo incompleto en $ROOT"

  log "Operations Hub — instalación NATIVA Ubuntu"
  echo "Repo: $ROOT"
  echo "Dominio: $DOMAIN"

  install_system_packages
  install_nodejs
  ensure_app_user
  configure_firewall
  ensure_env
  setup_postgres
  setup_python_api
  setup_frontend
  install_systemd_units
  setup_nginx
  wait_health
  maybe_enable_https

  if [[ "$DO_MIGRATE" -eq 1 ]]; then
    log "Migrando datos"
    bash "$ROOT/scripts/migrate-data.sh" --yes
  fi

  print_summary
}

main
