"""Branding público (sin auth) — asistente N1 y producto abonado."""

from __future__ import annotations

from fastapi import APIRouter

from app.branding_assistant import assistant_intro_public
from app.config import (
    ASSISTANT_TAGLINE,
    BOT_DISPLAY_NAME,
    BOT_DISPLAY_NAME_SHORT,
    PRODUCT_DISPLAY_NAME,
)

router = APIRouter(tags=["branding"])


@router.get("/public/branding")
def public_branding():
    return {
        "bot_display_name": BOT_DISPLAY_NAME,
        "bot_display_name_short": BOT_DISPLAY_NAME_SHORT,
        "org_hint": "Cooperativa Batán",
        "product_display_name": PRODUCT_DISPLAY_NAME,
        "assistant_tagline": ASSISTANT_TAGLINE,
        "assistant_intro": assistant_intro_public(),
    }
