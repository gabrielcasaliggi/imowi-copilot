#!/usr/bin/env python3
"""Prueba Sentry: envía un mensaje de verificación.

Uso (en el server):
  cd /opt/operations-hub
  sudo -u ops .venv/bin/python scripts/sentry-ping.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Cargar .env mínimo
env_path = ROOT / ".env"
if env_path.is_file():
    for raw in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        if key and key not in os.environ:
            os.environ[key] = val

from app.observability import init_sentry, sentry_activo  # noqa: E402


def main() -> int:
    if not (os.getenv("SENTRY_DSN") or "").strip():
        print("SENTRY_DSN vacío — creá un proyecto en sentry.io y pegá el DSN en .env")
        print("Alternativa: SENTRY_RISK_ACCEPTED=true si aceptás operar sin Sentry")
        return 1
    if not init_sentry() and not sentry_activo():
        print("No se pudo inicializar Sentry (¿falta sentry-sdk?)")
        return 1
    import sentry_sdk

    event_id = sentry_sdk.capture_message(
        "ops-hub sentry-ping OK",
        level="info",
    )
    sentry_sdk.flush(timeout=5)
    print(f"OK — evento enviado (id={event_id}). Revisá el proyecto Sentry.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
