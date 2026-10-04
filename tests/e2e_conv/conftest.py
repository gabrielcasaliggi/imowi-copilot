"""Marca todo lo de ``tests/e2e_conv`` con ``@pytest.mark.e2e_conv`` (tanda propia)."""

from __future__ import annotations

from pathlib import Path

import pytest

_AQUI = Path(__file__).resolve().parent


def pytest_collection_modifyitems(items):
    for item in items:
        if _AQUI in Path(str(item.fspath)).resolve().parents:
            item.add_marker(pytest.mark.e2e_conv)
