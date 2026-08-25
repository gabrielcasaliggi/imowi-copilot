"""Lotes nombrados del entrenamiento N1 (IDs de personas hogareñas)."""

from __future__ import annotations

LOTE_BASE = [f"P{i:02d}" for i in range(1, 19)]  # P01–P18
LOTE_GUION = LOTE_BASE + [f"P{i:02d}" for i in range(19, 29)]  # + P19–P28
LOTE_EXHAUSTIVO = LOTE_GUION

LOTES: dict[str, list[str]] = {
    "base": LOTE_BASE,
    "guion": LOTE_GUION,
    "exhaustivo": LOTE_EXHAUSTIVO,
    "internet": [
        "P01",
        "P02",
        "P03",
        "P04",
        "P05",
        "P06",
        "P08",
        "P09",
        "P10",
        "P11",
        "P12",
    ],
    "factura": ["P13", "P14", "P15", "P16", "P21", "P22", "P27"],
    "movil": ["P19", "P23", "P24", "P26"],
    "agente": ["P07", "P20"],
    "sensa": ["P17", "P18"],
}
