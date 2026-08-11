#!/usr/bin/env bash
# Restore Data Estate desde dump custom (pg_dump -Fc).
#
# Uso:
#   # Staging / drill (recomendado):
#   sudo bash scripts/restore-estate.sh /var/backups/ops-hub/ops_hub_estate_XXXX.dump \
#     --url 'postgresql://user:pass@127.0.0.1:5432/ops_hub_staging' --yes
#
#   # Producción (PELIGROSO — pide confirmación explícita):
#   sudo bash scripts/restore-estate.sh /var/backups/ops-hub/ops_hub_estate_latest.dump \
#     --yes --i-understand-this-wipes-target
#
# Sin --url usa DATABASE_URL del .env de APP_ROOT.
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/operations-hub}"
DUMP=""
TARGET_URL=""
YES=0
WIPE_OK=0

red() { printf '\033[31m%s\033[0m\n' "$*"; }
grn() { printf '\033[32m%s\033[0m\n' "$*"; }
ylw() { printf '\033[33m%s\033[0m\n' "$*"; }

usage() {
  sed -n '2,14p' "$0" | sed 's/^# \?//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage 0 ;;
    --url) TARGET_URL="${2:-}"; shift 2 ;;
    --yes|-y) YES=1; shift ;;
    --i-understand-this-wipes-target) WIPE_OK=1; shift ;;
    -*)
      red "Flag desconocida: $1"
      usage 1
      ;;
    *)
      if [[ -z "$DUMP" ]]; then DUMP="$1"; shift
      else red "Argumento extra: $1"; usage 1
      fi
      ;;
  esac
done

if [[ -z "$DUMP" ]]; then
  red "Falta ruta al .dump"
  usage 1
fi
if [[ ! -f "$DUMP" ]]; then
  # Permite symlink latest
  if [[ -L "$DUMP" && -e "$DUMP" ]]; then
    :
  else
    red "No existe dump: $DUMP"
    exit 1
  fi
fi

load_env_file() {
  local file="$1"
  [[ -f "$file" ]] || return 0
  local line key val
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line#"${line%%[![:space:]]*}"}"
    [[ -z "$line" || "$line" == \#* ]] && continue
    [[ "$line" == export\ * ]] && line="${line#export }"
    [[ "$line" == *=* ]] || continue
    key="${line%%=*}"
    val="${line#*=}"
    key="${key%"${key##*[![:space:]]}"}"
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    if [[ ${#val} -ge 2 ]]; then
      if [[ "${val:0:1}" == '"' && "${val: -1}" == '"' ]]; then
        val="${val:1:${#val}-2}"
      elif [[ "${val:0:1}" == "'" && "${val: -1}" == "'" ]]; then
        val="${val:1:${#val}-2}"
      fi
    fi
    export "$key=$val"
  done < "$file"
}

if [[ -z "$TARGET_URL" ]]; then
  load_env_file "$APP_ROOT/.env"
  TARGET_URL="${DATABASE_URL:-}"
  if [[ -z "$TARGET_URL" && -n "${POSTGRES_USER:-}" && -n "${POSTGRES_DB:-}" ]]; then
    TARGET_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:5432/${POSTGRES_DB}"
  fi
fi

if [[ -z "$TARGET_URL" ]]; then
  red "Sin URL destino: pasá --url o definí DATABASE_URL"
  exit 1
fi

PG_URL="${TARGET_URL/postgresql+psycopg:\/\//postgresql:\/\/}"
PG_URL="${PG_URL/postgresql+psycopg2:\/\//postgresql:\/\/}"

# Detectar si el destino parece producción (mismo host que .env de la app)
PROD_LIKE=0
if [[ -f "$APP_ROOT/.env" ]]; then
  load_env_file "$APP_ROOT/.env"
  PROD_DB="${DATABASE_URL:-}"
  PROD_DB="${PROD_DB/postgresql+psycopg:\/\//postgresql:\/\/}"
  PROD_DB="${PROD_DB/postgresql+psycopg2:\/\//postgresql:\/\/}"
  if [[ -n "$PROD_DB" && "$PG_URL" == "$PROD_DB" ]]; then
    PROD_LIKE=1
  fi
fi

ylw "Dump:    $DUMP"
ylw "Target:  $(echo "$PG_URL" | sed -E 's#://([^:/@]+):[^@]+@#://\1:***@#')"
if [[ "$PROD_LIKE" -eq 1 ]]; then
  red "ADVERTENCIA: el destino coincide con DATABASE_URL de producción ($APP_ROOT)."
fi

if [[ "$YES" -ne 1 ]]; then
  red "Abortado: falta --yes"
  exit 1
fi
if [[ "$PROD_LIKE" -eq 1 && "$WIPE_OK" -ne 1 ]]; then
  red "Para restaurar sobre la DB de producción agregá: --i-understand-this-wipes-target"
  exit 1
fi

if ! command -v pg_restore >/dev/null 2>&1; then
  red "pg_restore no encontrado"
  exit 1
fi
if ! command -v psql >/dev/null 2>&1; then
  red "psql no encontrado"
  exit 1
fi

ylw "==> pg_restore --clean --if-exists"
pg_restore --clean --if-exists --no-owner --no-acl -d "$PG_URL" "$DUMP"

ylw "==> Verificación"
ORGS="$(psql "$PG_URL" -Atc 'SELECT COUNT(*) FROM organizations' 2>/dev/null || echo FAIL)"
TICKETS="$(psql "$PG_URL" -Atc 'SELECT COUNT(*) FROM tickets_estate' 2>/dev/null || echo FAIL)"
if [[ "$ORGS" == "FAIL" ]]; then
  red "Restore terminó pero no pude leer organizations — revisá schema"
  exit 1
fi
grn "OK — organizations=$ORGS tickets_estate=$TICKETS"
echo "Reiniciá la API tras restore: sudo systemctl restart operations-hub-api"
