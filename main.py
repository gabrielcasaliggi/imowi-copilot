"""
imowi NOC Copilot — plataforma Agentic AI multitenant (OSS/BSS).
Ejecutar: uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager
from pathlib import Path
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import tickets_store
from app.api.v1.router import api_v1
from app.auth import cargar_tokens_desde_disco
from app.config import (
    APP_TITLE,
    AUTH_SECRET,
    CORS_ORIGINS,
    database_url_enmascarada,
    es_postgres,
    es_produccion,
    supabase_configurado,
    validar_config_produccion,
)
from app.estate.database import Base, get_engine, get_session_factory
from app.estate.health import verificar_database
from app.estate.migrate import migrate_schema
from app.estate.seed import seed_estate, seed_lineas_jsc
import app.estate.models  # noqa: F401 — registra tablas SQLAlchemy
from app.knowledge import cargar_base_conocimiento, estadisticas
from app.routers import auth_router, chat_router, tickets_router

logger = logging.getLogger("imowi")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: Data Estate (SQLite o PostgreSQL) + KB legacy + persistencia tickets."""
    for aviso in validar_config_produccion():
        logger.warning("Config producción: %s", aviso)

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    migrados = migrate_schema(engine)
    if migrados:
        logger.info("Migración schema: %s", migrados)
    with get_session_factory()() as db:
        estate_info = seed_estate(db)
        lineas_info = seed_lineas_jsc(db)
        estate_info["lineas_jsc"] = lineas_info
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
    n_tickets = tickets_store.cargar_tickets_desde_disco()
    backend = (
        "PostgreSQL (Data Estate)"
        if es_postgres()
        else ("Supabase REST" if supabase_configurado() else "JSON local (data/)")
    )
    logger.info(
        "Persistencia [%s]: auth JWT, %s tickets | env=%s",
        backend,
        n_tickets,
        "production" if es_produccion() else "development",
    )
    yield
    logger.info("Apagando imowi NOC Copilot")


app = FastAPI(
    title=APP_TITLE,
    description="Plataforma Agentic AI multitenant — NOC autónomo OSS/BSS",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1)
app.include_router(auth_router.router)
app.include_router(chat_router.router)
app.include_router(tickets_router.router)

_ROOT = Path(__file__).resolve().parent
_STATIC = _ROOT / "static"
if _STATIC.is_dir():
    app.mount("/static", StaticFiles(directory=_STATIC), name="static")


@app.get("/health")
async def health():
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
        "api_v1": "/api/v1",
        "frontend_recomendado": "Next.js",
    }


@app.get("/config.js")
async def config_js():
    path = _ROOT / "config.js"
    if path.exists():
        return FileResponse(path, media_type="application/javascript")
    from fastapi import HTTPException
    raise HTTPException(404, "config.js no encontrado")


@app.get("/")
async def root():
    for candidate in (_ROOT / "index.html", _ROOT / "public" / "index.html"):
        if candidate.exists():
            return FileResponse(candidate)
    kb = estadisticas()
    return {
        "app": APP_TITLE,
        "version": "3.0.0",
        "docs": "/docs",
        "health": "/health",
        "knowledge": kb,
        "api_only": "Frontend en Netlify: configurá IMOWI_API_URL",
    }
