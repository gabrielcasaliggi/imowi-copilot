#!/usr/bin/env bash
# Deploy de Operations Hub / Eko. Se ejecuta en la máquina del operador (no en el server).
# Procedimiento de referencia: DEPLOY.md. Sin secretos: SSH por clave, no se lee ni imprime ninguna.
#
# Uso: scripts/deploy.sh [--dry-run] [--yes]
#   --dry-run  imprime los comandos; no hace push ni nada remoto
#   --yes      omite la confirmación interactiva (solo uso no interactivo explícito)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${DEPLOY_ENV_FILE:-$ROOT/scripts/deploy.env}"
DRY_RUN=0
ASSUME_YES=0

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --yes) ASSUME_YES=1 ;;
    -h | --help) sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "Argumento desconocido: $arg (usá --dry-run, --yes)" >&2; exit 2 ;;
  esac
done

die() { # qué falló / qué se esperaba / dónde
  echo "ERROR: $1" >&2
  [ -n "${2:-}" ] && echo "  Se esperaba: $2" >&2
  [ -n "${3:-}" ] && echo "  Dónde: $3" >&2
  exit 1
}
step() { printf '\n==> %s\n' "$1"; }
show() { printf '  $ %s\n' "$*"; }

[ -f "$ENV_FILE" ] || die "no existe $ENV_FILE" "copiar scripts/deploy.env.example a scripts/deploy.env y completarlo" "scripts/deploy.sh"
# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a

for v in DEPLOY_HOST DEPLOY_USER DEPLOY_PATH DEPLOY_BRANCH DEPLOY_RESTART_CMD DEPLOY_SERVICE; do
  [ -n "${!v:-}" ] || die "falta $v" "definirlo en $ENV_FILE" "scripts/deploy.env"
done
DEPLOY_HEALTH_URL="${DEPLOY_HEALTH_URL:-}"
DEPLOY_BACKUP_CMD="${DEPLOY_BACKUP_CMD:-}"
DEPLOY_SSH_TTY="${DEPLOY_SSH_TTY:-0}"

TARGET="${DEPLOY_USER}@${DEPLOY_HOST}"
SSH_OPTS=(-o ConnectTimeout=10)
[ "$DEPLOY_SSH_TTY" = "1" ] && SSH_OPTS+=(-t) || SSH_OPTS+=(-o BatchMode=yes)
QPATH="$(printf '%q' "$DEPLOY_PATH")"

remote() { # remote "<comando>" ; en dry-run solo imprime
  if [ "$DRY_RUN" = 1 ]; then show "ssh ${SSH_OPTS[*]} $TARGET '$1'"; return 0; fi
  ssh "${SSH_OPTS[@]}" "$TARGET" "$1"
}

cd "$ROOT"
[ "$DRY_RUN" = 1 ] && echo "*** DRY-RUN: no se hace push ni nada remoto ***"

# ---------------------------------------------------------------- 1. Precondiciones
step "1/7 Precondiciones locales"
problemas=0
warn_or_die() { # en dry-run solo avisa
  if [ "$DRY_RUN" = 1 ]; then echo "  [WARN] $1"; problemas=$((problemas + 1)); else die "$1" "$2" "$3"; fi
}

[ -z "$(git status --porcelain --untracked-files=no)" ] \
  && echo "  [ok] árbol de trabajo limpio (archivos trackeados)" \
  || warn_or_die "el árbol tiene cambios sin commitear" "git status limpio" "git status"

rama="$(git rev-parse --abbrev-ref HEAD)"
[ "$rama" = "$DEPLOY_BRANCH" ] \
  && echo "  [ok] rama $rama" \
  || warn_or_die "estás en '$rama'" "rama $DEPLOY_BRANCH" "git rev-parse --abbrev-ref HEAD"

if [ "$DRY_RUN" = 1 ]; then
  show "git fetch origin $DEPLOY_BRANCH   # omitido en dry-run; se usa la ref origin/$DEPLOY_BRANCH local"
else
  git fetch origin "$DEPLOY_BRANCH" --quiet 2>/dev/null || echo "  [WARN] no pude hacer git fetch (¿sin red?); el resumen puede estar desactualizado"
fi
RANGE="origin/${DEPLOY_BRANCH}..HEAD"

# Archivos sensibles dentro de lo que se va a pushear
sensibles="$(git diff --name-only "$RANGE" 2>/dev/null \
  | grep -E '(^|/)\.env($|\.)|(^|/)deploy\.env$|\.pem$|\.key$|(^|/)id_(rsa|ed25519)|credentials?(\.|$)' \
  | grep -Ev '\.example$' || true)"
if [ -n "$sensibles" ]; then
  warn_or_die "hay archivos de credenciales/.env en lo que se va a pushear:
