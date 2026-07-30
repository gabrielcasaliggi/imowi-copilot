#!/usr/bin/env bash
# Instala Operations Hub con Docker Compose (alternativa).
# En servidor dedicado preferí: bash scripts/install-server.sh (nativo).
#
# Uso:
#   sudo bash scripts/install-server-docker.sh --public-url http://TU_IP

set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]}"
if command -v readlink >/dev/null 2>&1; then
  SCRIPT_PATH="$(readlink -f "$SCRIPT_PATH" 2>/dev/null || realpath "$SCRIPT_PATH" 2>/dev/null || echo "$SCRIPT_PATH")"
fi
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"

resolve_root() {
  local candidate
  for candidate in "$SCRIPT_DIR/.." "$PWD" "$PWD/.." "$(dirname "$SCRIPT_DIR")"; do
    candidate="$(cd "$candidate" 2>/dev/null && pwd || true)"
    [[ -n "$candidate" ]] || continue
    if [[ -f "$candidate/deploy/docker-compose.yml" && -f "$candidate/main.py" ]]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

ROOT="$(resolve_root || true)"
[[ -n "${ROOT}" ]] || {
  echo "ERROR: no encontré el repo (main.py + deploy/docker-compose.yml)." >&2
  exit 1
}
cd "$ROOT"

COMPOSE_FILE="$ROOT/deploy/docker-compose.yml"
ENV_FILE="$ROOT/.env"
ENV_EXAMPLE="$ROOT/.env.server.example"
PUBLIC_URL=""
SKIP_DOCKER_INSTALL=0
DO_MIGRATE=0
HTTP_PORT="80"

usage() { sed -n '2,8p' "$0" | sed 's/^# \?//'; exit 0; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --public-url) PUBLIC_URL="${2:?}"; shift 2 ;;
    --http-port) HTTP_PORT="${2:?}"; shift 2 ;;
    --skip-docker-install) SKIP_DOCKER_INSTALL=1; shift ;;
    --migrate) DO_MIGRATE=1; shift ;;
    -h|--help) usage ;;
    *) echo "Opción desconocida: $1" >&2; usage ;;
  esac
done

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
need_root() { [[ "${EUID}" -eq 0 ]] || die "Ejecutá con sudo"; }

detect_public_ip() {
  curl -4 -fsS --max-time 5 https://ifconfig.me 2>/dev/null \
    || curl -4 -fsS --max-time 5 https://api.ipify.org 2>/dev/null \
    || true
}

install_docker() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    log "Docker ya instalado: $(docker --version)"; return 0
  fi
  log "Instalando Docker Engine + Compose"
  apt-get update -y
  apt-get install -y ca-certificates curl gnupg
  install -m 0755 -d /etc/apt/keyrings
  [[ -f /etc/apt/keyrings/docker.asc ]] || {
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
  }
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
}

configure_firewall() {
  command -v ufw >/dev/null 2>&1 || apt-get install -y ufw
  ufw allow OpenSSH >/dev/null 2>&1 || ufw allow 22/tcp >/dev/null 2>&1 || true
  ufw allow "${HTTP_PORT}/tcp" >/dev/null 2>&1 || true
  if ufw status | grep -qi "Status: inactive"; then echo "y" | ufw enable || true; fi
}

ensure_env() {
  [[ -f "$ENV_FILE" ]] || { [[ -f "$ENV_EXAMPLE" ]] || die "Falta $ENV_EXAMPLE"; cp "$ENV_EXAMPLE" "$ENV_FILE"; }
  if [[ -z "$PUBLIC_URL" ]]; then
    PUBLIC_URL="$(grep -E '^PUBLIC_URL=' "$ENV_FILE" | head -1 | cut -d= -f2- || true)"
  fi
  if [[ -z "$PUBLIC_URL" || "$PUBLIC_URL" == *"TU_IP_PUBLICA"* ]]; then
    local ip; ip="$(detect_public_ip)"
    [[ -n "$ip" ]] || die "Pasá --public-url http://TU_IP"
    PUBLIC_URL="http://${ip}"
  fi
  PUBLIC_URL="${PUBLIC_URL%/}"
  if ! grep -qE '^AUTH_SECRET=.+' "$ENV_FILE" || grep -qE '^AUTH_SECRET=$' "$ENV_FILE"; then
    local secret; secret="$(openssl rand -hex 32)"
    grep -qE '^AUTH_SECRET=' "$ENV_FILE" && sed -i "s|^AUTH_SECRET=.*|AUTH_SECRET=${secret}|" "$ENV_FILE" || echo "AUTH_SECRET=${secret}" >> "$ENV_FILE"
  fi
  if grep -qE 'POSTGRES_PASSWORD=CAMBIAR_PASSWORD_FUERTE' "$ENV_FILE"; then
    local pw; pw="$(openssl rand -base64 24 | tr -d '/+=' | head -c 28)"
    sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${pw}|" "$ENV_FILE"
  fi
  if grep -qE 'ADMIN_PASSWORD=CAMBIAR_ADMIN' "$ENV_FILE"; then
    sed -i "s|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=admin-cambiar|" "$ENV_FILE"
  fi
  sed -i "s|^PUBLIC_URL=.*|PUBLIC_URL=${PUBLIC_URL}|" "$ENV_FILE" || echo "PUBLIC_URL=${PUBLIC_URL}" >> "$ENV_FILE"
  sed -i "s|^CORS_ORIGINS=.*|CORS_ORIGINS=${PUBLIC_URL}|" "$ENV_FILE" || echo "CORS_ORIGINS=${PUBLIC_URL}" >> "$ENV_FILE"
  grep -qE '^HTTP_PORT=' "$ENV_FILE" && sed -i "s|^HTTP_PORT=.*|HTTP_PORT=${HTTP_PORT}|" "$ENV_FILE" || echo "HTTP_PORT=${HTTP_PORT}" >> "$ENV_FILE"
  grep -qE '^APP_ENV=' "$ENV_FILE" && sed -i "s|^APP_ENV=.*|APP_ENV=production|" "$ENV_FILE" || echo "APP_ENV=production" >> "$ENV_FILE"
}

bring_up() {
  log "docker compose up --build"
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --build
  local ok=0
  for _ in $(seq 1 60); do
    curl -fsS "http://127.0.0.1:${HTTP_PORT}/health" >/dev/null 2>&1 && { ok=1; break; }
    sleep 3
  done
  [[ "$ok" -eq 1 ]] || die "API sin /health — revisá logs de compose"
  curl -fsS "http://127.0.0.1:${HTTP_PORT}/health" | python3 -m json.tool || true
}

main() {
  need_root
  [[ -f "$COMPOSE_FILE" ]] || die "No encuentro $COMPOSE_FILE"
  [[ "$SKIP_DOCKER_INSTALL" -eq 0 ]] && install_docker || true
  apt-get install -y openssl curl python3 >/dev/null
  configure_firewall
  ensure_env
  bring_up
  [[ "$DO_MIGRATE" -eq 1 ]] && bash "$ROOT/scripts/migrate-data.sh" --yes
  echo "Listo (Docker): $PUBLIC_URL"
}

main
