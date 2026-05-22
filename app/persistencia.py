"""Persistencia JSON en disco (demo: sobrevive reinicios de uvicorn)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import DATA_DIR

_DEFAULT_DATA = Path(__file__).resolve().parent.parent / "data"


def data_dir() -> Path:
    base = Path(DATA_DIR) if DATA_DIR else _DEFAULT_DATA
    base.mkdir(parents=True, exist_ok=True)
    return base


def leer_json(nombre: str, default: Any) -> Any:
    path = data_dir() / nombre
    if not path.is_file():
        return default
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def escribir_json(nombre: str, data: Any) -> None:
    path = data_dir() / nombre
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
