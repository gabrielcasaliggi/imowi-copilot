"""Métricas in-process de llamadas LLM (Fase C rápida)."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class LlmCallRecord:
    ts: float
    ok: bool
    latency_ms: float
    model: str
    error: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


_LOCK = threading.Lock()
_HISTORY: deque[LlmCallRecord] = deque(maxlen=500)
_TOTAL_OK = 0
_TOTAL_ERR = 0
_SUM_LATENCY_OK_MS = 0.0


def record_llm_call(
    *,
    ok: bool,
    latency_ms: float,
    model: str,
    error: str = "",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
) -> None:
    global _TOTAL_OK, _TOTAL_ERR, _SUM_LATENCY_OK_MS
    rec = LlmCallRecord(
        ts=time.time(),
        ok=ok,
        latency_ms=round(latency_ms, 1),
        model=(model or "")[:80],
        error=(error or "")[:200],
        prompt_tokens=int(prompt_tokens or 0),
        completion_tokens=int(completion_tokens or 0),
        total_tokens=int(total_tokens or 0),
    )
    with _LOCK:
        _HISTORY.append(rec)
        if ok:
            _TOTAL_OK += 1
            _SUM_LATENCY_OK_MS += rec.latency_ms
        else:
            _TOTAL_ERR += 1


def snapshot_llm_metrics(*, recent: int = 20) -> dict[str, Any]:
    with _LOCK:
        hist = list(_HISTORY)
        total_ok = _TOTAL_OK
        total_err = _TOTAL_ERR
        sum_lat = _SUM_LATENCY_OK_MS
    n = len(hist)
    avg = (sum_lat / total_ok) if total_ok else 0.0
    recent_recs = hist[-max(1, min(recent, 100)) :] if hist else []
    by_model: dict[str, int] = {}
    for r in hist:
        by_model[r.model or "?"] = by_model.get(r.model or "?", 0) + 1
    return {
        "calls_ok": total_ok,
        "calls_error": total_err,
        "calls_total": total_ok + total_err,
        "avg_latency_ms_ok": round(avg, 1),
        "window_size": n,
        "by_model": by_model,
        "recent": [asdict(r) for r in recent_recs],
    }


def reset_llm_metrics_for_tests() -> None:
    global _TOTAL_OK, _TOTAL_ERR, _SUM_LATENCY_OK_MS
    with _LOCK:
        _HISTORY.clear()
        _TOTAL_OK = 0
        _TOTAL_ERR = 0
        _SUM_LATENCY_OK_MS = 0.0
