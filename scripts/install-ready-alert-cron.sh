#!/usr/bin/env bash
# Instala cron de alerta /ready cada 2 minutos.
# Uso: sudo bash scripts/install-ready-alert-cron.sh
#
# Opcional en /etc/default/operations-hub-alert (sourceable):
#   PUBLIC_URL=https://ibot.ecolan.com
#   ALERT_WEBHOOK_URL=...
#   ALERT_EMAIL_TO=ops@ecolan.com
#   FAIL_THRESHOLD=2
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
chmod +x "$APP_ROOT/scripts/alert-ready.sh"

if [[ ! -f "$DEFAULTS" ]]; then
  cat >"$DEFAULTS" <<'EOF'
# Operations Hub — alerta /ready
PUBLIC_URL=https://ibot.ecolan.com
FAIL_THRESHOLD=2
# ALERT_WEBHOOK_URL=
# ALERT_EMAIL_TO=
EOF
  chmod 644 "$DEFAULTS"
fi

cat >"$CRON_FILE" <<EOF
# Operations Hub — readiness alert cada 2 minutos
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin
*/2 * * * * root set -a; [ -f $DEFAULTS ] && . $DEFAULTS; set +a; /bin/bash $APP_ROOT/scripts/alert-ready.sh >> /var/log/ops-hub-ready-alert.log 2>&1
EOF
chmod 644 "$CRON_FILE"

echo "OK — cron: $CRON_FILE"
echo "Config:    $DEFAULTS"
echo "Probar:    sudo bash $APP_ROOT/scripts/alert-ready.sh"
echo "Log:       sudo tail -f /var/log/ops-hub-ready-alert.log"
