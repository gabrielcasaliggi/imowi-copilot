"""Métricas operativas (LLM)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import UsuarioSesion, obtener_usuario_requerido, requiere_admin
from app.llm_metrics import history_llm_metrics, snapshot_llm_metrics

router = APIRouter(tags=["Metrics"])


@router.get("/metrics/llm")
def metrics_llm(
    recent: int = 20,
    desde: str | None = None,
    hasta: str | None = None,
    _: UsuarioSesion = Depends(requiere_admin),
):
    """Live (memoria desde restart) + histórico persistido (llm_calls) con rango de fechas."""
    live = snapshot_llm_metrics(recent=recent)
    try:
        history = history_llm_metrics(desde=desde, hasta=hasta, recent=recent)
    except Exception:
        history = {
            "desde": None,
            "hasta": None,
            "calls_ok": 0,
            "calls_error": 0,
            "calls_total": 0,
            "avg_latency_ms_ok": 0.0,
            "tokens_total": 0,
            "by_model": {},
            "recent": [],
            "error": "historial_no_disponible",
        }
    return {
        "status": "ok",
        # Compat: campos top-level = live (como antes)
        **live,
        "live": live,
        "history": history,
    }
