from fastapi import APIRouter

from app.api.v1 import admin, analytics, chat, demo, inbox, jsc, kb, telemetry, tenants, tickets, templates, whatsapp

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(chat.router)
api_v1.include_router(demo.router)
api_v1.include_router(jsc.router)
api_v1.include_router(kb.router)
api_v1.include_router(telemetry.router)
api_v1.include_router(tickets.router)
api_v1.include_router(templates.router)
api_v1.include_router(inbox.router)
api_v1.include_router(whatsapp.router)
api_v1.include_router(tenants.router)
api_v1.include_router(analytics.router)
api_v1.include_router(admin.router)
