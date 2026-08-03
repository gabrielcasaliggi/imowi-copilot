"""Convierte documentos de troubleshooting (texto libre) a playbooks N1 estructurados."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.domain.flujos_abonado import PLAYBOOKS

_VALID_KEYS = frozenset(PLAYBOOKS.keys())

# Nombres que la IA suele inventar → clave real del sistema
_ALIASES: dict[str, str] = {
    "otro": "no_tecnico",
    "otro_no_tecnico": "no_tecnico",
    "no_tecnico": "no_tecnico",
    "ticket_generico": "no_tecnico",
    "ticket_genérico": "no_tecnico",
    "reclamo_generico": "no_tecnico",
    "reclamo_genérico": "no_tecnico",
    "consulta_no_tecnica": "no_tecnico",
    "comercial_admin": "no_tecnico",
    "legal": "no_tecnico",
    "administrativo": "facturacion",
    "comercial": "alta_plan",
}

_SYSTEM = """Sos un asistente que convierte guías de soporte a playbooks N1.
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
- Documentos NO técnicos (comercial, administrativo, legal, ticket genérico, "otro"):
  usá la clave **no_tecnico**. Opcionalmente también facturacion / alta_plan / general si el texto lo cubre.
- Si el documento ramifica por tecnología (fibra/ADSL/radio/WiFi/móvil), generá un flujo por rama.
- Cada flujo es una lista LINEAL de preguntas (una por turno). No uses ramas dentro del flujo.
- Convertí solo lo que se le pregunta al abonado. Ignorá etiquetas internas de ticket, notas de agente y checklists de backoffice.
- "id": snake_case corto, único dentro del flujo, sin espacios.
- "pregunta": tono humano breve en español rioplatense, como WhatsApp. Terminar en pregunta cuando corresponda.
- Incluí un paso final de derivación si el documento lo indica.
- "sugeridos": claves que conviene aplicar.
- No inventes claves fuera de la lista. Si pensás en "otro" o "ticket_generico", usá **no_tecnico**.
"""


def _extract_json(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("Respuesta vacía de la IA")
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if fence:
        raw = fence.group(1).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
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


def _resolve_key(nombre: str) -> str | None:
    key = (nombre or "").strip()
    if key in _VALID_KEYS:
        return key
    aliased = _ALIASES.get(key.lower().replace(" ", "_"))
    if aliased and aliased in _VALID_KEYS:
        return aliased
    return None


def normalize_playbooks_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Valida y limpia el payload de la IA."""
    raw_pb = data.get("playbooks") or {}
    if not isinstance(raw_pb, dict):
        raise ValueError("'playbooks' debe ser un objeto")

    out: dict[str, list[dict[str, str]]] = {}
    descartados: list[str] = []

    for key, pasos in raw_pb.items():
        nombre = str(key or "").strip()
        resolved = _resolve_key(nombre)
        if not resolved:
            if nombre:
                descartados.append(nombre)
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
            # Si dos alias caen en la misma clave, gana el más largo (más completo)
            prev = out.get(resolved) or []
            if len(cleaned) >= len(prev):
                out[resolved] = cleaned

    if not out:
        hint = ""
        if descartados:
            hint = (
                f" La IA usó claves no válidas: {', '.join(descartados)}. "
                f"Válidas: {', '.join(sorted(_VALID_KEYS))}."
            )
        raise ValueError("No se pudo extraer ningún flujo válido del documento." + hint)

    sugeridos_raw = data.get("sugeridos")
    if isinstance(sugeridos_raw, list) and sugeridos_raw:
        sugeridos: list[str] = []
        for s in sugeridos_raw:
            resolved = _resolve_key(str(s).strip())
            if resolved and resolved in out and resolved not in sugeridos:
                sugeridos.append(resolved)
        if not sugeridos:
            sugeridos = list(out.keys())
    else:
        sugeridos = list(out.keys())

    return {
        "playbooks": out,
        "sugeridos": sugeridos,
        "descartados": descartados,
        "claves_validas": sorted(_VALID_KEYS),
    }


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
                    "Convertí este documento de soporte a playbooks N1:\n\n"
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
