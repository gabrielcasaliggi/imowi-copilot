#!/usr/bin/env bash
# Emite / renueva certificado Let's Encrypt para el dominio del Operations Hub.
#
# Requisitos:
#   - DNS A de ibot.ecolan.com y soporte.ecolan.com → IP de este servidor
#   - Nginx ya instalado (scripts/install-server.sh)
#   - Puertos 80 y 443 abiertos
#
# Uso:
#   sudo bash scripts/enable-https.sh
#   sudo bash scripts/enable-https.sh --domain ibot.ecolan.com --email admin@ecolan.com
#   sudo bash scripts/enable-https.sh --portal-domain soporte.ecolan.com --rebuild-frontend

set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]}"
if command -v readlink >/dev/null 2>&1; then
  SCRIPT_PATH="$(readlink -f "$SCRIPT_PATH" 2>/dev/null || realpath "$SCRIPT_PATH" 2>/dev/null || echo "$SCRIPT_PATH")"
fi
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

ENV_FILE="$ROOT/.env"
DOMAIN="ibot.ecolan.com"
PORTAL_DOMAIN="soporte.ecolan.com"
EMAIL=""
REBUILD_FRONTEND=0
SKIP_DNS_CHECK=0

usage() { sed -n '2,14p' "$0" | sed 's/^# \?//'; exit 0; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) DOMAIN="${2:?}"; shift 2 ;;
    --portal-domain) PORTAL_DOMAIN="${2:?}"; shift 2 ;;
    --email) EMAIL="${2:?}"; shift 2 ;;
    --rebuild-frontend) REBUILD_FRONTEND=1; shift ;;
    --skip-dns-check) SKIP_DNS_CHECK=1; shift ;;
    -h|--help) usage ;;
    *) echo "Opción desconocida: $1" >&2; usage ;;
  esac
done

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[[ "${EUID}" -eq 0 ]] || die "Ejecutá con sudo"

[[ -f "$ENV_FILE" ]] || die "Falta $ENV_FILE — corré antes install-server.sh"

if [[ -z "$EMAIL" ]]; then
  EMAIL="$(grep -E '^LETSENCRYPT_EMAIL=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- || true)"
fi
[[ -n "$EMAIL" && "$EMAIL" != *"@"* ]] && EMAIL=""
[[ -n "$EMAIL" ]] || die "Pasá --email admin@tudominio.com (Let's Encrypt lo requiere)"

APP_USER="$(stat -c '%U' "$ROOT" 2>/dev/null || echo root)"
PUBLIC_URL="https://${DOMAIN}"

detect_public_ip() {
  curl -4 -fsS --max-time 5 https://ifconfig.me 2>/dev/null \
    || curl -4 -fsS --max-time 5 https://api.ipify.org 2>/dev/null \
    || true
}

check_dns() {
  [[ "$SKIP_DNS_CHECK" -eq 1 ]] && return 0
  log "Verificando DNS de ${DOMAIN}"
  local pub resolved
  pub="$(detect_public_ip)"
  resolved="$(getent ahostsv4 "$DOMAIN" 2>/dev/null | awk '{print $1; exit}' || true)"
  if [[ -z "$resolved" ]]; then
    resolved="$(dig +short A "$DOMAIN" 2>/dev/null | head -1 || true)"
  fi
  echo "  IP servidor: ${pub:-desconocida}"
  echo "  DNS ${DOMAIN}: ${resolved:-sin registro A}"
  if [[ -z "$resolved" ]]; then
    die "No hay registro A para ${DOMAIN}. Crealo apuntando a la IP del servidor y reintentá."
  fi
  if [[ -n "$pub" && "$pub" != "$resolved" ]]; then
    die "DNS (${resolved}) no coincide con la IP de este server (${pub}). Corregí el A record."
  fi
  log "DNS OK"
}

install_certbot() {
  if ! command -v certbot >/dev/null 2>&1; then
    log "Instalando certbot"
    apt-get update -y
    DEBIAN_FRONTEND=noninteractive apt-get install -y certbot python3-certbot-nginx
  fi
}

open_https_firewall() {
  if command -v ufw >/dev/null 2>&1; then
    ufw allow 443/tcp >/dev/null 2>&1 || true
    ufw allow OpenSSH >/dev/null 2>&1 || true
  fi
}

ensure_nginx_server_name() {
  local site="/etc/nginx/sites-available/operations-hub"
  if [[ -f "$site" ]]; then
    sed -i "s/server_name .*/server_name ${DOMAIN} ${PORTAL_DOMAIN};/" "$site"
    nginx -t
    systemctl reload nginx
  else
    die "No está el site Nginx operations-hub. Corré install-server.sh primero."
  fi
}

