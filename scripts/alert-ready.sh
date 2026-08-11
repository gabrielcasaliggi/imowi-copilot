#!/usr/bin/env bash
# Alerta mínima de readiness — Operations Hub (Batán)
# Chequea GET /ready; si falla N veces seguidas, loguea y opcionalmente notifica.
#
# Uso:
#   bash scripts/alert-ready.sh https://ibot.ecolan.com
#   READY_URL=http://127.0.0.1:8000/ready FAIL_THRESHOLD=2 bash scripts/alert-ready.sh
#
# Notificación (opcionales):
#   ALERT_WEBHOOK_URL=https://hooks.slack.com/...   # POST JSON {text}
#   ALERT_EMAIL_TO=ops@ecolan.com                   # usa mail(1) si existe
set -euo pipefail

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
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $msg" >>"$STATE_DIR/alerts.log"
  if [[ -n "${ALERT_WEBHOOK_URL:-}" ]]; then
    curl -sS -X POST "$ALERT_WEBHOOK_URL" \
      -H 'Content-Type: application/json' \
      -d "{\"text\":$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$msg")}" \
      >/dev/null 2>&1 || true
  fi
  if [[ -n "${ALERT_EMAIL_TO:-}" ]] && command -v mail >/dev/null 2>&1; then
    printf '%s\n' "$msg" | mail -s "[ops-hub] readiness FAIL" "$ALERT_EMAIL_TO" || true
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
  # Evitar spam: notificar solo al cruzar el umbral o cada 10 fallos
  if [[ "$fails" -eq "$FAIL_THRESHOLD" || $((fails % 10)) -eq 0 ]]; then
    notify "$msg"
  fi
  exit 1
fi
exit 1
