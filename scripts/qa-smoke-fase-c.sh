#!/usr/bin/env bash
# Smoke Fase C: LLM metrics endpoint (API) + Playwright opcional.
# Uso:
#   ./scripts/qa-smoke-fase-c.sh https://ibot.ecolan.com
#   VERIFY_USER=... VERIFY_PASSWORD=... ./scripts/qa-smoke-fase-c.sh https://ibot.ecolan.com --ui

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE="${1:-http://127.0.0.1:8000}"
BASE="${BASE%/}"
shift || true

echo "==> Health $BASE/health"
curl -fsS "$BASE/health" >/dev/null
echo "  ok"

echo "==> Login + metrics/llm"
if [[ -z "${VERIFY_USER:-}" || -z "${VERIFY_PASSWORD:-}" ]]; then
  echo "  (omitido metrics — export VERIFY_USER y VERIFY_PASSWORD)"
else
  TOKEN="$(curl -sf -X POST "$BASE/api/login" \
    -H 'Content-Type: application/json' \
    -d "{\"usuario\":\"$VERIFY_USER\",\"password\":\"$VERIFY_PASSWORD\"}" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin).get("token",""))')"
  [[ -n "$TOKEN" ]] || { echo "Login falló"; exit 1; }
  curl -fsS -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/metrics/llm" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("status")=="ok"; print("  calls_total:", d.get("calls_total"), "avg_ms:", d.get("avg_latency_ms_ok"))'
fi

if [[ "${1:-}" == "--ui" ]]; then
  echo "==> Playwright smoke"
  cd "$ROOT"
  export QA_BASE_URL="${QA_BASE_URL:-$BASE}"
  # Si BASE es solo API :8000, UI suele estar en :3000 o mismo host sin puerto
  .venv/bin/python -m qa_bot.smoke_fase_c --base-url "$QA_BASE_URL" || true
fi

echo "Smoke Fase C listo."
