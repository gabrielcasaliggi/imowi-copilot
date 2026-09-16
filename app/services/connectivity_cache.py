"""Cache in-process de evaluaciones de conectividad portal (TTL configurable)."""

from __future__ import annotations

import threading
import time
from typing import Any

from app.config import PORTAL_CONNECTIVITY_TTL_SEC

_LOCK = threading.Lock()
# key -> {"ts": float, "payload": dict}
_STORE: dict[tuple[str, str, str], dict[str, Any]] = {}


def _ttl() -> float:
    try:
        return float(PORTAL_CONNECTIVITY_TTL_SEC)
    except (TypeError, ValueError):
        return 300.0


def cache_key(org_id: str, abonado_id: str, service_id: str) -> tuple[str, str, str]:
    return (
        str(org_id or "").strip(),
        str(abonado_id or "").strip(),
        str(service_id or "").strip(),
    )


def get_fresh(
    org_id: str, abonado_id: str, service_id: str
) -> dict[str, Any] | None:
    """Devuelve payload cacheado solo si está dentro del TTL."""
    key = cache_key(org_id, abonado_id, service_id)
    now = time.monotonic()
    with _LOCK:
        entry = _STORE.get(key)
        if not entry:
            return None
        age = now - float(entry.get("ts") or 0)
        if age > _ttl():
            _STORE.pop(key, None)
            return None
        payload = entry.get("payload")
        return dict(payload) if isinstance(payload, dict) else None


def put(
    org_id: str,
    abonado_id: str,
    service_id: str,
    payload: dict[str, Any],
) -> None:
    """Cachea solo estados afirmativos (no unknown)."""
    status = str((payload or {}).get("status") or "")
    if status == "unknown":
        return
    if status not in ("operational", "impaired", "outage"):
        return
    key = cache_key(org_id, abonado_id, service_id)
    with _LOCK:
        _STORE[key] = {"ts": time.monotonic(), "payload": dict(payload)}


def clear() -> None:
    """Solo tests."""
    with _LOCK:
        _STORE.clear()


def ttl_seconds() -> float:
    return _ttl()
