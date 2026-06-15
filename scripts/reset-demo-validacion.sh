#!/usr/bin/env bash
# Resetea casos conversacionales y tickets de una cooperativa demo.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TENANT="${1:-coop-batan}"
API="${API_URL:-http://127.0.0.1:8000}"
USER="${DEMO_USER:-batan}"
PASS="${DEMO_PASS:-batan}"

echo "→ Login ($USER)…"
TOKEN=$(curl -sf -X POST "$API/api/login" \
  -H "Content-Type: application/json" \
  -d "{\"usuario\":\"$USER\",\"password\":\"$PASS\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

echo "→ Reset demo tenant=$TENANT…"
curl -sf -X POST "$API/api/v1/demo/reset" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Slug: $TENANT" \
  -d '{"incluir_tickets": true}' \
  | python3 -m json.tool

echo "✓ Demo lista para revalidar escenarios."
