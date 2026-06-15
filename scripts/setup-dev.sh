#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"

echo "==> Python"
"$PYTHON_BIN" --version

if ! "$PYTHON_BIN" -m venv "$VENV_DIR" >/tmp/imowi-venv.log 2>&1; then
  cat /tmp/imowi-venv.log
  echo
  echo "No se pudo crear el entorno virtual."
  echo "En Ubuntu/Debian instalá primero:"
  echo "  sudo apt update && sudo apt install -y python3.14-venv"
  echo
  echo "Luego repetí:"
  echo "  bash scripts/setup-dev.sh"
  exit 1
fi

echo "==> Instalando dependencias"
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -r requirements-dev.txt

if [[ ! -f .env && -f .env.example ]]; then
  cp .env.example .env
  echo "==> .env creado desde .env.example"
fi

echo
echo "Entorno listo."
echo "Ejecutar:"
echo "  ./run.sh"
echo
echo "Validar:"
echo "  .venv/bin/python -m pytest"
echo "  .venv/bin/ruff check ."
