#!/usr/bin/env bash
# Verifica despliegue productivo: health + Postgres + auth configurado.
# Uso: ./scripts/verify-production.sh https://tu-api.onrender.com

set -euo pipefail

API_URL="${1:-http://127.0.0.1:8000}"
API_URL="${API_URL%/}"

echo "==> Verificando $API_URL/health"

BODY="$(curl -sf "$API_URL/health")"
echo "$BODY" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d.get('status') == 'ok', 'status no es ok'
assert d.get('estate') is True, 'estate no activo'
db = d.get('database')
print(f'  status: ok')
print(f'  database: {db}')
print(f'  estate_seeded: {d.get(\"estate_seeded\")}')
print(f'  auth_secret_configured: {d.get(\"auth_secret_configured\")}')
if d.get('env') == 'production':
    assert db == 'postgresql', 'en producción se espera database=postgresql'
    assert d.get('database_connected') is True, 'sin conexión a Postgres'
    print('  database_connected: True')
print('OK — health check pasó')
"

echo ""
echo "==> Verificando login (opcional, requiere credenciales)"
if [[ -n "${VERIFY_USER:-}" && -n "${VERIFY_PASSWORD:-}" ]]; then
  TOKEN="$(curl -sf -X POST "$API_URL/api/login" \
    -H 'Content-Type: application/json' \
    -d "{\"usuario\":\"$VERIFY_USER\",\"password\":\"$VERIFY_PASSWORD\"}" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin).get("token",""))')"
  [[ -n "$TOKEN" ]] || { echo "Login falló"; exit 1; }
  curl -sf -H "Authorization: Bearer $TOKEN" "$API_URL/api/me" >/dev/null
  echo "  login: OK ($VERIFY_USER)"
else
  echo "  (omitido — export VERIFY_USER y VERIFY_PASSWORD para probar login)"
fi

echo ""
echo "==> Superficie pública (hardening)"
DOCS_CODE="$(curl -s -o /dev/null -w '%{http_code}' "$API_URL/docs" || true)"
OPENAPI_CODE="$(curl -s -o /dev/null -w '%{http_code}' "$API_URL/openapi.json" || true)"
GUEST_CODE="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API_URL/api/v1/portal/session" \
  -H 'Content-Type: application/json' \
  -d '{"org_slug":"coop-batan"}' || true)"
CHAT_CODE="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API_URL/api/chat" \
  -H 'Content-Type: application/json' \
  -d '{}' || true)"

echo "  /docs HTTP $DOCS_CODE"
echo "  /openapi.json HTTP $OPENAPI_CODE"
echo "  POST /api/v1/portal/session (guest) HTTP $GUEST_CODE"
echo "  POST /api/chat (legacy) HTTP $CHAT_CODE"

ENV_NAME="$(echo "$BODY" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("env",""))')"
if [[ "${EXPECT_HARDENED:-}" == "1" || "$ENV_NAME" == "production" ]]; then
  [[ "$DOCS_CODE" == "404" ]] || { echo "FAIL: /docs debería ser 404 en production"; exit 1; }
  [[ "$GUEST_CODE" == "401" || "$GUEST_CODE" == "403" ]] || {
    echo "WARN: guest session HTTP $GUEST_CODE (esperado 401 si PORTAL_ALLOW_GUEST=false)"
  }
  [[ "$CHAT_CODE" == "404" || "$CHAT_CODE" == "405" ]] || {
    echo "WARN: legacy /api/chat HTTP $CHAT_CODE (esperado 404 si ENABLE_LEGACY_API=false)"
  }
fi

echo ""
echo "==> WhatsApp webhook (HMAC)"
WA_CODE="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API_URL/api/v1/whatsapp/webhook" \
  -H 'Content-Type: application/json' \
  -d '{}' || true)"
echo "  POST /api/v1/whatsapp/webhook sin firma HTTP $WA_CODE"
if [[ "$ENV_NAME" == "production" ]]; then
  # Con secret: 403. Sin secret en prod: 503. 200 solo si no hay secret y no es prod (no debería).
  if [[ "$WA_CODE" != "403" && "$WA_CODE" != "503" && "$WA_CODE" != "400" ]]; then
    echo "  WARN: webhook abierto sin firma (HTTP $WA_CODE) — revisá WHATSAPP_APP_SECRET"
  fi
fi

echo ""
echo "==> HSTS (solo HTTPS)"
if [[ "$API_URL" == https://* ]]; then
  if curl -sI "$API_URL/" | grep -qi 'strict-transport-security'; then
    echo "  HSTS: presente"
  else
    echo "  WARN: HSTS no detectado en headers"
  fi
else
  echo "  (omitido — URL no es https)"
fi

echo ""
echo "Despliegue verificado."
