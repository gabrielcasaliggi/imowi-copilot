"""Cliente LLM compatible OpenAI (Ollama / Groq / Gemini)."""

from __future__ import annotations

from openai import OpenAI
from fastapi import HTTPException

from app.config import AI_API_KEY, AI_BASE_URL, AI_MODEL

_client = OpenAI(base_url=AI_BASE_URL, api_key=AI_API_KEY)


def chat_completion(
    messages: list[dict],
    *,
    temperature: float = 0.2,
    json_mode: bool = False,
) -> str:
    try:
        kwargs: dict = {"model": AI_MODEL, "messages": messages, "temperature": temperature}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = _client.chat.completions.create(**kwargs)
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
    if "API key" in msg or "API_KEY" in msg or "connection" in msg.lower():
        return HTTPException(
            status_code=503,
            detail="No se pudo conectar con el LLM. Verificá AI_BASE_URL y que Ollama esté corriendo.",
        )
    return HTTPException(status_code=500, detail=msg)
