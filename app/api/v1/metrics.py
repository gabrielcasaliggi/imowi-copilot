"""Métricas operativas (LLM)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import UsuarioSesion, obtener_usuario_requerido
from app.llm_metrics import snapshot_llm_metrics

router = APIRouter(tags=["Metrics"])


@router.get("/metrics/llm")
def metrics_llm(
    recent: int = 20,
    _: UsuarioSesion = Depends(obtener_usuario_requerido),
):
    """Snapshot in-process de llamadas LLM desde el último restart del API."""
    return {"status": "ok", **snapshot_llm_metrics(recent=recent)}
