"""Evaluación masiva N1: replay de casos Botmaker contra el endpoint del bot.

Reemplaza el ciclo de capturas manuales. Tras cada ajuste de KB/playbook:

    .venv/bin/python -m qa_bot.eval_masivo
    .venv/bin/python -m qa_bot.eval_masivo --limit 50 --categoria internet
    .venv/bin/python -m qa_bot.eval_masivo --solo-extraer
    .venv/bin/python -m qa_bot.eval_masivo --corpus data/eval-botmaker/corpus.json

Por defecto pega a la API local (TestClient), no a producción.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qa_bot.analyzer import analizar_turno  # noqa: E402
from qa_bot.cliente_hogareno import (  # noqa: E402
    _enviar,
    _reset_hilo_n1,
    _sesion_portal,
    _ticket_en_payload,
)
from qa_bot.corpus_botmaker import (  # noqa: E402
    DEFAULT_CORPUS,
    DEFAULT_INPUT,
    FIXTURE_MUESTRA,
    CasoBotmaker,
    cargar_corpus,
    extraer_desde_dir,
    extraer_desde_paths,
    guardar_corpus,
)

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
_EVAL_DB = ROOT / "data" / "eval_estate.db"


def _aislar_entorno_eval() -> None:
    """Antes de importar app: load_dotenv no pisa vars ya definidas.

    Un `pop` de BILLTRACK_DATABASE_URL no alcanza: dotenv la rellena desde
    `.env` y el lookup real (o settings en Postgres) tumba el OTP. El eval
    usa SQLite propio + mock de padrón, igual que pytest.
    """
    _EVAL_DB.parent.mkdir(parents=True, exist_ok=True)
    os.environ["DATABASE_URL"] = f"sqlite:///{_EVAL_DB}"
    os.environ["APP_ENV"] = "development"
    os.environ["DISABLE_DEMO_USERS"] = "false"
    os.environ["BILLTRACK_DATABASE_URL"] = ""
    os.environ["BILLTRACK_LOOKUP_READY"] = "0"
    os.environ["BILLTRACK_ENABLED"] = "false"


@dataclass
class ResultadoCaso:
    caso_id: str
    categoria: str
    apertura: str
    turnos: list[dict] = field(default_factory=list)
    ticket: bool = False
    ticket_id: str = ""
    estado_final: str = ""
    intencion_final: str = ""
    lectura_forzada_e1: bool = False
    bucle: bool = False
    fallas: list[str] = field(default_factory=list)
    score_n1: float = 0.0
    latency_ms_total: int = 0
    error: str = ""


def _jsonable(obj: Any) -> Any:
    if is_dataclass(obj):
        return {k: _jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, list):
        return [_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    return obj


def _marcar_lectura(payload: dict[str, Any], bot: str) -> bool:
    if payload.get("lectura_forzada_e1"):
        return True
    low = (bot or "").lower()
    return any(
        k in low
        for k in (
            "revisé tu ont",
            "revise tu ont",
            "revisé la antena",
            "revise la antena",
            "revisé tu ont en la central",
            "potencia óptica",
            "potencia optica",
        )
    )


def replay_caso(
    client: Any,
    caso: CasoBotmaker,
    *,
    dni: str = "30111222",
    max_turnos: int = 4,
    token: str | None = None,
) -> ResultadoCaso:
    from app.domain.flujos_abonado import PLAYBOOKS

    try:
        with (
            patch("app.api.v1.portal.resolve_canal_usar_llama", return_value=False),
            patch("app.services.canal_abonado.playbooks_as_pasos", return_value=PLAYBOOKS),
        ):
            if not token:
                token, _conv_id = _sesion_portal(client, dni)
            mensajes = (caso.turnos_usuario or [caso.apertura])[:max_turnos]
            prev: list[str] = []
            analisis = []
            turnos_out: list[dict] = []
            ticket = ""
            lectura = False
            estado = ""
            intent = ""
            t0 = time.perf_counter()
            for texto in mensajes:
                if not (texto or "").strip():
                    continue
                payload = _enviar(client, token, texto)
                bot = str(payload.get("respuesta") or payload.get("reply") or "").strip()
                ticket = ticket or _ticket_en_payload(payload, bot)
                lectura = lectura or _marcar_lectura(payload, bot)
                estado = str(payload.get("estado") or estado)
                intent = str(payload.get("intencion") or intent)
                a = analizar_turno(
                    texto,
                    bot,
                    espera_autodiagnostico=caso.categoria == "internet",
                    no_debe_ticket_prematuro=True,
                    ticket_aceptable=False,
                    respuestas_previas=prev,
                )
                analisis.append(a)
                turnos_out.append(
                    {
                        "usuario": texto,
                        "bot": bot,
                        "estado": estado,
                        "intencion": intent,
                        "ticket_id": ticket,
                        "lectura_forzada_e1": bool(payload.get("lectura_forzada_e1")),
                    }
                )
                if bot:
                    prev.append(bot)
                if ticket or estado in ("espera_agente", "con_agente", "cerrado"):
                    break
            ms = int((time.perf_counter() - t0) * 1000)
            scores = [t.score_n1 for t in analisis] or [0.0]
            fallas = []
            for i, t in enumerate(analisis, 1):
                for h in t.hallazgos:
                    fallas.append(f"T{i}: {h}")
            return ResultadoCaso(
                caso_id=caso.id,
                categoria=caso.categoria,
                apertura=caso.apertura,
                turnos=turnos_out,
                ticket=bool(ticket),
                ticket_id=ticket,
                estado_final=estado,
                intencion_final=intent,
                lectura_forzada_e1=lectura,
                bucle=any(t.posible_bucle for t in analisis),
                fallas=fallas,
                score_n1=round(sum(scores) / len(scores), 3),
                latency_ms_total=ms,
            )
    except Exception as exc:  # noqa: BLE001
        return ResultadoCaso(
            caso_id=caso.id,
            categoria=caso.categoria,
            apertura=caso.apertura,
            error=str(exc)[:300],
            fallas=[f"ERROR: {exc}"],
        )


def replay_casos(
    casos: list[CasoBotmaker],
    *,
    client: Any | None = None,
    dni: str = "30111222",
    max_turnos: int = 4,
) -> list[ResultadoCaso]:
    if client is not None:
        return _replay_con_cliente(client, casos, dni=dni, max_turnos=max_turnos)
    _aislar_entorno_eval()
    from fastapi.testclient import TestClient

    from main import app

    # Context manager: dispara lifespan (schema + seed). Sin `with`, SQLite nace vacío.
    with TestClient(app) as owned:
        return _replay_con_cliente(owned, casos, dni=dni, max_turnos=max_turnos)


def _replay_con_cliente(
    client: Any,
    casos: list[CasoBotmaker],
    *,
    dni: str,
    max_turnos: int,
) -> list[ResultadoCaso]:
    token, conv_id = _sesion_portal(client, dni)
    results: list[ResultadoCaso] = []
    for i, caso in enumerate(casos, 1):
        print(
            f"[{i}/{len(casos)}] {caso.id} {caso.categoria} — {caso.apertura[:60]!r}…",
            flush=True,
        )
        _reset_hilo_n1(conv_id)
        r = replay_caso(client, caso, dni=dni, max_turnos=max_turnos, token=token)
        flag = "ERR" if r.error else ("N2" if r.ticket else "OK")
        print(
            f"  {flag} score={r.score_n1} bucle={r.bucle} "
            f"e1_lectura={r.lectura_forzada_e1} fallas={len(r.fallas)}",
            flush=True,
        )
        results.append(r)
    return results


def resumen(results: list[ResultadoCaso]) -> dict[str, Any]:
    n = len(results) or 1
    return {
        "n": len(results),
        "con_error": sum(1 for r in results if r.error),
        "tickets": sum(1 for r in results if r.ticket),
        "bucles": sum(1 for r in results if r.bucle),
        "lectura_forzada_e1": sum(1 for r in results if r.lectura_forzada_e1),
        "score_n1_promedio": round(sum(r.score_n1 for r in results) / n, 3),
        "con_fallas": sum(1 for r in results if r.fallas),
    }


def _reporte_md(results: list[ResultadoCaso], dest: Path) -> None:
    s = resumen(results)
    lines = [
        "# Evaluación masiva N1 (Botmaker → endpoint)",
        "",
        f"Generado: {datetime.now(UTC).isoformat()}",
        "",
        f"- Casos: **{s['n']}**",
        f"- Score N1 promedio: **{s['score_n1_promedio']}**",
        f"- Bucles: **{s['bucles']}**",
        f"- Tickets N2: **{s['tickets']}**",
        f"- Lectura forzada E1 (OLT/WIS): **{s['lectura_forzada_e1']}**",
        f"- Con fallas de scoring: **{s['con_fallas']}**",
        f"- Errores de ejecución: **{s['con_error']}**",
        "",
        "## Casos con fallas o bucle",
        "",
        "| ID | Cat | Score | Bucle | N2 | E1 lectura | Fallas |",
        "|----|-----|-------|-------|----|------------|--------|",
    ]
    fallidos = [r for r in results if r.fallas or r.bucle or r.error]
    if not fallidos:
        lines.append("| — | — | — | — | — | — | ninguno |")
    else:
        for r in fallidos[:80]:
            fallas = "; ".join(r.fallas)[:120].replace("|", "/")
            lines.append(
                f"| `{r.caso_id}` | {r.categoria} | {r.score_n1} | "
                f"{r.bucle} | {r.ticket} | {r.lectura_forzada_e1} | {fallas} |"
            )
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluación masiva del bot N1 con casos Botmaker"
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT,
        help="Dump Botmaker (sessions-*.raw.json)",
    )
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--solo-extraer", action="store_true")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--max-turnos", type=int, default=4)
    parser.add_argument(
        "--categoria",
        default="internet",
        help="internet | facturacion | movil | otro | all",
    )
    parser.add_argument("--max-files", type=int, default=0)
    parser.add_argument("--dni", default="30111222")
    parser.add_argument(
        "--input-file",
        type=Path,
        default=None,
        help="Un JSON Botmaker (items/sessions). Si no hay dump, usa el fixture de tests.",
    )
    parser.add_argument(
        "--reextraer",
        action="store_true",
        help="Ignora corpus.json y vuelve a leer el dump / --input-file.",
    )
    args = parser.parse_args(argv)

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    cat = None if args.categoria in ("", "all") else args.categoria

    if (
        args.corpus.is_file()
        and not args.solo_extraer
        and not args.reextraer
        and args.input_file is None
    ):
        print(f"Corpus: {args.corpus}", flush=True)
        casos = cargar_corpus(args.corpus)
        if cat:
            casos = [c for c in casos if c.categoria == cat]
        if args.limit:
            casos = casos[: args.limit]
    else:
        input_file = args.input_file
        if input_file is not None:
            if not input_file.is_file():
                print(f"ERROR: no existe {input_file}", file=sys.stderr)
                return 1
            print(f"Extrayendo desde archivo {input_file}…", flush=True)
            casos = extraer_desde_paths(
                [input_file],
                max_turnos=args.max_turnos,
                categoria=cat,
                limit=args.limit,
            )
        elif args.input_dir.is_dir():
            print(f"Extrayendo desde {args.input_dir}…", flush=True)
            casos = extraer_desde_dir(
                args.input_dir,
                max_turnos=args.max_turnos,
                categoria=cat,
                limit=args.limit,
                max_files=args.max_files,
            )
        elif FIXTURE_MUESTRA.is_file():
            print(
                f"WARN: no está el dump en {args.input_dir}; "
                f"uso fixture {FIXTURE_MUESTRA}",
                flush=True,
            )
            casos = extraer_desde_paths(
                [FIXTURE_MUESTRA],
                max_turnos=args.max_turnos,
                categoria=cat,
                limit=args.limit,
            )
        else:
            print(
                f"ERROR: no está el dump Botmaker en {args.input_dir}\n"
                "Pasá --input-dir / --input-file.",
                file=sys.stderr,
            )
            return 1
        guardar_corpus(casos, args.corpus)
        print(f"Corpus: {len(casos)} casos → {args.corpus}", flush=True)

    if args.solo_extraer:
        return 0 if casos else 2

    if not casos:
        print("ERROR: corpus vacío", file=sys.stderr)
        return 2

    results = replay_casos(casos, dni=args.dni, max_turnos=args.max_turnos)
    s = resumen(results)
    out_json = ARTIFACTS / "eval_botmaker.json"
    out_md = ARTIFACTS / "eval_botmaker.md"
    payload = {
        "generado_at": datetime.now(UTC).isoformat(),
        "resumen": s,
        "casos": _jsonable(results),
    }
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _reporte_md(results, out_md)
    print(
        f"\nResumen: n={s['n']} score={s['score_n1_promedio']} "
        f"bucles={s['bucles']} n2={s['tickets']} e1_lectura={s['lectura_forzada_e1']}",
        flush=True,
    )
    print(f"JSON: {out_json}", flush=True)
    print(f"MD:   {out_md}", flush=True)
    if s["con_error"] and s["con_error"] == s["n"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
