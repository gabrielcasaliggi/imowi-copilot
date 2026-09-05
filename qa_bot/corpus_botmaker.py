"""Corpus de evaluación desde exports Botmaker (sesiones reales, anonimizadas).

No versiona transcripts. Lee el dump local (gitignored) y emite un JSON de casos
reproducibles: primeros turnos de usuario, sin PII.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = Path.home() / "Descargas/sesiones-historicas-2025_2026-06"
DEFAULT_CORPUS = ROOT / "data" / "eval-botmaker" / "corpus.json"

_MENU_SOLO = re.compile(r"^[\d\s.,)(\-]+$")
_RUIDO_TURNO = frozenset(
    {
        "hola",
        "holaa",
        "holaaa",
        "buenas",
        "buen dia",
        "buen día",
        "buenos dias",
        "buenos días",
        "buenas tardes",
        "buenas noches",
        "ok",
        "okey",
        "okay",
        "si",
        "sí",
        "no",
        "gracias",
        "dale",
        "listo",
        "vale",
        "?",
        "??",
        ".",
        "menu",
        "menú",
    }
)
_KEYWORDS_INTERNET = (
    "internet",
    "wifi",
    "wi-fi",
    "fibra",
    "antena",
    "adsl",
    "router",
    "modem",
    "módem",
    "ont",
    "onu",
    "sin servicio",
    "no anda",
    "no me anda",
    "lento",
    "corte",
    "señal",
    "senal",
)
_KEYWORDS_FACTURA = (
    "factura",
    "pago",
    "deuda",
    "saldo",
    "cuánto debo",
    "cuanto debo",
    "qr",
    "mora",
)
_KEYWORDS_MOVIL = ("imowi", "móvil", "movil", "chip", "abono", "pack", "datos móviles")


def _minero():
    path = ROOT / "scripts" / "minar_comprension_botmaker.py"
    spec = importlib.util.spec_from_file_location("minar_comprension_botmaker", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"No se pudo cargar {path}")
    mod = importlib.util.module_from_spec(spec)
    # Python 3.14 dataclasses exige el módulo en sys.modules antes de exec.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_MINERO = None


def _m():
    global _MINERO
    if _MINERO is None:
        _MINERO = _minero()
    return _MINERO


@dataclass
class CasoBotmaker:
    id: str
    categoria: str
    apertura: str
    turnos_usuario: list[str]
    n_user: int
    fuente: str = ""
    tags: list[str] = field(default_factory=list)


def clasificar_categoria(textos: Iterable[str]) -> str:
    blob = " ".join(textos).lower()
    if any(k in blob for k in _KEYWORDS_FACTURA) and not any(
        k in blob for k in ("internet", "wifi", "fibra", "antena")
    ):
        return "facturacion"
    if any(k in blob for k in _KEYWORDS_MOVIL) and "internet" not in blob:
        return "movil"
    if any(k in blob for k in _KEYWORDS_INTERNET):
        return "internet"
    if any(k in blob for k in _KEYWORDS_FACTURA):
        return "facturacion"
    return "otro"


def _es_menu_botmaker(texto: str) -> bool:
    t = (texto or "").strip()
    if not t:
        return True
    if _MENU_SOLO.match(t):
        return True
    if t.lower() in ("menu", "menú", "hola", "buenas", "."):
        return True
    return False


def _es_ruido_turno(texto: str) -> bool:
    """Saludos y réplicas cortas: no sirven como apertura de eval."""
    if _es_menu_botmaker(texto):
        return True
    t = (texto or "").strip().lower()
    t = t.strip("!.¡¿ ")
    if t in _RUIDO_TURNO:
        return True
    return len(t) < 6


def _id_caso(apertura: str, fuente: str, idx: int) -> str:
    raw = f"{fuente}|{idx}|{apertura[:80]}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]
    return f"BM-{digest}"


def extraer_caso_sesion(
    session: dict[str, Any],
    *,
    fuente: str = "",
    max_turnos: int = 4,
    idx: int = 0,
) -> CasoBotmaker | None:
    minero = _m()
    turnos: list[str] = []
    cupo = max(max_turnos, 1) + 8
    for msg in session.get("messages") or []:
        if (msg.get("from") or "") != "user":
            continue
        texto = minero._extraer_texto_mensaje(msg)
        if not texto:
            continue
        anon = minero._anonimizar_texto(texto)
        if _es_ruido_turno(anon):
            continue
        if len(anon) > 400:
            anon = anon[:400].rstrip()
        turnos.append(anon)
        if len(turnos) >= cupo:
            break
    if not turnos:
        return None
    cat = clasificar_categoria(turnos)
    if cat == "internet":
        start = next(
            (
                i
                for i, t in enumerate(turnos)
                if any(k in t.lower() for k in _KEYWORDS_INTERNET)
            ),
            0,
        )
        turnos = turnos[start:]
    turnos = turnos[:max_turnos]
    return CasoBotmaker(
        id=_id_caso(turnos[0], fuente, idx),
        categoria=cat,
        apertura=turnos[0],
        turnos_usuario=turnos,
        n_user=len(turnos),
        fuente=fuente,
        tags=[cat],
    )


def extraer_casos(
    sesiones: Iterable[dict[str, Any]],
    *,
    fuente: str = "",
    max_turnos: int = 4,
    categoria: str | None = None,
    dedup: bool = True,
    limit: int = 0,
) -> list[CasoBotmaker]:
    seen: set[str] = set()
    out: list[CasoBotmaker] = []
    for i, session in enumerate(sesiones):
        caso = extraer_caso_sesion(
            session, fuente=fuente, max_turnos=max_turnos, idx=i
        )
        if caso is None:
            continue
        if categoria and caso.categoria != categoria:
            continue
        clave = minero_norm(caso.apertura)
        if dedup and clave in seen:
            continue
        seen.add(clave)
        out.append(caso)
        if limit and len(out) >= limit:
            break
    return out


def minero_norm(texto: str) -> str:
    return _m()._normalizar_frase(texto)


def iter_sesiones_archivo(path: Path) -> Iterable[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        items = data.get("items") or data.get("sessions") or []
        if isinstance(items, list):
            yield from (s for s in items if isinstance(s, dict))
            return
    if isinstance(data, list):
        yield from (s for s in data if isinstance(s, dict))


def extraer_desde_paths(
    paths: Iterable[Path],
    *,
    max_turnos: int = 4,
    categoria: str | None = "internet",
    limit: int = 200,
) -> list[CasoBotmaker]:
    casos: list[CasoBotmaker] = []
    seen: set[str] = set()
    for path in paths:
        if not path.is_file():
            continue
        for i, session in enumerate(iter_sesiones_archivo(path)):
            caso = extraer_caso_sesion(
                session, fuente=path.name, max_turnos=max_turnos, idx=i
            )
            if caso is None:
                continue
            if categoria and caso.categoria != categoria:
                continue
            clave = minero_norm(caso.apertura)
            if clave in seen:
                continue
            seen.add(clave)
            casos.append(caso)
            if limit and len(casos) >= limit:
                return casos
    return casos


def extraer_desde_dir(
    input_dir: Path,
    *,
    max_turnos: int = 4,
    categoria: str | None = "internet",
    limit: int = 200,
    max_files: int = 0,
) -> list[CasoBotmaker]:
    paths = sorted(input_dir.glob("sessions-*.raw.json"))
    if not paths:
        paths = sorted(input_dir.glob("*.json"))
    if max_files > 0:
        paths = paths[:max_files]
    return extraer_desde_paths(
        paths, max_turnos=max_turnos, categoria=categoria, limit=limit
    )


FIXTURE_MUESTRA = ROOT / "tests" / "fixtures" / "botmaker_sesiones_muestra.json"


def guardar_corpus(casos: list[CasoBotmaker], dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "n": len(casos),
        "casos": [asdict(c) for c in casos],
    }
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def cargar_corpus(path: Path) -> list[CasoBotmaker]:
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get("casos") if isinstance(data, dict) else data
    out: list[CasoBotmaker] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        out.append(
            CasoBotmaker(
                id=str(item.get("id") or ""),
                categoria=str(item.get("categoria") or "otro"),
                apertura=str(item.get("apertura") or ""),
                turnos_usuario=list(item.get("turnos_usuario") or []),
                n_user=int(item.get("n_user") or 0),
                fuente=str(item.get("fuente") or ""),
                tags=list(item.get("tags") or []),
            )
        )
    return out
