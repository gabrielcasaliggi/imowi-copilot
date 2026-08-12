#!/usr/bin/env bash
# Alerta mínima de readiness — Operations Hub (Batán)
# Chequea GET /ready; si falla N veces seguidas, loguea y notifica.
#
# Uso:
#   bash scripts/alert-ready.sh https://ibot.ecolan.com
#
# Canales (en /etc/default/operations-hub-alert o env):
#   ALERT_WEBHOOK_URL=https://hooks.slack.com/...
#   ALERT_EMAIL_TO=ops@ecolan.com          # vía SMTP del .env de la app
#   ALERT_TELEGRAM_CHAT_ID=123456789       # + TELEGRAM_BOT_TOKEN en .env
#   FAIL_THRESHOLD=2
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/operations-hub}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib-ops-env.sh
source "$SCRIPT_DIR/lib-ops-env.sh"

# Cron defaults primero; .env de la app rellena lo que falte
[[ -f /etc/default/operations-hub-alert ]] && set -a && . /etc/default/operations-hub-alert && set +a || true
ops_load_env_file "$APP_ROOT/.env"

BASE_URL="${1:-${PUBLIC_URL:-https://ibot.ecolan.com}}"
BASE_URL="${BASE_URL%/}"
READY_URL="${READY_URL:-${BASE_URL}/ready}"
STATE_DIR="${STATE_DIR:-/var/tmp/ops-hub-ready-alert}"
STATE_FILE="$STATE_DIR/fail_count"
FAIL_THRESHOLD="${FAIL_THRESHOLD:-2}"
TIMEOUT="${TIMEOUT:-8}"

mkdir -p "$STATE_DIR"

code="$(curl -sS -o /tmp/ops-hub-ready.json -w '%{http_code}' --max-time "$TIMEOUT" "$READY_URL" || echo 000)"
body="$(cat /tmp/ops-hub-ready.json 2>/dev/null || true)"

notify() {
  local msg="$1"
  local subject="[ops-hub] readiness"
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $msg" >>"$STATE_DIR/alerts.log"

  if [[ -n "${ALERT_WEBHOOK_URL:-}" ]]; then
    curl -sS -X POST "$ALERT_WEBHOOK_URL" \
      -H 'Content-Type: application/json' \
      -d "{\"text\":$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$msg")}" \
      >/dev/null 2>&1 || true
  fi

  if [[ -n "${ALERT_EMAIL_TO:-}" ]] || [[ -n "${ALERT_TELEGRAM_CHAT_ID:-}" ]]; then
    if [[ -x "$APP_ROOT/.venv/bin/python" ]]; then
      APP_ROOT="$APP_ROOT" "$APP_ROOT/.venv/bin/python" "$SCRIPT_DIR/send-ops-alert.py" \
        --subject "$subject" --body "$msg" --app-root "$APP_ROOT" \
        >>"$STATE_DIR/alerts.log" 2>&1 || true
    elif command -v mail >/dev/null 2>&1 && [[ -n "${ALERT_EMAIL_TO:-}" ]]; then
      printf '%s\n' "$msg" | mail -s "$subject" "$ALERT_EMAIL_TO" || true
    fi
  fi
}

if [[ "$code" == "200" ]] && echo "$body" | grep -q '"ready"[[:space:]]*:[[:space:]]*true'; then
  prev="$(cat "$STATE_FILE" 2>/dev/null || echo 0)"
  echo 0 >"$STATE_FILE"
  if [[ "${prev:-0}" -ge "$FAIL_THRESHOLD" ]]; then
    notify "RECOVERED: $READY_URL vuelve a 200 (ready=true)"
  fi
  exit 0
fi

fails="$(cat "$STATE_FILE" 2>/dev/null || echo 0)"
fails=$((fails + 1))
echo "$fails" >"$STATE_FILE"
msg="FAIL ($fails): $READY_URL → HTTP $code body=${body:0:200}"
echo "$msg" >&2

if [[ "$fails" -ge "$FAIL_THRESHOLD" ]]; then
  if [[ "$fails" -eq "$FAIL_THRESHOLD" || $((fails % 10)) -eq 0 ]]; then
    notify "$msg"
  fi
  exit 1
fi
exit 1
