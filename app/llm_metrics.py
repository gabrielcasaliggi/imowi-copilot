"""Métricas LLM: snapshot in-process + persistencia en llm_calls."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, time as dt_time, timedelta
from typing import Any

logger = logging.getLogger("operations_hub.llm_metrics")


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
    organizacion_id: str = "",
    actor: str = "",
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
    _persist_llm_call(
        rec,
        organizacion_id=(organizacion_id or "")[:36],
        actor=(actor or "")[:120],
    )


def _persist_llm_call(rec: LlmCallRecord, *, organizacion_id: str, actor: str) -> None:
    """Best-effort: no debe romper el flujo LLM si falla la DB."""
    try:
        from app.estate.database import get_session_factory
        from app.estate.models import LlmCall

        db = get_session_factory()()
        try:
            db.add(
                LlmCall(
                    organizacion_id=organizacion_id,
                    actor=actor,
                    ok=1 if rec.ok else 0,
                    latency_ms=int(round(rec.latency_ms)),
                    model=rec.model,
                    error=rec.error,
                    prompt_tokens=rec.prompt_tokens,
                    completion_tokens=rec.completion_tokens,
                    total_tokens=rec.total_tokens,
                )
            )
            db.commit()
        finally:
            db.close()
    except Exception:
        logger.debug("No se pudo persistir llm_call", exc_info=True)


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


def _parse_day_start(value: str | None) -> datetime | None:
    if not value:
        return None
    d = datetime.fromisoformat(value).date()
    return datetime.combine(d, dt_time.min, tzinfo=UTC)


def _parse_day_end(value: str | None) -> datetime | None:
    if not value:
        return None
    d = datetime.fromisoformat(value).date()
    return datetime.combine(d, dt_time.max, tzinfo=UTC)


def history_llm_metrics(
    *,
    desde: str | None = None,
    hasta: str | None = None,
    recent: int = 30,
) -> dict[str, Any]:
    """Agregados persistidos en llm_calls para el rango de fechas."""
    from sqlalchemy import select

    from app.estate.database import get_session_factory
    from app.estate.models import LlmCall

    ahora = datetime.now(UTC)
    hasta_dt = _parse_day_end(hasta) or ahora
    desde_dt = _parse_day_start(desde) or (hasta_dt - timedelta(days=7))

    db = get_session_factory()()
    try:
        rows = list(
            db.scalars(
                select(LlmCall)
                .where(LlmCall.created_at >= desde_dt, LlmCall.created_at <= hasta_dt)
                .order_by(LlmCall.created_at.asc())
            ).all()
        )
    finally:
        db.close()

    ok_n = sum(1 for r in rows if r.ok)
    err_n = len(rows) - ok_n
    lat_ok = [r.latency_ms for r in rows if r.ok]
    avg = round(sum(lat_ok) / len(lat_ok), 1) if lat_ok else 0.0
    tokens = sum(int(r.total_tokens or 0) for r in rows)

    by_model: dict[str, dict[str, Any]] = {}
    for r in rows:
        key = r.model or "?"
        bucket = by_model.setdefault(
            key,
            {"calls": 0, "ok": 0, "error": 0, "tokens": 0, "latency_sum_ok": 0},
        )
        bucket["calls"] += 1
        if r.ok:
            bucket["ok"] += 1
            bucket["latency_sum_ok"] += int(r.latency_ms or 0)
        else:
            bucket["error"] += 1
        bucket["tokens"] += int(r.total_tokens or 0)

    by_model_out: dict[str, dict[str, Any]] = {}
    for model, b in by_model.items():
        by_model_out[model] = {
            "calls": b["calls"],
            "ok": b["ok"],
            "error": b["error"],
            "tokens": b["tokens"],
            "avg_latency_ms_ok": round(b["latency_sum_ok"] / b["ok"], 1) if b["ok"] else 0.0,
        }

    recent_n = max(1, min(int(recent or 30), 100))
    recent_rows = rows[-recent_n:]
    recent_out = [
        {
            "ts": r.created_at.timestamp() if r.created_at else 0,
            "ok": bool(r.ok),
            "latency_ms": float(r.latency_ms or 0),
            "model": r.model or "",
            "error": r.error or "",
            "prompt_tokens": int(r.prompt_tokens or 0),
            "completion_tokens": int(r.completion_tokens or 0),
            "total_tokens": int(r.total_tokens or 0),
            "actor": r.actor or "",
        }
        for r in recent_rows
    ]

    return {
        "desde": desde_dt.isoformat(),
        "hasta": hasta_dt.isoformat(),
        "calls_ok": ok_n,
        "calls_error": err_n,
        "calls_total": len(rows),
        "avg_latency_ms_ok": avg,
        "tokens_total": tokens,
        "by_model": by_model_out,
        "recent": recent_out,
    }


def reset_llm_metrics_for_tests() -> None:
    global _TOTAL_OK, _TOTAL_ERR, _SUM_LATENCY_OK_MS
    with _LOCK:
        _HISTORY.clear()
        _TOTAL_OK = 0
        _TOTAL_ERR = 0
        _SUM_LATENCY_OK_MS = 0.0
