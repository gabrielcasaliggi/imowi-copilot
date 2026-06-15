import json
import os
import re
from dotenv import load_dotenv

load_dotenv()


def normalizar_database_url(url: str) -> str:
    """Acepta postgres:// o postgresql:// y lo convierte a driver SQLAlchemy."""
    u = (url or "").strip()
    if not u:
        return "sqlite:///./data/estate.db"
    if u.startswith("postgres://"):
        return "postgresql+psycopg://" + u[len("postgres://") :]
    if u.startswith("postgresql://") and "+psycopg" not in u:
        return "postgresql+psycopg://" + u[len("postgresql://") :]
    return u


def database_url_enmascarada(url: str | None = None) -> str:
    """Oculta credenciales en logs."""
    u = url or DATABASE_URL
    return re.sub(r":([^:@/]+)@", ":***@", u, count=1)


AI_BASE_URL = os.getenv("AI_BASE_URL", "http://localhost:11434/v1")
AI_API_KEY = os.getenv("AI_API_KEY", "ollama")
AI_MODEL = os.getenv("AI_MODEL", "llama3.2")

APP_TITLE = "imowi NOC Copilot"
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
DATA_DIR = os.getenv("DATA_DIR", "")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# Supabase — API REST (espejo legacy de tickets; opcional si DATABASE_URL ya es Postgres)
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# Auth JWT (stateless — ideal para Render/Fly sin disco persistente)
AUTH_SECRET = os.getenv("AUTH_SECRET", "")
AUTH_TOKEN_HOURS = int(os.getenv("AUTH_TOKEN_HOURS", "72"))

# RAG — búsqueda por keywords (no inyectar la KB completa al prompt)
KNOWLEDGE_MIN_SCORE = float(os.getenv("KNOWLEDGE_MIN_SCORE", "0.15"))
KNOWLEDGE_TOP_K = int(os.getenv("KNOWLEDGE_TOP_K", "1"))
ANOMALY_TTL_MINUTES = int(os.getenv("ANOMALY_TTL_MINUTES", "30"))

# Data Estate — SQLite local o PostgreSQL (Supabase) en producción
DATABASE_URL = normalizar_database_url(os.getenv("DATABASE_URL", "sqlite:///./data/estate.db"))
DATABASE_SSLMODE = os.getenv("DATABASE_SSLMODE", "require")
KNOWLEDGE_MAX_FRAGMENT_CHARS = int(os.getenv("KNOWLEDGE_MAX_FRAGMENT_CHARS", "1800"))
KNOWLEDGE_MAX_SYSTEM_TOKENS = int(os.getenv("KNOWLEDGE_MAX_SYSTEM_TOKENS", "4500"))

ESTADOS_TICKET_VALIDOS = ("Abierto", "En Revisión", "Cerrado")

_DEFAULT_MOCK_USERS = {
    "admin": {
        "password": "admin",
        "rol": "admin",
        "cooperativa": None,
        "nombre": "NOC imowi — Administrador",
        "org_slug": "imowi",
    },
    "batan": {
        "password": "batan",
        "rol": "cooperativa",
        "cooperativa": "Cooperativa Batán",
        "nombre": "Operador Coop Batán",
        "org_slug": "coop-batan",
    },
    "viamonte": {
        "password": "viamonte",
        "rol": "cooperativa",
        "cooperativa": "Cooperativa Viamonte",
        "nombre": "Operador Coop Viamonte",
        "org_slug": "coop-viamonte",
    },
    "coop_prueba": {
        "password": "prueba",
        "rol": "cooperativa",
        "cooperativa": "Cooperativa Prueba",
        "nombre": "Operador Prueba",
        "org_slug": "coop-batan",
    },
}


def es_mirror_supabase_activo() -> bool:
    """Mirror REST legacy solo cuando Postgres no es la fuente principal."""
    return supabase_configurado() and not es_postgres()


def supabase_configurado() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)


def es_postgres() -> bool:
    return DATABASE_URL.startswith("postgresql")


def es_sqlite() -> bool:
    return DATABASE_URL.startswith("sqlite")


def es_produccion() -> bool:
    return APP_ENV in ("production", "prod")


def _usuarios_desde_env() -> dict:
    """Usuarios demo configurables por variables de entorno."""
    raw = os.getenv("MOCK_USERS_JSON", "").strip()
    if raw:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("MOCK_USERS_JSON debe ser un objeto JSON")
        return parsed

    admin_user = os.getenv("ADMIN_USER", "admin")
    admin_pass = os.getenv("ADMIN_PASSWORD", "admin")
    coop_user = os.getenv("COOP_USER", "coop_prueba")
    coop_pass = os.getenv("COOP_PASSWORD", "prueba")
    coop_nombre = os.getenv("COOP_NOMBRE", "Operador Prueba")
    coop_cooperativa = os.getenv("COOP_COOPERATIVA", "Cooperativa Prueba")

    users = {
        admin_user: {
            "password": admin_pass,
            "rol": "admin",
            "cooperativa": None,
            "nombre": "NOC imowi — Administrador",
            "org_slug": "imowi",
        },
        coop_user: {
            "password": coop_pass,
            "rol": "cooperativa",
            "cooperativa": coop_cooperativa,
            "nombre": coop_nombre,
            "org_slug": "coop-batan",
        },
    }
    for user, cred in _DEFAULT_MOCK_USERS.items():
        users.setdefault(user, cred)
    return users


MOCK_USERS = _usuarios_desde_env()


def validar_config_produccion() -> list[str]:
    """Advertencias de configuración insegura o incompleta."""
    avisos: list[str] = []
    if not es_produccion():
        return avisos

    if not AUTH_SECRET or AUTH_SECRET in ("change-me", "change-me-in-production"):
        avisos.append("AUTH_SECRET no configurado o inseguro")
    if not es_postgres():
        avisos.append(
            "DATABASE_URL no apunta a PostgreSQL — en producción usá Supabase "
            "(Settings → Database → Connection string URI)"
        )
    elif not supabase_configurado():
        avisos.append(
            "SUPABASE_URL/SERVICE_KEY opcionales si DATABASE_URL ya es Postgres del mismo proyecto"
        )
    if AI_API_KEY in ("", "ollama", "tu-api-key"):
        avisos.append("AI_API_KEY no configurada")
    if CORS_ORIGINS == ["*"]:
        avisos.append("CORS_ORIGINS=* — restringí al dominio de Netlify en producción")

    for user, cred in MOCK_USERS.items():
        pwd = cred.get("password", "")
        if pwd in ("admin", "prueba", "password", "123456"):
            avisos.append(f"Contraseña débil para usuario '{user}'")

    return avisos
