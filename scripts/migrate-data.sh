#!/usr/bin/env bash
# Migra el Data Estate desde Supabase al PostgreSQL local (instalación nativa).
#
# IMPORTANTE:
# - Usá la URI DIRECTA de Supabase (puerto 5432), no el pooler :6543.
# - El stack nativo debe estar instalado (scripts/install-server.sh).
# - Reemplaza el contenido local del Data Estate.
#
# Uso:
#   export SUPABASE_DATABASE_URL='postgresql://postgres.[ref]:PASS@db.[ref].supabase.co:5432/postgres'
#   sudo bash scripts/migrate-data.sh --yes
#
# Opciones:
#   --dump-only FILE
#   --restore-only FILE
#   --yes

set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]}"
if command -v readlink >/dev/null 2>&1; then
  SCRIPT_PATH="$(readlink -f "$SCRIPT_PATH" 2>/dev/null || realpath "$SCRIPT_PATH" 2>/dev/null || echo "$SCRIPT_PATH")"
fi
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

ENV_FILE="$ROOT/.env"
DUMP_ONLY=""
RESTORE_ONLY=""
ASSUME_YES=0
STAMP="$(date +%Y%m%d-%H%M%S)"
DUMP_DIR="$ROOT/.tmp/migrations"
DUMP_FILE="$DUMP_DIR/estate-${STAMP}.dump"

ESTATE_TABLES=(
  organizations
  users
  knowledge_articles
  knowledge_contributions
  network_elements
  lineas_jsc
  tickets_estate
  ticket_events
  casos_conversacion
  ticket_notifications
  audit_events
  abonados
  conversaciones_canal
  mensajes_canal
  platform_config
  pilot_events
)

usage() { sed -n '2,18p' "$0" | sed 's/^# \?//'; exit 0; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dump-only) DUMP_ONLY="${2:?}"; shift 2 ;;
    --restore-only) RESTORE_ONLY="${2:?}"; shift 2 ;;
    --yes|-y) ASSUME_YES=1; shift ;;
    -h|--help) usage ;;
    *) echo "Opción desconocida: $1" >&2; usage ;;
  esac
done

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

load_env() {
  [[ -f "$ENV_FILE" ]] || die "No existe $ENV_FILE — corré primero install-server.sh"
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
  POSTGRES_USER="${POSTGRES_USER:-ops_hub}"
  POSTGRES_DB="${POSTGRES_DB:-ops_hub}"
  POSTGRES_PASSWORD="${POSTGRES_PASSWORD:?Falta POSTGRES_PASSWORD en .env}"
  HTTP_PORT="${HTTP_PORT:-80}"
}

confirm() {
  [[ "$ASSUME_YES" -eq 1 ]] && return 0
  read -r -p "¿Continuar? [y/N] " ans
  [[ "$ans" == "y" || "$ans" == "Y" ]] || die "Cancelado"
}

ensure_pg_client() {
  if ! command -v pg_dump >/dev/null 2>&1 || ! command -v pg_restore >/dev/null 2>&1; then
    log "Instalando cliente PostgreSQL"
    apt-get update -y
    DEBIAN_FRONTEND=noninteractive apt-get install -y postgresql-client
  fi
}

do_dump() {
  local url="$1"
  local out="$2"
  mkdir -p "$(dirname "$out")"

  log "Exportando Data Estate desde origen → $out"
  echo "Tablas: ${ESTATE_TABLES[*]}"

  # Parsear URL con Python (más seguro que sed)
  eval "$(python3 - "$url" <<'PY'
import sys, shlex, urllib.parse
u = urllib.parse.urlparse(sys.argv[1])
print("export PGHOST=" + shlex.quote(u.hostname or ""))
print("export PGPORT=" + shlex.quote(str(u.port or 5432)))
print("export PGUSER=" + shlex.quote(urllib.parse.unquote(u.username or "")))
print("export PGPASSWORD=" + shlex.quote(urllib.parse.unquote(u.password or "")))
db = (u.path or "/postgres").lstrip("/") or "postgres"
print("export PGDATABASE=" + shlex.quote(db))
PY
)"
  export PGSSLMODE="${PGSSLMODE:-require}"

  local args=()
  local t
  for t in "${ESTATE_TABLES[@]}"; do
    args+=(-t "$t")
  done

  pg_dump -Fc --no-owner --no-acl "${args[@]}" -f "$out"
  [[ -s "$out" ]] || die "Dump vacío o no generado"
  ls -lh "$out"
}

do_restore() {
  local dump="$1"
  [[ -f "$dump" ]] || die "No existe el dump: $dump"

  log "Restaurando en Postgres local (${POSTGRES_DB})"
  echo "Esto REEMPLAZA las tablas del Data Estate en el servidor."
  confirm

  log "Deteniendo API durante el restore"
  systemctl stop operations-hub-api operations-hub-frontend 2>/dev/null || true

  export PGPASSWORD="$POSTGRES_PASSWORD"
  set +e
  pg_restore \
    --clean \
    --if-exists \
    --no-owner \
    --no-acl \
    -h 127.0.0.1 \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    "$dump"
  local rc=$?
  set -e
  if [[ "$rc" -gt 1 ]]; then
    die "pg_restore falló con código $rc"
  fi

  log "Verificando tablas"
  psql -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
    "SELECT relname AS tabla, n_live_tup AS filas_aprox
     FROM pg_stat_user_tables ORDER BY relname;"

  log "Reiniciando servicios"
  systemctl start operations-hub-api
  sleep 5
  systemctl start operations-hub-frontend
  systemctl reload nginx 2>/dev/null || true

  log "Health check"
  curl -fsS "http://127.0.0.1:${HTTP_PORT}/health" | python3 -m json.tool || true
}

main() {
  [[ "${EUID}" -eq 0 ]] || die "Ejecutá con sudo (para systemctl y apt)"
  load_env
  ensure_pg_client

  if [[ -n "$RESTORE_ONLY" ]]; then
    do_restore "$RESTORE_ONLY"
    log "Restore completado"
    exit 0
  fi

  local src="${SUPABASE_DATABASE_URL:-}"
  [[ -n "$src" ]] || die "Definí SUPABASE_DATABASE_URL (URI directa :5432) en entorno o .env"
  [[ "$src" != *":6543"* ]] || die "La URL usa pooler :6543. Usá conexión DIRECTA puerto 5432."

  local out="${DUMP_ONLY:-$DUMP_FILE}"
  do_dump "$src" "$out"

  if [[ -n "$DUMP_ONLY" ]]; then
    log "Solo dump — $out"
    exit 0
  fi

  do_restore "$out"
  log "Migración completada"
  echo "Dump guardado en: $out"
}

main
