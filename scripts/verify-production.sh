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
echo "Despliegue verificado."
