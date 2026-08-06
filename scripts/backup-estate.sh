#!/usr/bin/env bash
# Backup Data Estate (Postgres local) — Operations Hub
# Uso: sudo bash scripts/backup-estate.sh [/var/backups/ops-hub]
set -euo pipefail

DEST="${1:-/var/backups/ops-hub}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$DEST"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Carga segura de .env: KEY=valor (todo tras el primer =), sin `source`
# (evita "batan.coop: command not found" si SMTP_FROM no está entre comillas).
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

load_env_file "$ROOT/.env"

DB_URL="${DATABASE_URL:-}"
if [[ -z "$DB_URL" && -n "${POSTGRES_USER:-}" && -n "${POSTGRES_DB:-}" ]]; then
  DB_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:5432/${POSTGRES_DB}"
fi

if [[ -z "$DB_URL" ]]; then
  echo "ERROR: definí DATABASE_URL o POSTGRES_*" >&2
  exit 1
fi

PG_URL="${DB_URL/postgresql+psycopg:\/\//postgresql:\/\/}"
PG_URL="${PG_URL/postgresql+psycopg2:\/\//postgresql:\/\/}"

OUT="$DEST/ops_hub_estate_${STAMP}.dump"
echo "Backup → $OUT"
pg_dump --format=custom --file="$OUT" "$PG_URL"
ln -sfn "$(basename "$OUT")" "$DEST/ops_hub_estate_latest.dump"

# Retener 14 días
find "$DEST" -maxdepth 1 -name 'ops_hub_estate_*.dump' -type f -mtime +14 -delete 2>/dev/null || true

echo "OK. Restore: pg_restore --clean --if-exists -d \"\$DATABASE_URL\" $OUT"
echo "Drill recomendado: restaurar en DB staging al menos 1 vez/mes."
