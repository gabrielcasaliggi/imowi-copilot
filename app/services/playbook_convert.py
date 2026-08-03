"""Convierte documentos de troubleshooting (texto libre) a playbooks N1 estructurados."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.domain.flujos_abonado import PLAYBOOKS

_VALID_KEYS = frozenset(PLAYBOOKS.keys())

_SYSTEM = """Sos un asistente que convierte guías de soporte técnico a playbooks N1.
Respondé SOLO con JSON válido (sin markdown ni explicaciones).

Formato exacto:
{
  "playbooks": {
    "<clave>": [{"id": "slug_corto", "pregunta": "pregunta conversacional al abonado?"}]
  },
  "sugeridos": ["<clave>", ...]
}

Reglas:
- Claves permitidas (solo estas): """ + ", ".join(sorted(_VALID_KEYS)) + """
- Si el documento ramifica por tecnología (fibra/ADSL/radio/WiFi/móvil), generá un flujo por rama.
- Cada flujo es una lista LINEAL de preguntas (una por turno). No uses ramas dentro del flujo.
- "id": snake_case corto, único dentro del flujo, sin espacios.
- "pregunta": tono humano breve en español rioplatense, como si hablara un agente por WhatsApp. Terminar en pregunta cuando corresponda.
- Incluí un paso final de derivación/escalamiento si el documento lo indica.
- "sugeridos": lista de claves que conviene aplicar (las que el documento cubre).
- No inventes flujos ajenos al documento. Si solo habla de internet lento + fibra/ADSL/radio, no toques móvil ni facturación.
"""


def _extract_json(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("Respuesta vacía de la IA")
    # Quitar fences ```json ... ```
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if fence:
        raw = fence.group(1).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Intentar primer objeto {...}
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("La IA no devolvió JSON válido")
        data = json.loads(raw[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("JSON raíz debe ser un objeto")
    return data


def _slugify(value: str, fallback: str) -> str:
    s = re.sub(r"[^a-z0-9_]+", "_", (value or "").lower().strip())
    s = re.sub(r"_+", "_", s).strip("_")
    return s or fallback


def normalize_playbooks_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Valida y limpia el payload de la IA."""
    raw_pb = data.get("playbooks") or {}
    if not isinstance(raw_pb, dict):
        raise ValueError("'playbooks' debe ser un objeto")

    out: dict[str, list[dict[str, str]]] = {}
    for key, pasos in raw_pb.items():
        nombre = str(key or "").strip()
        if nombre not in _VALID_KEYS:
            continue
        if not isinstance(pasos, list) or not pasos:
            continue
        cleaned: list[dict[str, str]] = []
        seen: set[str] = set()
        for i, p in enumerate(pasos):
            if not isinstance(p, dict):
                continue
            pregunta = str(p.get("pregunta") or "").strip()
            if not pregunta:
                continue
            pid = _slugify(str(p.get("id") or ""), f"paso_{i + 1}")
            base = pid
            n = 2
            while pid in seen:
                pid = f"{base}_{n}"
                n += 1
            seen.add(pid)
            cleaned.append({"id": pid, "pregunta": pregunta})
        if cleaned:
            out[nombre] = cleaned

    if not out:
        raise ValueError("No se pudo extraer ningún flujo válido del documento")

    sugeridos_raw = data.get("sugeridos")
    if isinstance(sugeridos_raw, list) and sugeridos_raw:
        sugeridos = [str(s).strip() for s in sugeridos_raw if str(s).strip() in out]
    else:
        sugeridos = list(out.keys())

    return {"playbooks": out, "sugeridos": sugeridos}


def convert_document_to_playbooks(db: Session | None, texto: str) -> dict[str, Any]:
    """Llama a la IA de plataforma y normaliza el resultado."""
    texto = (texto or "").strip()
    if len(texto) < 40:
        raise ValueError("El texto es demasiado corto para convertir")
    if len(texto) > 80_000:
        raise ValueError("El texto supera el límite (80.000 caracteres)")

    from app.services.platform_settings import resolve_ai

    cfg = resolve_ai(db)
    from openai import OpenAI

    client = OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"] or "ollama")
    resp = client.chat.completions.create(
        model=cfg["model"],
        messages=[
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": (
                    "Convertí este documento de troubleshooting a playbooks N1:\n\n"
                    f"{texto}"
                ),
            },
        ],
        temperature=0.2,
        max_tokens=4096,
    )
    content = (resp.choices[0].message.content or "").strip()
    parsed = _extract_json(content)
    return normalize_playbooks_payload(parsed)
