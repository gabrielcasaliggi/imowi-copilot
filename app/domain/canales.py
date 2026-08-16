"""Canales del abonado: propios (web/app) vs terceros (WhatsApp/Telegram)."""

from __future__ import annotations

CANALES_PROPIOS = frozenset({"web", "app"})
CANALES_PORTAL = CANALES_PROPIOS
CANAL_DEFAULT_PORTAL = "web"


def normalizar_canal_portal(raw: str | None) -> str:
    c = (raw or "").strip().lower()
    return c if c in CANALES_PORTAL else CANAL_DEFAULT_PORTAL


def es_canal_propio(canal: str | None) -> bool:
    return (canal or "").strip().lower() in CANALES_PROPIOS


def enviar_externo(canal: str | None) -> bool:
    """True si hay que empujar la respuesta a WhatsApp/Telegram."""
    return not es_canal_propio(canal)


def canal_display(canal: str | None) -> str:
    c = (canal or "").strip().lower()
    if c in ("whatsapp", "simulate"):
        return "WhatsApp"
    if c == "telegram":
        return "Telegram"
    if c == "web":
        return "Web"
    if c == "app":
        return "App"
    return canal or "otro"
