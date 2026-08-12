#!/usr/bin/env bash
# Cierra / verifica Definition of Done Fase 1 Batán.
# Uso: bash scripts/fase1-cerrar-checklist.sh https://ibot.ecolan.com
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/operations-hub}"
API_URL="${1:-${PUBLIC_URL:-https://ibot.ecolan.com}}"
API_URL="${API_URL%/}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/ops-hub}"
PASS=0
FAIL=0
WARN=0

ok() { printf 'OK   %s\n' "$*"; PASS=$((PASS + 1)); }
bad() { printf 'FAIL %s\n' "$*" >&2; FAIL=$((FAIL + 1)); }
warn() { printf 'WARN %s\n' "$*"; WARN=$((WARN + 1)); }

echo "==> Checklist Fase 1 → $API_URL"
echo

# Health / ready
HEALTH="$(curl -sf --max-time 15 "$API_URL/health" || true)"
if echo "$HEALTH" | grep -q '"status"'; then
  ok "health responde"
  echo "$HEALTH" | python3 -c '
import json,sys
d=json.load(sys.stdin)
print("     env=%s demo_reset=%s sentry=%s db=%s" % (
  d.get("env"), d.get("demo_reset_enabled"), d.get("sentry_configured"), d.get("database_connected")))
' 2>/dev/null || true
  if echo "$HEALTH" | grep -q '"demo_reset_enabled": true\|"demo_reset_enabled":true'; then
    bad "demo_reset_enabled=true en prod"
  else
    ok "demo_reset deshabilitado (o no true)"
  fi
  if echo "$HEALTH" | grep -q '"sentry_configured": true\|"sentry_configured":true'; then
    ok "Sentry configurado"
  elif echo "$HEALTH" | grep -q '"sentry_risk_accepted": true\|"sentry_risk_accepted":true'; then
    ok "Sentry: riesgo aceptado documentado"
  else
    warn "Sentry no configurado — set SENTRY_DSN o SENTRY_RISK_ACCEPTED=true"
  fi
else
  bad "health no responde"
fi

READY="$(curl -sf --max-time 15 "$API_URL/ready" || true)"
if echo "$READY" | grep -q '"ready": true\|"ready":true'; then
  ok "/ready = true"
else
  bad "/ready no OK: ${READY:0:120}"
fi

# Crons
[[ -f /etc/cron.d/operations-hub-backup ]] && ok "cron backup instalado" || bad "falta cron backup (install-backup-cron.sh)"
[[ -f /etc/cron.d/operations-hub-ready-alert ]] && ok "cron /ready instalado" || bad "falta cron ready-alert"

# Backup reciente
if [[ -d "$BACKUP_DIR" ]]; then
  latest="$(ls -1t "$BACKUP_DIR"/ops_hub_estate_*.dump 2>/dev/null | head -1 || true)"
  if [[ -n "$latest" ]]; then
    ok "backup existe: $(basename "$latest")"
  else
    warn "sin dumps en $BACKUP_DIR — corré backup-estate.sh"
  fi
else
  warn "no existe $BACKUP_DIR"
fi

# Alert channels
ALERT_CFG="/etc/default/operations-hub-alert"
if [[ -f "$ALERT_CFG" ]]; then
  # shellcheck disable=SC1090
  set -a && . "$ALERT_CFG" && set +a || true
  if [[ -n "${ALERT_EMAIL_TO:-}" || -n "${ALERT_TELEGRAM_CHAT_ID:-}" || -n "${ALERT_WEBHOOK_URL:-}" ]]; then
    ok "canal de alerta definido en $ALERT_CFG"
  else
    warn "cron alerta OK pero sin canal (ALERT_EMAIL_TO / TELEGRAM / WEBHOOK) en $ALERT_CFG"
  fi
else
  warn "falta $ALERT_CFG"
fi

# Smoke credentials
SMOKE_FILE=""
for f in /etc/operations-hub/smoke.env "$APP_ROOT/.smoke.env"; do
  [[ -f "$f" ]] && SMOKE_FILE="$f" && break
done
if [[ -n "$SMOKE_FILE" ]]; then
  ok "credenciales smoke: $SMOKE_FILE"
elif [[ -n "${VERIFY_USER:-}" && -n "${VERIFY_PASSWORD:-}" ]]; then
  ok "VERIFY_USER/PASSWORD en entorno"
else
  warn "sin smoke autenticado — creá /etc/operations-hub/smoke.env (VERIFY_USER/PASSWORD)"
fi

# Restore script presente
[[ -f "$APP_ROOT/scripts/restore-estate.sh" ]] && ok "restore-estate.sh presente" || bad "falta restore-estate.sh"
warn "drill restore mensual: documentar fecha del último restore en staging (manual)"

# WhatsApp stance
if [[ -f "$APP_ROOT/.env" ]]; then
  if grep -qE '^WHATSAPP_TOKEN=.+' "$APP_ROOT/.env" 2>/dev/null; then
    ok "WHATSAPP_TOKEN presente en .env"
  else
    warn "WhatsApp sin token — OK si quedó para próximo sprint (HMAC ya testeado en smoke)"
  fi
fi

echo
echo "==> Resultado: $PASS OK · $WARN WARN · $FAIL FAIL"
if [[ "$FAIL" -gt 0 ]]; then
  echo "Hay bloqueos — corregí los FAIL y reejecutá."
  exit 1
fi
if [[ "$WARN" -gt 0 ]]; then
  echo "Piloto operable con advertencias. Resolvé WARNs cuando puedas."
  exit 0
fi
echo "Fase 1 checklist completa."
exit 0
