#!/usr/bin/env bash
# Cierra en masa los tickets abiertos de una cooperativa (conserva historial).
#
# Preferido (código nuevo): POST /api/v1/tickets/bulk-close
# Fallback (API ya en prod): lista solo_abiertos y PUT estado=Cerrado uno a uno
#
# Uso:
#   ./scripts/cerrar-tickets-abiertos.sh                 # dry-run local coop-batan
#   ./scripts/cerrar-tickets-abiertos.sh --confirm       # ejecuta en local
#   API_URL=https://ibot.ecolan.com DEMO_USER=admin DEMO_PASS='...' \
#     ./scripts/cerrar-tickets-abiertos.sh coop-batan --confirm
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CONFIRM=0
TENANT="coop-batan"
ARGS=()
for arg in "$@"; do
  case "$arg" in
    --confirm|-y) CONFIRM=1 ;;
    --dry-run) CONFIRM=0 ;;
    *) ARGS+=("$arg") ;;
  esac
done
if [[ ${#ARGS[@]} -gt 0 ]]; then
  TENANT="${ARGS[0]}"
fi

API="${API_URL:-http://127.0.0.1:8000}"
USER="${DEMO_USER:-admin}"
PASS="${DEMO_PASS:-admin}"
RESOLUCION="${RESOLUCION_TECNICA:-Cierre masivo previo a pruebas en producción / validación piloto.}"

echo "→ Login ($USER) @ $API…"
TOKEN=$(curl -sf -X POST "$API/api/login" \
  -H "Content-Type: application/json" \
  -d "{\"usuario\":\"$USER\",\"password\":\"$PASS\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

AUTH=(-H "Authorization: Bearer $TOKEN" -H "X-Tenant-Slug: $TENANT" -H "Content-Type: application/json")

bulk_code=$(curl -s -o /tmp/bulk-close.json -w '%{http_code}' -X POST "$API/api/v1/tickets/bulk-close" \
  "${AUTH[@]}" \
  -d "$(python3 -c "import json; print(json.dumps({'dry_run': True, 'confirmar': False, 'resolucion_tecnica': '''$RESOLUCION'''}))")")

if [[ "$bulk_code" == "200" ]]; then
  echo "→ Usando endpoint bulk-close…"
  if [[ "$CONFIRM" -eq 0 ]]; then
    python3 -m json.tool </tmp/bulk-close.json
    echo
    echo "✓ Preview listo. Para ejecutar: $0 $TENANT --confirm"
    exit 0
  fi
  curl -sf -X POST "$API/api/v1/tickets/bulk-close" \
    "${AUTH[@]}" \
    -d "$(python3 -c "import json; print(json.dumps({'dry_run': False, 'confirmar': True, 'resolucion_tecnica': '''$RESOLUCION'''}))")" \
    | python3 -m json.tool
  exit 0
fi

echo "→ bulk-close no disponible (HTTP $bulk_code); fallback list+PUT…"
OFFSET=0
LIMIT=100
IDS=()
while true; do
  PAGE=$(curl -sf "$API/api/v1/tickets?solo_abiertos=true&limit=$LIMIT&offset=$OFFSET" "${AUTH[@]}")
  mapfile -t CHUNK < <(python3 -c "import sys,json; d=json.load(sys.stdin); print('\\n'.join(t['id'] for t in d.get('tickets',[])))" <<<"$PAGE")
  TOTAL=$(python3 -c "import sys,json; print(json.load(sys.stdin).get('total',0))" <<<"$PAGE")
  if [[ ${#CHUNK[@]} -eq 0 ]]; then
    break
  fi
  IDS+=("${CHUNK[@]}")
  OFFSET=$((OFFSET + LIMIT))
  if [[ ${#IDS[@]} -ge "$TOTAL" ]]; then
    break
  fi
done

echo "tickets_abiertos=${#IDS[@]} tenant=$TENANT total_api=${TOTAL:-?}"
if [[ ${#IDS[@]} -gt 0 ]]; then
  printf 'ids_sample=%s\n' "$(printf '%s,' "${IDS[@]:0:20}" | sed 's/,$//')"
fi

if [[ "$CONFIRM" -eq 0 ]]; then
  echo
  echo "✓ Preview listo (fallback). Para ejecutar: $0 $TENANT --confirm"
  exit 0
fi

closed=0
for tid in "${IDS[@]}"; do
  code=$(curl -s -o /tmp/close-one.json -w '%{http_code}' -X PUT "$API/api/v1/tickets/$tid" \
    "${AUTH[@]}" \
    -d "$(python3 -c "import json; print(json.dumps({'estado': 'Cerrado', 'resolucion_tecnica': '''$RESOLUCION''', 'estado_sla': 'Cerrado'}))")")
  if [[ "$code" == "200" ]]; then
    closed=$((closed + 1))
    echo "  cerrado $tid"
  else
    echo "  ERROR $tid HTTP $code $(cat /tmp/close-one.json)" >&2
  fi
done
echo "✓ cerrados=$closed / ${#IDS[@]}"
