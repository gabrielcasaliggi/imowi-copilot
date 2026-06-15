#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

UVICORN="$ROOT/.venv/bin/uvicorn"

if [[ ! -x "$UVICORN" ]]; then
  echo "Error: no se encontró $UVICORN"
  echo "Recreá el entorno virtual (requiere python3.14-venv):"
  echo "  sudo apt install python3.14-venv python3-full"
  echo "  rm -rf .venv && python3 -m venv .venv"
  echo "  .venv/bin/pip install -r requirements.txt"
  exit 1
fi

exec "$UVICORN" main:app --reload --host 0.0.0.0 --port "${PORT:-8000}"