portal_dns_ok() {
  local pub resolved
  pub="$(detect_public_ip)"
  resolved="$(getent ahostsv4 "$PORTAL_DOMAIN" 2>/dev/null | awk '{print $1; exit}' || true)"
  if [[ -z "$resolved" ]]; then
    resolved="$(dig +short A "$PORTAL_DOMAIN" 2>/dev/null | head -1 || true)"
  fi
  [[ -n "$resolved" && ( -z "$pub" || "$pub" == "$resolved" ) ]]
}

issue_cert() {
  mkdir -p /var/www/html
  if portal_dns_ok; then
    log "Solicitando certificado Let's Encrypt para ${DOMAIN} y ${PORTAL_DOMAIN}"
    certbot --nginx \
      -d "$DOMAIN" \
      -d "$PORTAL_DOMAIN" \
      --non-interactive \
      --agree-tos \
      --email "$EMAIL" \
      --redirect \
      --keep-until-expiring
  else
    log "Sin DNS válido para ${PORTAL_DOMAIN}: certificado solo ${DOMAIN}"
    echo "  Cuando el A de ${PORTAL_DOMAIN} apunte acá:"
    echo "  sudo bash scripts/enable-https.sh --domain ${DOMAIN} --portal-domain ${PORTAL_DOMAIN} --email ${EMAIL}"
    certbot --nginx \
      -d "$DOMAIN" \
      --non-interactive \
      --agree-tos \
      --email "$EMAIL" \
      --redirect \
      --keep-until-expiring
  fi
}

update_env_https() {
  log "Actualizando .env → ${PUBLIC_URL}"
  if grep -qE '^PUBLIC_URL=' "$ENV_FILE"; then
    sed -i "s|^PUBLIC_URL=.*|PUBLIC_URL=${PUBLIC_URL}|" "$ENV_FILE"
  else
    echo "PUBLIC_URL=${PUBLIC_URL}" >> "$ENV_FILE"
  fi
  local cors="${PUBLIC_URL},https://${PORTAL_DOMAIN}"
  if grep -qE '^CORS_ORIGINS=' "$ENV_FILE"; then
    sed -i "s|^CORS_ORIGINS=.*|CORS_ORIGINS=${cors}|" "$ENV_FILE"
  else
    echo "CORS_ORIGINS=${cors}" >> "$ENV_FILE"
  fi
  if grep -qE '^PORTAL_DOMAIN=' "$ENV_FILE"; then
    sed -i "s|^PORTAL_DOMAIN=.*|PORTAL_DOMAIN=${PORTAL_DOMAIN}|" "$ENV_FILE"
  else
    echo "PORTAL_DOMAIN=${PORTAL_DOMAIN}" >> "$ENV_FILE"
  fi
  if grep -qE '^LETSENCRYPT_EMAIL=' "$ENV_FILE"; then
    sed -i "s|^LETSENCRYPT_EMAIL=.*|LETSENCRYPT_EMAIL=${EMAIL}|" "$ENV_FILE"
  else
    echo "LETSENCRYPT_EMAIL=${EMAIL}" >> "$ENV_FILE"
  fi
  if grep -qE '^DOMAIN=' "$ENV_FILE"; then
    sed -i "s|^DOMAIN=.*|DOMAIN=${DOMAIN}|" "$ENV_FILE"
  else
    echo "DOMAIN=${DOMAIN}" >> "$ENV_FILE"
  fi
}

rebuild_frontend() {
  [[ "$REBUILD_FRONTEND" -eq 1 ]] || return 0
  log "Rebuild frontend same-origin (hosts ${DOMAIN} / ${PORTAL_DOMAIN})"
  sudo -u "$APP_USER" bash -c "
    set -euo pipefail
    cd '$ROOT/frontend'
    cat > .env.production <<EOF
NEXT_PUBLIC_API_URL=
NEXT_PUBLIC_CONSOLE_HOST=${DOMAIN}
NEXT_PUBLIC_PORTAL_HOST=${PORTAL_DOMAIN}
NEXT_PUBLIC_APP_ENV=production
EOF
    cp .env.production .env.local
    npm ci
    npm run build
  "
  systemctl restart operations-hub-frontend
  systemctl restart operations-hub-api
}

verify() {
  log "Verificando HTTPS"
  sleep 2
  curl -fsS "https://${DOMAIN}/health" | python3 -m json.tool || {
    echo "Aviso: https://${DOMAIN}/health no respondió aún; revisá DNS/firewall."
    return 0
  }
}

main() {
  check_dns
  install_certbot
  open_https_firewall
  ensure_nginx_server_name
  issue_cert
  update_env_https
  # Tras HTTPS siempre conviene rebuild para que el browser use https://
  REBUILD_FRONTEND=1
  rebuild_frontend
  verify
  cat <<EOF

HTTPS listo: ${PUBLIC_URL}
Renovación automática: certbot.timer (systemd)

Probar:
  curl -I https://${DOMAIN}
  curl https://${DOMAIN}/health
EOF
}

main
