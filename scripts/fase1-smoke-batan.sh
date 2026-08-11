#!/usr/bin/env bash
# Smoke Fase 1 Batán/Ecolan — health, hardening demo/reset, anti-ticket N1.
# Uso:
#   ./scripts/fase1-smoke-batan.sh https://ibot.ecolan.com
#   VERIFY_USER=admin@… VERIFY_PASSWORD=… ./scripts/fase1-smoke-batan.sh https://ibot.ecolan.com
set -euo pipefail

API_URL="${1:-https://ibot.ecolan.com}"
API_URL="${API_URL%/}"
FAIL=0

red() { printf 'FAIL: %s\n' "$*" >&2; FAIL=1; }
ok() { printf 'OK   %s\n' "$*"; }
warn() { printf 'WARN %s\n' "$*"; }

echo "==> Fase 1 smoke → $API_URL"

BODY="$(curl -sf "$API_URL/health")" || { red "health no responde"; exit 1; }
python3 -c '
import json, sys
d = json.loads(sys.argv[1])
assert d.get("status") in ("ok", "degraded"), d
print(
    "  status=%s env=%s db=%s connected=%s"
    % (d.get("status"), d.get("env"), d.get("database"), d.get("database_connected"))
)
print(
    "  sentry_configured=%s demo_reset_enabled=%s"
    % (d.get("sentry_configured"), d.get("demo_reset_enabled"))
)
if d.get("env") == "production" and d.get("demo_reset_enabled") is True:
    raise SystemExit("demo_reset_enabled=true en production — set ENABLE_DEMO_RESET=false")
if d.get("env") == "production" and not d.get("database_connected"):
    raise SystemExit("database_connected=false en production")
' "$BODY"
ok "health"

READY="$(curl -sf "$API_URL/ready")" || { red "/ready no responde (503 o down)"; exit 1; }
python3 -c '
import json, sys
d = json.loads(sys.argv[1])
assert d.get("ready") is True, d
assert d.get("database_connected") is True, d
print("  ready=true database=%s" % d.get("database"))
' "$READY"
ok "ready"

RESET_CODE="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API_URL/api/v1/demo/reset" \
  -H 'Content-Type: application/json' -d '{"incluir_tickets":false}' || true)"
if [[ "$RESET_CODE" == "401" || "$RESET_CODE" == "403" ]]; then
  ok "demo/reset sin auth → HTTP $RESET_CODE"
else
  red "demo/reset sin auth → HTTP $RESET_CODE (esperado 401/403)"
fi

if [[ -n "${VERIFY_USER:-}" && -n "${VERIFY_PASSWORD:-}" ]]; then
  TOKEN="$(curl -sf -X POST "$API_URL/api/login" \
    -H 'Content-Type: application/json' \
    -d "{\"usuario\":\"$VERIFY_USER\",\"password\":\"$VERIFY_PASSWORD\"}" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin).get("token",""))')"
  [[ -n "$TOKEN" ]] || { red "login falló"; exit 1; }
  ok "login $VERIFY_USER"

  R2="$(curl -s -o /tmp/fase1-reset.json -w '%{http_code}' -X POST "$API_URL/api/v1/demo/reset" \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' \
    -d '{"incluir_tickets":false}' || true)"
  if [[ "$R2" == "403" ]]; then
    ok "demo/reset autenticado bloqueado (HTTP 403)"
  else
    warn "demo/reset autenticado HTTP $R2 (en prod endurecido debe ser 403)"
    cat /tmp/fase1-reset.json 2>/dev/null || true
    echo
  fi

  GUEST="$(curl -s -X POST "$API_URL/api/v1/portal/session" \
    -H 'Content-Type: application/json' \
    -d '{"org_slug":"coop-batan"}')"
  PTOKEN="$(echo "$GUEST" | python3 -c 'import json,sys
try:
  d=json.load(sys.stdin); print(d.get("portal_token") or "")
except Exception:
  print("")')"
  if [[ -n "$PTOKEN" ]]; then
    MSG="$(curl -s -X POST "$API_URL/api/v1/portal/messages" \
      -H "Authorization: Bearer $PTOKEN" \
      -H 'Content-Type: application/json' \
      -d '{"texto":"Quiero hablar con un operador"}')"
    echo "$MSG" | python3 -c '
import json, sys
d = json.load(sys.stdin)
tid = d.get("ticket_id") or ""
estado = d.get("estado") or ""
resp = (d.get("respuesta") or "").lower()
if tid or estado == "espera_agente":
    raise SystemExit(f"ticket prematuro: estado={estado} ticket={tid} resp={resp[:120]}")
if "ticket" in resp and "jsc-" in resp:
    raise SystemExit(f"respuesta menciona ticket: {resp[:160]}")
print(f"  anti-ticket OK estado={estado}")
'
    ok "anti-ticket N1 (pedido humano sin síntoma)"

    GUEST2="$(curl -s -X POST "$API_URL/api/v1/portal/session" \
      -H 'Content-Type: application/json' -d '{"org_slug":"coop-batan"}')"
    P2="$(echo "$GUEST2" | python3 -c 'import json,sys
try:
  print(json.load(sys.stdin).get("portal_token") or "")
except Exception:
  print("")')"
    if [[ -n "$P2" ]]; then
      MSG2="$(curl -s -X POST "$API_URL/api/v1/portal/messages" \
        -H "Authorization: Bearer $P2" \
        -H 'Content-Type: application/json' \
        -d '{"texto":"Me cortaron el servicio por falta de pago, como pago?"}')"
      echo "$MSG2" | python3 -c '
import json, sys
d = json.load(sys.stdin)
resp = (d.get("respuesta") or "").lower()
if "qr" not in resp and "fiserv" not in resp and "mercado pago" not in resp:
    raise SystemExit(f"pago sin guía QR: {resp[:200]}")
print("  guía QR OK")
'
      ok "guía QR en corte/deuda"
    fi
  else
    warn "portal guest no disponible (PORTAL_ALLOW_GUEST=false?) — smoke N1 omitido"
  fi
else
  warn "sin VERIFY_USER/PASSWORD — omitido login + N1 smoke autenticado"
fi

WA="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API_URL/api/v1/whatsapp/webhook" \
  -H 'Content-Type: application/json' -d '{}' || true)"
if [[ "$WA" == "403" || "$WA" == "503" || "$WA" == "400" ]]; then
  ok "WhatsApp webhook sin firma → HTTP $WA"
else
  warn "WhatsApp webhook HTTP $WA — revisá WHATSAPP_APP_SECRET"
fi

echo ""
if [[ "$FAIL" -ne 0 ]]; then
  echo "Fase 1 smoke: FALLÓ"
  exit 1
fi
echo "Fase 1 smoke: OK"
