"""Entrenamiento exhaustivo N1 — reemplazo del barrido manual de ~2 semanas.

Corre el lote hogareño del guion (P01–P28) + corporativo (C01–C04) contra la
API local (TestClient). Métrica de corte: **0 N2 evitables**.

No sustituye la prueba con cliente real (typos, síntomas confusos, ruido).
Sí cubre de forma repetible el catálogo de procedimientos curados.

Uso:

    .venv/bin/python -m qa_bot.entrenamiento_exhaustivo
    .venv/bin/python -m qa_bot.entrenamiento_exhaustivo --solo hogar
    .venv/bin/python -m qa_bot.entrenamiento_exhaustivo --lote movil
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"


def main(argv: list[str] | None = None) -> int:
    import os

    # Antes de importar app: sin BillTrack (credenciales locales suelen fallar y desvían N1).
    os.environ.pop("BILLTRACK_DATABASE_URL", None)

    from qa_bot.cliente_corporativo import run_loop as run_corp
    from qa_bot.cliente_corporativo import resumen as resumen_corp
    from qa_bot.cliente_hogareno import run_loop as run_hogar
    from qa_bot.cliente_hogareno import resumen as resumen_hogar
    from qa_bot.lotes import LOTES

    parser = argparse.ArgumentParser(
        description="Entrenamiento exhaustivo N1 (hogareño + corporativo)"
    )
    parser.add_argument(
        "--lote",
        default="exhaustivo",
        choices=sorted(LOTES.keys()),
        help="Lote hogareño (default: exhaustivo = P01–P28)",
    )
    parser.add_argument(
        "--solo",
        default="ambos",
        choices=["ambos", "hogar", "corp"],
        help="Qué suites correr",
    )
    args = parser.parse_args(argv)

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()

    hogar_payload: dict[str, Any] = {}
    corp_payload: dict[str, Any] = {}

    if args.solo in ("ambos", "hogar"):
        print(f"\n=== HOGAR lote={args.lote} ({len(LOTES[args.lote])} personas) ===", flush=True)
        hogar_results = run_hogar(ids=LOTES[args.lote])
        hogar_payload = resumen_hogar(hogar_results)

    if args.solo in ("ambos", "corp"):
        print("\n=== CORPORATIVO C01–C04 ===", flush=True)
        corp_results = run_corp()
        corp_payload = resumen_corp(corp_results)

    n2_ev = int(hogar_payload.get("n2_evitables", 0)) + int(
        corp_payload.get("n2_evitables", 0)
    )
    n2_leg = int(hogar_payload.get("n2_legitimos", 0)) + int(
        corp_payload.get("n2_legitimos", 0)
    )
    ok = int(hogar_payload.get("ok", 0)) + int(corp_payload.get("ok", 0))
    total = int(hogar_payload.get("personas", 0)) + int(corp_payload.get("personas", 0))

    report = {
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "lote_hogar": args.lote if args.solo in ("ambos", "hogar") else None,
        "metricas": {
            "personas": total,
            "ok": ok,
            "n2_evitables": n2_ev,
            "n2_legitimos": n2_leg,
            "tasa_ok": round(ok / total, 3) if total else 0.0,
        },
        "hogar": hogar_payload or None,
        "corporativo": corp_payload or None,
        "nota": (
            "0 N2 evitables = corte del entrenamiento automatizado. "
            "Clientes reales (typos, síntomas ambiguos) siguen siendo la prueba final."
        ),
    }

    out = ARTIFACTS / "entrenamiento_exhaustivo.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nJSON: {out}", flush=True)
    print(
        f"TOTAL ok={ok}/{total} n2_evitables={n2_ev} n2_legitimos={n2_leg}",
        flush=True,
    )
    if n2_ev:
        print("FAIL: hay N2 evitables — revisar transcripts en el JSON.", flush=True)
        return 2
    print("PASS: 0 N2 evitables en el lote automatizado.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
