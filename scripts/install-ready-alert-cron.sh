#!/usr/bin/env bash
# Instala cron de alerta /ready cada 2 minutos.
# Uso: sudo bash scripts/install-ready-alert-cron.sh
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/operations-hub}"
CRON_FILE="/etc/cron.d/operations-hub-ready-alert"
DEFAULTS="/etc/default/operations-hub-alert"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Ejecutá con sudo" >&2
  exit 1
fi

if [[ ! -f "$APP_ROOT/scripts/alert-ready.sh" ]]; then
  echo "No encuentro $APP_ROOT/scripts/alert-ready.sh" >&2
  exit 1
fi
chmod +x "$APP_ROOT/scripts/alert-ready.sh" \
  "$APP_ROOT/scripts/send-ops-alert.py" \
  "$APP_ROOT/scripts/lib-ops-env.sh" 2>/dev/null || true

if [[ ! -f "$DEFAULTS" ]]; then
  cat >"$DEFAULTS" <<'EOF'
# Operations Hub — alerta /ready
PUBLIC_URL=https://ibot.ecolan.com
FAIL_THRESHOLD=2

# Elegí al menos un canal:
# ALERT_EMAIL_TO=ops@ecolan.com
# ALERT_TELEGRAM_CHAT_ID=          # chat id numérico; usa TELEGRAM_BOT_TOKEN del .env de la app
# ALERT_WEBHOOK_URL=               # Slack/Discord compatible con {"text":"..."}
EOF
  chmod 644 "$DEFAULTS"
  echo "Creado $DEFAULTS — editá un canal de alerta"
else
  # Asegurar claves documentadas sin pisar valores
  grep -q '^# ALERT_TELEGRAM_CHAT_ID' "$DEFAULTS" 2>/dev/null || \
    printf '\n# ALERT_TELEGRAM_CHAT_ID=\n' >>"$DEFAULTS"
fi

cat >"$CRON_FILE" <<EOF
# Operations Hub — readiness alert cada 2 minutos
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin
*/2 * * * * root /bin/bash $APP_ROOT/scripts/alert-ready.sh >> /var/log/ops-hub-ready-alert.log 2>&1
EOF
chmod 644 "$CRON_FILE"

echo "OK — cron: $CRON_FILE"
echo "Config:    $DEFAULTS"
echo "Probar:    sudo bash $APP_ROOT/scripts/alert-ready.sh"
echo "Test alerta (fuerza fail): READY_URL=http://127.0.0.1:9/ready FAIL_THRESHOLD=1 sudo -E bash $APP_ROOT/scripts/alert-ready.sh || true"
echo "Log:       sudo tail -f /var/log/ops-hub-ready-alert.log"
