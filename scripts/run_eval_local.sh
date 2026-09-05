#!/usr/bin/env bash
# Evaluación local N1: tests del corte E1 + replay de aperturas Botmaker.
# No pegar a producción. El dump queda en el PC (PII).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${ROOT}/.venv/bin/python"
RUFF="${ROOT}/.venv/bin/ruff"
DUMP="${HOME}/Descargas/sesiones-historicas-2025_2026-06"

echo "=== ruff ==="
"$RUFF" check \
  app/services/turno_e1.py \
  app/services/canal_diagnostico_ia.py \
  app/domain/flujos_abonado.py \
  app/services/canal_abonado.py \
  qa_bot/eval_masivo.py \
  qa_bot/corpus_botmaker.py \
  qa_bot/cliente_hogareno.py \
  tests/test_turno_e1.py \
  tests/test_lectura_forzada_e1.py \
  tests/test_corpus_botmaker.py \
  tests/test_triaje_sin_bucle.py

echo "=== pytest E1 / corpus / triaje ==="
"$PY" -m pytest \
  tests/test_turno_e1.py \
  tests/test_lectura_forzada_e1.py \
  tests/test_corpus_botmaker.py \
  tests/test_triaje_sin_bucle.py \
  -q --tb=short

echo "=== eval masivo Botmaker (30 aperturas, 1 archivo) ==="
# Aislar padrón real: load_dotenv no pisa estas vars.
export APP_ENV=development
export BILLTRACK_DATABASE_URL=
export BILLTRACK_LOOKUP_READY=0
export BILLTRACK_ENABLED=false
if [[ -d "$DUMP" ]]; then
  "$PY" -m qa_bot.eval_masivo \
    --input-dir "$DUMP" \
    --max-files 1 \
    --limit 30 \
    --categoria internet \
    --max-turnos 3 \
    --reextraer
else
  echo "WARN: no está $DUMP — replay con fixture de tests"
  "$PY" -m qa_bot.eval_masivo \
    --input-file tests/fixtures/botmaker_sesiones_muestra.json \
    --categoria all \
    --limit 10 \
    --max-turnos 3
fi

echo
echo "Listo. Reporte: qa_bot/artifacts/eval_botmaker.md"
