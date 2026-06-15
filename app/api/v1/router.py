from fastapi import APIRouter

from app.api.v1 import analytics, chat, demo, jsc, kb, telemetry, tenants, tickets

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(chat.router)
api_v1.include_router(demo.router)
api_v1.include_router(jsc.router)
api_v1.include_router(kb.router)
api_v1.include_router(telemetry.router)
api_v1.include_router(tickets.router)
api_v1.include_router(tenants.router)
api_v1.include_router(analytics.router)