$sensibles" "ningún .env ni credenciales en $RANGE" "git diff --name-only $RANGE"
else
  echo "  [ok] sin .env ni credenciales en $RANGE"
fi

if [ "$DRY_RUN" = 1 ]; then
  show ".venv/bin/python -m pytest -q          # se ejecuta en el deploy real"
  show ".venv/bin/ruff check .                  # se ejecuta en el deploy real"
else
  .venv/bin/python -m pytest -q 2>&1 | tail -n 5
  [ "${PIPESTATUS[0]}" = 0 ] || die "pytest falló" "suite en verde" ".venv/bin/python -m pytest -q"
  .venv/bin/ruff check . || die "ruff falló" "ruff check sin errores" ".venv/bin/ruff check ."
  echo "  [ok] pytest y ruff en verde"
fi

# ---------------------------------------------------------------- 2. Resumen y confirmación
step "2/7 Commits a desplegar ($RANGE)"
git log "$RANGE" --oneline || true
n="$(git rev-list --count "$RANGE" 2>/dev/null || echo 0)"
echo "  ($n commits)  destino: $TARGET:$DEPLOY_PATH  rama: $DEPLOY_BRANCH"
[ "$n" -gt 0 ] || echo "  Nada para pushear; se continúa solo con el pull/reinicio remoto."

if [ "$DRY_RUN" = 0 ] && [ "$ASSUME_YES" = 0 ]; then
  [ -t 0 ] || die "sin terminal interactiva" "correr en una terminal o usar --yes de forma explícita" "scripts/deploy.sh"
  read -r -p "Escribí 'deploy' para continuar: " resp
  [ "$resp" = "deploy" ] || die "confirmación no recibida" "escribir exactamente: deploy" "prompt"
fi

# ---------------------------------------------------------------- 3. Push
step "3/7 Push"
if [ "$DRY_RUN" = 1 ]; then show "git push origin $DEPLOY_BRANCH"; else
  git push origin "$DEPLOY_BRANCH" || die "git push falló" "push fast-forward a origin/$DEPLOY_BRANCH" "git push origin $DEPLOY_BRANCH"
fi

# ---------------------------------------------------------------- 4. Pull remoto
step "4/7 Server: backup (opcional), fetch y pull --ff-only"
if [ -n "$DEPLOY_BACKUP_CMD" ]; then
  remote "cd $QPATH && $DEPLOY_BACKUP_CMD" || die "el backup falló; no se hizo pull" "backup OK (DEPLOY.md paso 1)" "$TARGET:$DEPLOY_PATH"
else
  echo "  [aviso] DEPLOY_BACKUP_CMD vacío: DEPLOY.md paso 1 recomienda 'sudo bash scripts/backup-estate.sh'"
fi

PREV="(dry-run)"; NEW="(dry-run)"; CAMBIADOS=""
if [ "$DRY_RUN" = 1 ]; then
  show "ssh $TARGET 'cd $DEPLOY_PATH && git rev-parse --short HEAD   # PREV'"
  show "ssh $TARGET 'cd $DEPLOY_PATH && git fetch && git pull --ff-only origin $DEPLOY_BRANCH'"
  show "ssh $TARGET 'cd $DEPLOY_PATH && git rev-parse --short HEAD   # hash nuevo'"
else
  PREV="$(remote "cd $QPATH && git rev-parse --short HEAD")" \
    || die "no pude leer el HEAD remoto" "repo git en $DEPLOY_PATH accesible por ssh" "$TARGET:$DEPLOY_PATH"
  remote "cd $QPATH && git fetch origin && git pull --ff-only origin $(printf '%q' "$DEPLOY_BRANCH")" \
    || die "git pull --ff-only falló; NO se reinició nada (el server sigue en $PREV)" \
           "fast-forward limpio; si el server tiene commits/cambios locales o la rama divergió, resolverlo a mano" \
           "$TARGET:$DEPLOY_PATH"
  NEW="$(remote "cd $QPATH && git rev-parse --short HEAD")"
  CAMBIADOS="$(remote "cd $QPATH && git diff --name-only $PREV..$NEW" || true)"
  echo "  server: $PREV -> $NEW"
fi

# Avisos según archivos cambiados (no se hace rebuild automático de frontend/mobile)
if echo "$CAMBIADOS" | grep -qE '^(frontend|mobile)/'; then
  echo "  [AVISO] cambió frontend/ o mobile/: hay que reconstruir a mano (DEPLOY.md paso 4: cd frontend && npm ci && npm run build + restart del frontend). El script NO lo hace."
