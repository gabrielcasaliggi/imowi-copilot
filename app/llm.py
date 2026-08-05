"""Cliente LLM compatible OpenAI (Ollama / Groq / Gemini / Llama)."""

from __future__ import annotations

from fastapi import HTTPException
from openai import OpenAI

from app.config import AI_API_KEY, AI_BASE_URL, AI_MODEL


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
    client = OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"] or "ollama")
    try:
        kwargs: dict = {"model": cfg["model"], "messages": messages, "temperature": temperature}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""
    except Exception as e:
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
