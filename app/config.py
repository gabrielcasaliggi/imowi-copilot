import json
import os
from dotenv import load_dotenv

load_dotenv()

AI_BASE_URL = os.getenv("AI_BASE_URL", "http://localhost:11434/v1")
AI_API_KEY = os.getenv("AI_API_KEY", "ollama")
AI_MODEL = os.getenv("AI_MODEL", "llama3.2")

APP_TITLE = "imowi NOC Copilot"
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
DATA_DIR = os.getenv("DATA_DIR", "")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# Supabase (tickets en PostgreSQL — recomendado en producción)
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# Auth JWT (stateless — ideal para Render/Fly sin disco persistente)
AUTH_SECRET = os.getenv("AUTH_SECRET", "")
AUTH_TOKEN_HOURS = int(os.getenv("AUTH_TOKEN_HOURS", "72"))

# RAG
KNOWLEDGE_MIN_SCORE = float(os.getenv("KNOWLEDGE_MIN_SCORE", "0.15"))
KNOWLEDGE_TOP_K = int(os.getenv("KNOWLEDGE_TOP_K", "1"))

ESTADOS_TICKET_VALIDOS = ("Abierto", "En Revisión", "Cerrado")

_DEFAULT_MOCK_USERS = {
    "admin": {
        "password": "admin",
        "rol": "admin",
        "cooperativa": None,
        "nombre": "Administrador NOC",
    },
    "coop_prueba": {
        "password": "prueba",
        "rol": "cooperativa",
        "cooperativa": "Cooperativa Prueba",
        "nombre": "Operador Prueba",
    },
}


def supabase_configurado() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)


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

    return {
        admin_user: {
            "password": admin_pass,
            "rol": "admin",
            "cooperativa": None,
            "nombre": "Administrador NOC",
        },
        coop_user: {
            "password": coop_pass,
            "rol": "cooperativa",
            "cooperativa": coop_cooperativa,
            "nombre": coop_nombre,
        },
    }


MOCK_USERS = _usuarios_desde_env()


def validar_config_produccion() -> list[str]:
    """Advertencias de configuración insegura o incompleta."""
    avisos: list[str] = []
    if not es_produccion():
        return avisos

    if not AUTH_SECRET or AUTH_SECRET in ("change-me", "change-me-in-production"):
        avisos.append("AUTH_SECRET no configurado o inseguro")
    if not supabase_configurado():
        avisos.append("Supabase no configurado — los tickets no persistirán en PostgreSQL")
    if AI_API_KEY in ("", "ollama", "tu-api-key"):
        avisos.append("AI_API_KEY no configurada")
    if CORS_ORIGINS == ["*"]:
        avisos.append("CORS_ORIGINS=* — restringí al dominio de Netlify en producción")

    for user, cred in MOCK_USERS.items():
        pwd = cred.get("password", "")
        if pwd in ("admin", "prueba", "password", "123456"):
            avisos.append(f"Contraseña débil para usuario '{user}'")

    return avisos
