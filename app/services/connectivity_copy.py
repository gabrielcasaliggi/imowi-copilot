"""Copy de producto para self-service de conectividad (portal/mobile)."""

from __future__ import annotations

from app.services.connectivity_evidence import MessageKey

CHAT_HINT_DEFAULT = (
    "Si en tu casa sigue fallando, escribinos y te ayudamos."
)

_OUTAGE_FALLBACK = "Detectamos una incidencia que puede afectar tu servicio."

_MESSAGES: dict[MessageKey, str] = {
    "operational": "No registramos problemas en tu acceso a Internet.",
    "impaired_access_down": "Detectamos un problema en tu acceso a Internet.",
    "impaired_quality": (
        "Tu acceso muestra condiciones deficientes. Te recomendamos contactarnos."
    ),
    "impaired_no_session": (
        "Tu acceso responde, pero no hay una sesión activa en este momento."
    ),
    "outage": _OUTAGE_FALLBACK,
    "unknown_stale": "No tenemos una verificación reciente de tu acceso.",
    "unknown_sources": "No pudimos verificar tu servicio en este momento.",
    "service_selection": (
        "Tenés más de un servicio de Internet. Elegí cuál querés consultar."
    ),
}


def mensaje_para(
    message_key: MessageKey,
    *,
    incident_message: str = "",
) -> str:
    if message_key == "outage":
        custom = (incident_message or "").strip()
        return custom or _OUTAGE_FALLBACK
    return _MESSAGES[message_key]
