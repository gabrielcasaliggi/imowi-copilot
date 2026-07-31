#!/usr/bin/env bash
# Backup Data Estate (Postgres local) — Operations Hub
# Uso: sudo bash scripts/backup-estate.sh [/var/backups/ops-hub]
set -euo pipefail

DEST="${1:-/var/backups/ops-hub}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$DEST"

# Cargar .env del proyecto si existe
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

DB_URL="${DATABASE_URL:-}"
if [[ -z "$DB_URL" && -n "${POSTGRES_USER:-}" && -n "${POSTGRES_DB:-}" ]]; then
  DB_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:5432/${POSTGRES_DB}"
fi

if [[ -z "$DB_URL" ]]; then
  echo "ERROR: definí DATABASE_URL o POSTGRES_*" >&2
  exit 1
fi

# Normalizar driver SQLAlchemy → pg_dump
PG_URL="${DB_URL/postgresql+psycopg:\/\//postgresql:\/\/}"
PG_URL="${PG_URL/postgresql+psycopg2:\/\//postgresql:\/\/}"

OUT="$DEST/ops_hub_estate_${STAMP}.dump"
echo "Backup → $OUT"
pg_dump --format=custom --file="$OUT" "$PG_URL"
ln -sfn "$(basename "$OUT")" "$DEST/ops_hub_estate_latest.dump"
echo "OK. Restore: pg_restore --clean --if-exists -d \"\$DATABASE_URL\" $OUT"
echo "Drill recomendado: restaurar en DB staging al menos 1 vez/mes."
