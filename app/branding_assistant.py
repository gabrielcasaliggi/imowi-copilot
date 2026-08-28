"""Copy público del asistente N1 (Eko) — saludos y presentación."""

from __future__ import annotations

from app.config import ASSISTANT_TAGLINE, BOT_DISPLAY_NAME, PRODUCT_DISPLAY_NAME


def assistant_tagline_mid() -> str:
    """Tagline en minúscula para usar en medio de una oración."""
    t = (ASSISTANT_TAGLINE or "Tu asistente virtual").strip()
    if len(t) > 1 and t[0].isupper():
        return t[0].lower() + t[1:]
    return t


def frase_soy_eko(*, primer_nombre: str = "") -> str:
    """«Hola [Nombre], soy Eko, tu asistente virtual de Soporte Batán» (sin punto final)."""
    nombre = (primer_nombre or "").strip()
    if nombre:
        return (
            f"Hola {nombre}, soy {BOT_DISPLAY_NAME}, "
            f"{assistant_tagline_mid()} de {PRODUCT_DISPLAY_NAME}"
        )
    return (
        f"Hola, soy {BOT_DISPLAY_NAME}, "
        f"{assistant_tagline_mid()} de {PRODUCT_DISPLAY_NAME}"
    )


def saludo_identificacion_dni() -> str:
    return (
        f"{frase_soy_eko()}. "
        "Para ayudarte, enviame tu DNI o número de socio. "
        "Si preferís, escribí *agente*."
    )


def saludo_con_menu(*, primer_nombre: str = "", menu: str = "") -> str:
    base = frase_soy_eko(primer_nombre=primer_nombre)
    menu = (menu or "").strip()
    if menu:
        return f"{base}. {menu}"
    return f"{base}."


def assistant_intro_public() -> str:
    """Frase estándar de presentación (sin nombre)."""
    return f"{frase_soy_eko()}."
