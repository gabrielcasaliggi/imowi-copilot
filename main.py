"""
imowi NOC Copilot — punto de entrada FastAPI.
Ejecutar: uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager
from pathlib import Path
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app import tickets_store
from app.auth import cargar_tokens_desde_disco
from app.config import APP_TITLE, CORS_ORIGINS, es_produccion, supabase_configurado, validar_config_produccion
from app.knowledge import cargar_base_conocimiento, estadisticas
from app.routers import auth_router, chat_router, tickets_router

logger = logging.getLogger("imowi")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: carga e indexación de la base de conocimiento Markdown."""
    for aviso in validar_config_produccion():
        logger.warning("Config producción: %s", aviso)

    try:
        info = cargar_base_conocimiento(Path(__file__).resolve().parent)
        logger.info(
            "Base de conocimiento cargada: %s (%s bloques, %s tokens índice)",
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
    backend = "Supabase" if supabase_configurado() else "JSON local (data/)"
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
    description="Copilot de gestión inteligente de tickets — imowi NOC",
    version="2.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(chat_router.router)
app.include_router(tickets_router.router)

_ROOT = Path(__file__).resolve().parent


@app.get("/health")
async def health():
    kb = getattr(app.state, "knowledge", {})
    return {
        "status": "ok",
        "version": "2.2.0",
        "env": "production" if es_produccion() else "development",
        "knowledge_bloques": kb.get("bloques", 0),
        "supabase": supabase_configurado(),
        "auth": "jwt",
    }


@app.get("/")
async def root():
    for candidate in (_ROOT / "index.html", _ROOT / "public" / "index.html"):
        if candidate.exists():
            return FileResponse(candidate)
    kb = estadisticas()
    return {
        "app": APP_TITLE,
        "version": "2.2.0",
        "docs": "/docs",
        "health": "/health",
        "knowledge": kb,
        "api_only": "Frontend en Netlify: configurá IMOWI_API_URL",
    }