fi
if echo "$CAMBIADOS" | grep -qE '^requirements\.txt$'; then
  echo "  requirements.txt cambió: pip install (DEPLOY.md paso 3)"
  remote "cd $QPATH && .venv/bin/pip install -r requirements.txt" \
    || die "pip install falló; no se reinició" "dependencias instaladas" "$TARGET:$DEPLOY_PATH (.venv)"
elif [ "$DRY_RUN" = 1 ]; then
  show "ssh $TARGET 'cd $DEPLOY_PATH && .venv/bin/pip install -r requirements.txt'   # solo si cambió requirements.txt"
fi
echo "  Migraciones: DEPLOY.md las resuelve al reiniciar (migrate_schema aditivo + alembic stamp/upgrade); no se corre nada aparte."

# ---------------------------------------------------------------- 5. Reinicio
step "5/7 Reinicio"
if [ "$DRY_RUN" = 1 ]; then remote "cd $DEPLOY_PATH && $DEPLOY_RESTART_CMD"; else
  remote "cd $QPATH && $DEPLOY_RESTART_CMD" || die "el reinicio falló (código de salida distinto de 0).
  Si fue 'sudo: a terminal is required' / 'a password is required', son dos salidas:
    (a) sudoers NOPASSWD acotado a ese comando (visudo en el server):
        $DEPLOY_USER ALL=(root) NOPASSWD: $(echo "$DEPLOY_RESTART_CMD" | sed 's/^sudo //')
    (b) correr con terminal: DEPLOY_SSH_TTY=1 ./scripts/deploy.sh
  El código nuevo YA está en el server ($PREV -> $NEW) pero el servicio no se reinició." \
    "comando ejecutado sin pedir contraseña" "$TARGET: $DEPLOY_RESTART_CMD"
fi

# ---------------------------------------------------------------- 6. Verificación
step "6/7 Verificación"
resultado=0
if [ "$DRY_RUN" = 1 ]; then
  [ -n "$DEPLOY_HEALTH_URL" ] && show "curl -fsS --max-time 5 $DEPLOY_HEALTH_URL   # hasta 6 intentos, 5s entre cada uno"
  show "ssh $TARGET 'systemctl is-active $DEPLOY_SERVICE'"
  show "ssh $TARGET 'journalctl -u $DEPLOY_SERVICE -n 30 --no-pager'"
else
  if [ -n "$DEPLOY_HEALTH_URL" ]; then
    ok=0
    for i in 1 2 3 4 5 6; do
      if curl -fsS --max-time 5 "$DEPLOY_HEALTH_URL" >/dev/null; then ok=1; break; fi
      echo "  health intento $i/6 sin respuesta; reintento en 5s"; sleep 5
    done
    [ "$ok" = 1 ] && echo "  [PASS] health $DEPLOY_HEALTH_URL" || { echo "  [FAIL] health $DEPLOY_HEALTH_URL no respondió"; resultado=1; }
  else
    echo "  [aviso] sin DEPLOY_HEALTH_URL. Propuesta: https://ibot.ecolan.com/health (main.py:200; nginx 'location /health')."
  fi
  activo="$(remote "systemctl is-active $(printf '%q' "$DEPLOY_SERVICE")" || true)"
  [ "$activo" = "active" ] && echo "  [PASS] systemctl is-active $DEPLOY_SERVICE = active" \
    || { echo "  [FAIL] systemctl is-active $DEPLOY_SERVICE = '${activo:-?}'"; resultado=1; }
  echo "  --- últimas 30 líneas de journalctl -u $DEPLOY_SERVICE ---"
  remote "journalctl -u $(printf '%q' "$DEPLOY_SERVICE") -n 30 --no-pager 2>/dev/null || sudo -n journalctl -u $(printf '%q' "$DEPLOY_SERVICE") -n 30 --no-pager" \
    || echo "  [aviso] no pude leer el journal (permisos); revisalo en el server"
fi

# ---------------------------------------------------------------- 7. Rollback
step "7/7 Resumen y rollback"
echo "  PREV : $PREV"
echo "  NUEVO: $NEW"
echo "  Rollback manual (sin automatismos; deja el server en HEAD detached):"
echo "    ssh ${SSH_OPTS[*]} $TARGET 'cd $DEPLOY_PATH && git checkout $PREV && $DEPLOY_RESTART_CMD'"
echo "  Para volver a la rama después: ssh $TARGET 'cd $DEPLOY_PATH && git checkout $DEPLOY_BRANCH'"
if [ "$DRY_RUN" = 1 ]; then echo "  (dry-run: $problemas advertencia(s) de precondiciones; en un deploy real abortarían)"; fi
if [ "$resultado" != 0 ]; then echo "  RESULTADO: la verificación FALLÓ; considerá el rollback."; exit 1; fi
echo "  RESULTADO: OK"
