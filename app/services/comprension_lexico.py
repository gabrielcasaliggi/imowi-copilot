"""Carga del léxico curado (minado Botmaker + reglas estáticas)."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_LEXICO_PATH = Path(__file__).resolve().parent.parent / "data" / "comprension_lexico_curado.json"

# Base estática: siempre activa aunque falte el JSON curado.
_REEMPLAZOS_BASE: tuple[tuple[str, str], ...] = (
    (r"\bbeibe?\b", "bai"),
    (r"\bbaii+\b", "bai"),
    (r"\bwfi\b", "wifi"),
    (r"\bwiffi\b", "wifi"),
    (r"\bwi\s+fi\b", "wifi"),
    (r"\bintenret\b", "internet"),
    (r"\bintenet\b", "internet"),
    (r"\binternt\b", "internet"),
    (r"\binterenet\b", "internet"),
    (r"\bno\s+and\b", "no anda"),
    (r"\bnos\s+pague?\b", "no pagué"),
    (r"\btodo\s+bien.*?pague?\b", "todavía no pagué"),
    (r"\bedad\b", "deuda"),
    (r"\banel\b", "antena"),
    (r"\banntena\b", "antena"),
    (r"\bfibbra\b", "fibra"),
)


@lru_cache(maxsize=1)
def cargar_lexico_curado() -> dict[str, Any]:
    if not _LEXICO_PATH.is_file():
        return {}
    try:
        return json.loads(_LEXICO_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def reemplazos_lexico() -> tuple[tuple[str, str], ...]:
    """Patrones regex → reemplazo, base + curado."""
    out: list[tuple[str, str]] = list(_REEMPLAZOS_BASE)
    vistos = {p for p, _ in out}
    data = cargar_lexico_curado()
    for item in data.get("reemplazos_regex") or []:
        if not isinstance(item, dict):
            continue
        patron = str(item.get("patron") or "").strip()
        reemplazo = str(item.get("reemplazo") or "").strip()
        if patron and reemplazo and patron not in vistos:
            out.append((patron, reemplazo))
            vistos.add(patron)
    return tuple(out)


def frases_tecnico_en_aviso_deuda() -> frozenset[str]:
    """Frases cortas que en Botmaker eligieron seguir con diagnóstico (no pago)."""
    data = cargar_lexico_curado()
    base = {
        "internet",
        "no tengo internet",
        "sin internet",
        "no anda",
        "no funciona",
        "sin servicio",
        "no hay internet",
        "cortado",
        "corte",
        "wifi",
        "antena",
        "bai",
        "fibra",
        "lento",
        "el servicio",
        "problema",
    }
    extra = data.get("frases_tecnico_en_aviso_deuda") or []
    for bucket_frases in (data.get("frases_frecuentes_por_contexto") or {}).get(
        "aviso_deuda", []
    ):
        if isinstance(bucket_frases, str):
            extra.append(bucket_frases)
    for frase in extra:
        f = str(frase).lower().strip()
        if f and not f.isdigit() and f not in ("hola", "gracias", "ok", "menu", ".", "?"):
            base.add(f)
    return frozenset(base)


def afirmaciones_extra() -> frozenset[str]:
    data = cargar_lexico_curado()
    base = {"sip", "sep", "see", "listo", "claro", "obvio", "buena", "excelente"}
    for a in data.get("afirmaciones_cortas_extra") or []:
        base.add(str(a).lower().strip())
    return frozenset(x for x in base if x)


def negaciones_extra() -> frozenset[str]:
    data = cargar_lexico_curado()
    base: set[str] = set()
    for n in data.get("negaciones_cortas_extra") or []:
        base.add(str(n).lower().strip())
    return frozenset(x for x in base if x)


def aplicar_reemplazos_lexico(texto: str) -> str:
    t = re.sub(r"\s+", " ", (texto or "").strip())
    if not t:
        return t
    for patron, reemplazo in reemplazos_lexico():
        t = re.sub(patron, reemplazo, t, flags=re.IGNORECASE)
    return t.strip()
