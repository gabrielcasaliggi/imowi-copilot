"""Branding público (sin auth) — nombre del asistente abonado."""

from __future__ import annotations

from fastapi import APIRouter

from app.config import BOT_DISPLAY_NAME, BOT_DISPLAY_NAME_SHORT

router = APIRouter(tags=["branding"])


@router.get("/public/branding")
def public_branding():
    return {
        "bot_display_name": BOT_DISPLAY_NAME,
        "bot_display_name_short": BOT_DISPLAY_NAME_SHORT,
        "org_hint": "Cooperativa Batán",
    }
