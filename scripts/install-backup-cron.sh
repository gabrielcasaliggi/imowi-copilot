#!/usr/bin/env bash
# Instala cron diario de backup del Data Estate (Batán / Fase 1).
# Uso: sudo bash scripts/install-backup-cron.sh
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/operations-hub}"
BACKUP_DEST="${BACKUP_DEST:-/var/backups/ops-hub}"
CRON_FILE="/etc/cron.d/operations-hub-backup"
HOUR="${BACKUP_HOUR:-3}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Ejecutá con sudo" >&2
  exit 1
fi

if [[ ! -x "$APP_ROOT/scripts/backup-estate.sh" ]]; then
  echo "No encuentro $APP_ROOT/scripts/backup-estate.sh" >&2
  exit 1
fi

mkdir -p "$BACKUP_DEST"
chmod 750 "$BACKUP_DEST"

cat > "$CRON_FILE" <<EOF
# Operations Hub — backup diario Data Estate (UTC)
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin
${HOUR} 0 * * * root /bin/bash $APP_ROOT/scripts/backup-estate.sh $BACKUP_DEST >> /var/log/ops-hub-backup.log 2>&1
EOF
chmod 644 "$CRON_FILE"

echo "OK — cron instalado: $CRON_FILE (diario ${HOUR}:00 UTC)"
echo "Probar ahora: sudo bash $APP_ROOT/scripts/backup-estate.sh $BACKUP_DEST"
echo "Ver log:     sudo tail -f /var/log/ops-hub-backup.log"
