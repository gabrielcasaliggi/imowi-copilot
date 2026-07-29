"""Webhook WhatsApp Cloud API (Meta)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.config import WHATSAPP_DEFAULT_ORG_SLUG, WHATSAPP_VERIFY_TOKEN
from app.estate import repository as repo
from app.estate.database import get_db
from app.services.canal_abonado import procesar_mensaje_entrante
from app.services.platform_settings import resolve_whatsapp

logger = logging.getLogger("operations_hub")

router = APIRouter(tags=["WhatsApp"])


@router.get("/whatsapp/webhook")
def verify_webhook(
    hub_mode: str | None = Query(None, alias="hub.mode"),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(None, alias="hub.challenge"),
    db: Session = Depends(get_db),
):
    expected = resolve_whatsapp(db).get("verify_token") or WHATSAPP_VERIFY_TOKEN
    if hub_mode == "subscribe" and hub_verify_token == expected:
        return PlainTextResponse(content=hub_challenge or "")
    raise HTTPException(403, "Verify token inválido")


@router.post("/whatsapp/webhook")
async def receive_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    org_slug = resolve_whatsapp(db).get("default_org_slug") or WHATSAPP_DEFAULT_ORG_SLUG
    org = repo.get_org_by_slug(db, org_slug)
    if not org:
        logger.error("Org WhatsApp no encontrada: %s", org_slug)
        return {"status": "ok"}

    try:
        entries = payload.get("entry") or []
        for entry in entries:
            for change in entry.get("changes") or []:
                value = change.get("value") or {}
                messages = value.get("messages") or []
                for msg in messages:
                    if msg.get("type") != "text":
                        continue
                    from_wa = msg.get("from") or ""
                    text = (msg.get("text") or {}).get("body") or ""
                    mid = msg.get("id") or ""
                    if not from_wa or not text:
                        continue
                    procesar_mensaje_entrante(
                        db,
                        org.id,
                        telefono=from_wa,
                        texto=text,
                        canal="whatsapp",
                        wa_id=from_wa,
                        meta_message_id=mid,
                        usar_llama=True,
                    )
    except Exception:
        logger.exception("Error procesando webhook WhatsApp")
    # Meta espera 200 rápido
    return {"status": "ok"}
