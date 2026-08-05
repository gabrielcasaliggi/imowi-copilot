"""Cliente LLM compatible OpenAI (Ollama / Groq / Gemini / Llama)."""

from __future__ import annotations

import logging
import time

from fastapi import HTTPException
from openai import OpenAI

from app.config import AI_API_KEY, AI_BASE_URL, AI_MODEL
from app.llm_metrics import record_llm_call

logger = logging.getLogger("operations_hub.llm")


def _resolve_ai_runtime() -> dict[str, str]:
    try:
        from app.estate.database import get_session_factory
        from app.services.platform_settings import resolve_ai

        db = get_session_factory()()
        try:
            return resolve_ai(db)
        finally:
            db.close()
    except Exception:
        return {"base_url": AI_BASE_URL, "api_key": AI_API_KEY, "model": AI_MODEL}


def chat_completion(
    messages: list[dict],
    *,
    temperature: float = 0.2,
    json_mode: bool = False,
) -> str:
    cfg = _resolve_ai_runtime()
    model = cfg.get("model") or AI_MODEL
    client = OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"] or "ollama")
    t0 = time.perf_counter()
    try:
        kwargs: dict = {"model": model, "messages": messages, "temperature": temperature}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = client.chat.completions.create(**kwargs)
        latency_ms = (time.perf_counter() - t0) * 1000
        usage = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
        total_tokens = int(getattr(usage, "total_tokens", 0) or 0) if usage else 0
        record_llm_call(
            ok=True,
            latency_ms=latency_ms,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )
        logger.info(
            "llm_ok model=%s latency_ms=%.0f tokens=%s",
            model,
            latency_ms,
            total_tokens or "-",
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        latency_ms = (time.perf_counter() - t0) * 1000
        record_llm_call(ok=False, latency_ms=latency_ms, model=model, error=str(e)[:200])
        logger.warning("llm_error model=%s latency_ms=%.0f err=%s", model, latency_ms, e)
        raise manejar_error_ia(e) from e


def manejar_error_ia(e: Exception) -> HTTPException:
    msg = str(e)
    if "429" in msg or "quota" in msg.lower():
        return HTTPException(
            status_code=503,
            detail="Cuota de la API agotada. Probá más tarde o revisá tu proveedor LLM.",
        )
    if "413" in msg or "payload too large" in msg.lower() or "request too large" in msg.lower():
        return HTTPException(
            status_code=413,
            detail=(
                "Solicitud demasiado grande para el LLM (>6000 tokens). "
                "La KB ya se filtra por keywords; acortá el historial del chat o reducí KNOWLEDGE_MAX_FRAGMENT_CHARS."
            ),
        )
    if "API key" in msg or "API_KEY" in msg or "connection" in msg.lower():
        return HTTPException(
            status_code=503,
            detail="No se pudo conectar con el LLM. Verificá AI_BASE_URL y que Ollama esté corriendo.",
        )
    return HTTPException(status_code=500, detail=msg)
