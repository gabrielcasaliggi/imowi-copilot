"""
Operations Hub — plataforma Agentic AI multitenant (OSS/BSS).
Ejecutar: uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.estate.models  # noqa: F401 — registra tablas SQLAlchemy
from app import tickets_store
from app.api.v1.router import api_v1
from app.auth import cargar_tokens_desde_disco
from app.config import (
    APP_TITLE,
    AUTH_SECRET,
    CORS_ORIGINS,
    ENABLE_API_DOCS,
    ENABLE_DEMO_RESET,
    ENABLE_LEGACY_API,
    avisos_config_produccion,
    database_url_enmascarada,
    errores_config_produccion,
    es_postgres,
    es_produccion,
    supabase_configurado,
)
from app.estate.database import get_engine, get_session_factory
from app.estate.health import verificar_database
from app.estate.migrate import aplicar_schema
from app.estate.seed import (
    seed_abonados,
    seed_estate,
    seed_inbox_conversaciones,
    seed_kb_batan_servicios,
    seed_lineas_jsc,
)
from app.knowledge import cargar_base_conocimiento, estadisticas
from app.observability import init_sentry, sentry_activo, sentry_risk_accepted
from app.routers import auth_router, chat_router, tickets_router

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s",
    force=True,
)
logging.getLogger("operations_hub").setLevel(logging.INFO)

logger = logging.getLogger("operations_hub")

_SENTRY_OK = init_sentry()
_SENTRY_RISK_ACCEPTED = sentry_risk_accepted()


def cargar_persistencia_tickets_legacy() -> int:
    """JSON/Supabase REST de tickets. Solo si la API legacy está montada."""
    if not ENABLE_LEGACY_API:
        return 0
    return tickets_store.cargar_tickets_desde_disco()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: Data Estate (SQLite o PostgreSQL) + KB legacy + persistencia tickets."""
    fatales = errores_config_produccion()
    if fatales:
        for err in fatales:
            logger.error("Config producción FATAL: %s", err)
        raise RuntimeError(
            "Configuración de production inválida ("
            + "; ".join(fatales)
            + "). Corregí .env o usá ALLOW_INSECURE_PROD=true solo como rescate."
        )
    for aviso in avisos_config_produccion():
        logger.warning("Config producción: %s", aviso)

    engine = get_engine()
    migrados = aplicar_schema(engine)
    if migrados:
        logger.info("Migración schema: %s", migrados)
    with get_session_factory()() as db:
        estate_info = seed_estate(db)
        lineas_info = seed_lineas_jsc(db)
        abonados_info = seed_abonados(db)
        kb_info = seed_kb_batan_servicios(db)
        inbox_info = seed_inbox_conversaciones(db)
        estate_info["lineas_jsc"] = lineas_info
        estate_info["abonados"] = abonados_info
        estate_info["kb_batan"] = kb_info
        estate_info["inbox"] = inbox_info
    logger.info("Data Estate [%s]: %s", database_url_enmascarada(), estate_info)
    app.state.estate = estate_info
    app.state.database_health = verificar_database()
    if not app.state.database_health.get("connected"):
        logger.error(
            "Data Estate sin conexión: %s",
            app.state.database_health.get("error", "desconocido"),
        )

    try:
        info = cargar_base_conocimiento(Path(__file__).resolve().parent)
        logger.info(
            "Base de conocimiento indexada [%s]: %s (%s bloques, %s tokens índice)",
            info.get("modo", "keyword_rag"),
            info["archivo"],
            info["bloques"],
            info["tokens_indice"],
        )
        app.state.knowledge = info
    except FileNotFoundError as e:
        logger.error("No se pudo cargar la base de conocimiento: %s", e)
        app.state.knowledge = {"error": str(e), "bloques": 0}

    cargar_tokens_desde_disco()
    n_tickets = cargar_persistencia_tickets_legacy()
    backend = (
        "PostgreSQL (Data Estate)"
        if es_postgres()
        else ("Supabase REST" if supabase_configurado() else "JSON local (data/)")
    )
    logger.info(
        "Persistencia [%s]: auth JWT, legacy_tickets=%s | env=%s | ENABLE_LEGACY_API=%s",
        backend,
        n_tickets,
        "production" if es_produccion() else "development",
        ENABLE_LEGACY_API,
    )
    yield
    logger.info("Apagando Operations Hub")


app = FastAPI(
    title=APP_TITLE,
    description="Plataforma Agentic AI multitenant — NOC autónomo OSS/BSS",
    version="3.0.0",
    lifespan=lifespan,
    docs_url="/docs" if ENABLE_API_DOCS else None,
    redoc_url="/redoc" if ENABLE_API_DOCS else None,
    openapi_url="/openapi.json" if ENABLE_API_DOCS else None,
)

_cors_wildcard = CORS_ORIGINS == ["*"] or "*" in CORS_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _cors_wildcard else CORS_ORIGINS,
    # Credenciales (cookies) requieren orígenes explícitos — no compatibles con *
    allow_credentials=not _cors_wildcard,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1)
app.include_router(auth_router.router)
# HTML Copilot + /api/tickets JSON: solo si ENABLE_LEGACY_API (off en production).
if ENABLE_LEGACY_API:
    app.include_router(tickets_router.router)
    app.include_router(chat_router.router)


@app.get("/health")
async def health():
    """Liveness: el proceso responde. No fallar solo porque la DB esté caída."""
    kb = getattr(app.state, "knowledge", {})
    estate = getattr(app.state, "estate", {})
    db_health = getattr(app.state, "database_health", None) or verificar_database()
    prod = es_produccion()
    status = "ok"
    if prod and es_postgres() and not db_health.get("connected"):
        status = "degraded"
    return {
        "status": status,
        "version": "3.0.0",
        "env": "production" if prod else "development",
        "estate": True,
        "estate_seeded": estate.get("seeded"),
        "database": "postgresql" if es_postgres() else "sqlite",
        "database_connected": db_health.get("connected", False),
        "database_organizations": db_health.get("organizations"),
        "database_tickets": db_health.get("tickets"),
        "knowledge_bloques": kb.get("bloques", 0),
        "supabase_mirror": supabase_configurado() and not es_postgres(),
        "auth": "jwt",
        "auth_secret_configured": bool(AUTH_SECRET),
        "sentry_configured": bool(_SENTRY_OK) or sentry_activo(),
        "sentry_risk_accepted": bool(_SENTRY_RISK_ACCEPTED),
        "demo_reset_enabled": ENABLE_DEMO_RESET,
        "api_v1": "/api/v1",
        "frontend_recomendado": "Next.js",
        "ready": "/ready",
    }


@app.get("/ready")
async def ready():
    """Readiness: apto para tráfico. 503 si la DB no responde."""
    from fastapi.responses import JSONResponse

    db_health = verificar_database()
    connected = bool(db_health.get("connected"))
    body = {
        "ready": connected,
        "database_connected": connected,
        "database": "postgresql" if es_postgres() else "sqlite",
        "env": "production" if es_produccion() else "development",
    }
    if not connected:
        body["error"] = db_health.get("error", "database unavailable")
        return JSONResponse(status_code=503, content=body)
    return body


@app.get("/")
async def root():
    kb = estadisticas()
    return {
        "app": APP_TITLE,
        "version": "3.0.0",
        "docs": "/docs" if ENABLE_API_DOCS else None,
        "health": "/health",
        "knowledge": kb,
        "frontend": "Next.js (puerto 3000 / nginx)",
        "api_v1": "/api/v1",
    }
