"""Filtro semántico pre-LLM — evita invocar GPU/LLM en consultas irrelevantes."""

from __future__ import annotations

import re

# Consultas claramente fuera de dominio Telco/ISP
_CASUAL_PATTERNS = (
    r"\b(clima|tiempo|lluvia|temperatura)\b",
    r"\b(chiste|broma|cuento)\b",
    r"\b(qu[eé]\s*hora\s*es)\b",
    r"\b(quien\s*eres|qui[eé]n\s*sos|qu[eé]\s*eres)\b",
    r"\b(f[uú]tbol|deportes?|partido)\b",
    r"\b(receta|cocinar|comida)\b",
)

_SALUDO_PATTERN = r"^(hola|buenas|buen d[ií]a|buenos d[ií]as|buenas tardes|buenas noches|hey|qu[eé] tal)\s*[!.?]*$"

_TECHNICAL_HINTS = (
    "falla", "fallo", "problema", "sin servicio", "no funciona", "no anda",
    "linea", "línea", "apn", "roaming", "datos", "fibra", "ont", "olt",
    "sms", "llamada", "internet", "esim", "sim", "cooperativa", "coop",
    "cliente", "abonado", "ticket", "incidente", "latencia", "paquete",
    "celda", "red", "dispositivo", "samsung", "iphone", "motorola",
    "escalar", "noc", "reclamo", "averia", "avería",
    "anomalia", "anomalía", "predictiva", "predictivo", "degradacion", "degradación",
)


def analizar_relevancia(mensaje: str, historial_tecnico: bool = False) -> dict:
    """
    Retorna si el mensaje amerita pipeline agentic + LLM.
    historial_tecnico: True si la conversación ya trata un caso técnico.
    """
    t = (mensaje or "").strip().lower()
    if not t:
        return {"relevante": False, "motivo": "vacío", "respuesta_corta": "Contame el inconveniente técnico del cliente."}

    if historial_tecnico:
        return {"relevante": True, "motivo": "contexto_tecnico_activo"}

    if re.search(_SALUDO_PATTERN, t, re.I):
        return {
            "relevante": False,
            "motivo": "saludo",
            "respuesta_corta": (
                "Buen día. Contame el reclamo cuando quieras: línea, síntoma y, si lo tenés, modelo del equipo."
            ),
        }

    for pat in _CASUAL_PATTERNS:
        if re.search(pat, t, re.I):
            return {
                "relevante": False,
                "motivo": "consulta_no_operativa",
                "respuesta_corta": (
                    "Soy el Copilot NOC de operaciones. Solo puedo ayudarte con "
                    "reclamos técnicos, red, líneas y servicios del ISP. ¿Qué le pasa al cliente?"
                ),
            }

    if any(h in t for h in _TECHNICAL_HINTS):
        return {"relevante": True, "motivo": "senal_tecnica"}

    if re.search(r"\d{8,11}", t):
        return {"relevante": True, "motivo": "linea_detectada"}

    if len(t.split()) <= 3 and t in ("hola", "buenas", "gracias", "ok", "listo"):
        return {
            "relevante": False,
            "motivo": "saludo",
            "respuesta_corta": "Dale. Cuando tengas el caso, pasame línea, síntoma y equipo.",
        }

    # Ambiguo: permitir LLM si parece descripción larga
    if len(t) > 40:
        return {"relevante": True, "motivo": "descripcion_extensa"}

    return {
        "relevante": False,
        "motivo": "fuera_de_dominio",
        "respuesta_corta": (
            "Para ayudarte necesito un poco más de contexto del reclamo: línea, dispositivo y qué le pasa al cliente."
        ),
    }
