"""Entrypoint QA Automation — portal Ecolan modo Invitado."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qa_bot.analyzer import AnalisisEscenario  # noqa: E402
from qa_bot.report import generar_reporte  # noqa: E402
from qa_bot.runner_api import run_matriz_api  # noqa: E402
from qa_bot.runner_playwright import run_matriz_playwright  # noqa: E402

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
PORTAL = "https://ibot.ecolan.com/portal"
API_BASE = "https://ibot.ecolan.com"


def _to_jsonable(obj):
    if is_dataclass(obj):
        return {k: _to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, list):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    return obj


def _merge_prefer_api(
    api: list[AnalisisEscenario], pw: list[AnalisisEscenario]
) -> list[AnalisisEscenario]:
    """Usa API como fuente principal; anexa escenarios solo-Playwright si hubiera."""
    by_id = {r.escenario_id: r for r in api}
    for r in pw:
        if r.escenario_id not in by_id:
            by_id[r.escenario_id] = r
    # Orden estable por id
    return [by_id[k] for k in sorted(by_id.keys())]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="QA N1 bot portal Ecolan")
    parser.add_argument(
        "--mode",
        choices=("api", "playwright", "both"),
        default="both",
        help="api=matriz completa vía portal API; playwright=UI invitado; both=API+smoke UI",
    )
    parser.add_argument(
        "--scenarios",
        default="",
        help="IDs separados por coma (ej. E01,E08). Vacío = todos.",
    )
    parser.add_argument("--base-url", default=API_BASE)
    parser.add_argument(
        "--report",
        default=str(ROOT / "reporte_qa_bot.md"),
        help="Ruta del reporte Markdown",
    )
    parser.add_argument("--headed", action="store_true", help="Playwright con UI visible")
    args = parser.parse_args(argv)

    ids = [s.strip() for s in args.scenarios.split(",") if s.strip()] or None
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    api_results: list[AnalisisEscenario] = []
    pw_results: list[AnalisisEscenario] = []

    if args.mode in ("api", "both"):
        print("=== Matriz API (producción) ===", flush=True)
        api_results = run_matriz_api(base_url=args.base_url, scenario_ids=ids)

    if args.mode == "playwright":
        print("=== Matriz Playwright UI ===", flush=True)
        pw_results = run_matriz_playwright(scenario_ids=ids, headless=not args.headed)
    elif args.mode == "both":
        # Smoke UI: login + 2 escenarios representativos (o los pedidos)
        smoke_ids = ids or ["E01", "E08", "E13"]
        print(f"=== Smoke Playwright UI ({', '.join(smoke_ids)}) ===", flush=True)
        pw_results = run_matriz_playwright(scenario_ids=smoke_ids, headless=not args.headed)

    if args.mode == "api":
        final = api_results
        metodo = "Portal API (`/api/v1/portal/session` + `/messages`) — mismo backend que UI"
    elif args.mode == "playwright":
        final = pw_results
        metodo = "Playwright UI — login Invitado + chat en https://ibot.ecolan.com/portal"
    else:
        final = _merge_prefer_api(api_results, pw_results)
        metodo = (
            "Matriz completa vía Portal API + smoke Playwright (Invitado) en escenarios "
            + (", ".join(ids or ["E01", "E08", "E13"]))
        )

    # Persistir JSON
    out_json = ARTIFACTS / "resultados_qa.json"
    out_json.write_text(
        json.dumps(_to_jsonable(final), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if api_results:
        (ARTIFACTS / "resultados_api.json").write_text(
            json.dumps(_to_jsonable(api_results), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    if pw_results:
        (ARTIFACTS / "resultados_playwright.json").write_text(
            json.dumps(_to_jsonable(pw_results), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    report_path = Path(args.report)
    generar_reporte(final, portal_url=PORTAL, metodo=metodo, out_path=report_path)
    print(f"\nReporte: {report_path}", flush=True)
    print(f"JSON:    {out_json}", flush=True)

    # Exit code: fallar si resolutividad < 50% o muchos prematuros
    total = len(final) or 1
    resol = sum(1 for r in final if r.resolutivo_autonomo) / total
    prem = sum(1 for r in final if r.ticket_prematuro) / total
    if resol < 0.5 or prem > 0.4:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
