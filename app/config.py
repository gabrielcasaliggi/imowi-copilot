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

    # Comillas o prefijo accidental al copiar desde Supabase/Prisma/Render
    for _ in range(2):
        if len(u) >= 2 and u[0] == u[-1] and u[0] in ("'", '"'):
            u = u[1:-1].strip()
    if u.upper().startswith("DATABASE_URL="):
        u = u.split("=", 1)[1].strip()
        if len(u) >= 2 and u[0] == u[-1] and u[0] in ("'", '"'):
            u = u[1:-1].strip()

    # Parámetros de Prisma no válidos para psycopg/SQLAlchemy
    for suffix in ("?pgbouncer=true", "&pgbouncer=true", "?pgbouncer=false", "&pgbouncer=false"):
        if suffix in u.lower():
            u = u[: u.lower().index(suffix)] + u[u.lower().index(suffix) + len(suffix) :]
    u = u.rstrip("?&")

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

APP_TITLE = "Operations Hub"
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
AUTH_TOKEN_HOURS = int(os.getenv("AUTH_TOKEN_HOURS", "12"))
CONSOLE_JWT_AUD = os.getenv("CONSOLE_JWT_AUD", "ops-hub-console")
PORTAL_AUTH_SECRET = os.getenv("PORTAL_AUTH_SECRET", "").strip()
PORTAL_JWT_AUD = os.getenv("PORTAL_JWT_AUD", "ops-hub-portal")
PORTAL_TOKEN_HOURS = float(os.getenv("PORTAL_TOKEN_HOURS", "4"))
PORTAL_AUTH_MODE = os.getenv("PORTAL_AUTH_MODE", "dni_otp").strip().lower()
# Guest anónimo: en production off por defecto (forzá true solo si lo necesitás en piloto)
_raw_portal_guest = os.getenv("PORTAL_ALLOW_GUEST")
if _raw_portal_guest is None:
    PORTAL_ALLOW_GUEST = APP_ENV not in ("production", "prod")
else:
    PORTAL_ALLOW_GUEST = _raw_portal_guest.strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
# UI/API Copilot HTML legacy (/api/chat sin auth). Off en production salvo override.
_raw_legacy = os.getenv("ENABLE_LEGACY_API")
if _raw_legacy is None:
    ENABLE_LEGACY_API = APP_ENV not in ("production", "prod")
else:
    ENABLE_LEGACY_API = _raw_legacy.strip().lower() in ("1", "true", "yes", "on")
# Swagger/OpenAPI público
_raw_api_docs = os.getenv("ENABLE_API_DOCS")
if _raw_api_docs is None:
    ENABLE_API_DOCS = APP_ENV not in ("production", "prod")
else:
    ENABLE_API_DOCS = _raw_api_docs.strip().lower() in ("1", "true", "yes", "on")
DISABLE_DEMO_USERS = os.getenv("DISABLE_DEMO_USERS", "").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
# POST /api/v1/demo/reset — en production OFF por defecto (destruye tickets del tenant)
_raw_demo_reset = os.getenv("ENABLE_DEMO_RESET")
if _raw_demo_reset is None:
    ENABLE_DEMO_RESET = APP_ENV not in ("production", "prod")
else:
    ENABLE_DEMO_RESET = _raw_demo_reset.strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
DNI_PEPPER = os.getenv("DNI_PEPPER", "").strip() or AUTH_SECRET or "dev-dni-pepper"

# SMTP (invites consola + OTP portal)
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or "587")
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "").strip() or SMTP_USER
SMTP_TLS = os.getenv("SMTP_TLS", "true").strip().lower() in ("1", "true", "yes", "on")
SMTP_SSL = os.getenv("SMTP_SSL", "false").strip().lower() in ("1", "true", "yes", "on")
PUBLIC_URL = os.getenv("PUBLIC_URL", os.getenv("DOMAIN", "")).strip().rstrip("/")
if PUBLIC_URL and not PUBLIC_URL.startswith("http"):
    PUBLIC_URL = f"https://{PUBLIC_URL}"

# Branding — asistente abonado (N1 canal). No confundir con Copilot NOC.
BOT_DISPLAY_NAME = (os.getenv("BOT_DISPLAY_NAME", "Eko") or "Eko").strip() or "Eko"
BOT_DISPLAY_NAME_SHORT = (
    os.getenv("BOT_DISPLAY_NAME_SHORT", "") or BOT_DISPLAY_NAME
).strip().upper() or "EKO"
# Producto abonado (portal / WhatsApp). Consola ops sigue siendo APP_TITLE (Operations Hub).
PRODUCT_DISPLAY_NAME = (
    os.getenv("PRODUCT_DISPLAY_NAME", "Soporte Batán") or "Soporte Batán"
).strip() or "Soporte Batán"
# Prefijo de IDs de ticket (antes JSC-; legacy JSC-* se sigue contando para secuencia).
TICKET_ID_PREFIX = (
    os.getenv("TICKET_ID_PREFIX", "IBOT") or "IBOT"
).strip().upper().rstrip("-") or "IBOT"

# OTP portal
OTP_LENGTH = int(os.getenv("OTP_LENGTH", "6") or "6")
OTP_TTL_MINUTES = int(os.getenv("OTP_TTL_MINUTES", "10") or "10")
OTP_MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", "5") or "5")

# Login rate-limit / lockout
AUTH_LOGIN_MAX_FAILURES = int(os.getenv("AUTH_LOGIN_MAX_FAILURES", "5") or "5")
AUTH_LOGIN_WINDOW_MINUTES = int(os.getenv("AUTH_LOGIN_WINDOW_MINUTES", "15") or "15")
AUTH_LOCKOUT_MINUTES = int(os.getenv("AUTH_LOCKOUT_MINUTES", "30") or "30")

# BillTrack lookup (SQL parametrizado, solo SELECT)
BILLTRACK_LOOKUP_SQL = os.getenv("BILLTRACK_LOOKUP_SQL", "").strip()
BILLTRACK_LOOKUP_READY = os.getenv("BILLTRACK_LOOKUP_READY", "").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# RAG — búsqueda por keywords (no inyectar la KB completa al prompt)
KNOWLEDGE_MIN_SCORE = float(os.getenv("KNOWLEDGE_MIN_SCORE", "0.15"))
KNOWLEDGE_TOP_K = int(os.getenv("KNOWLEDGE_TOP_K", "1"))
ANOMALY_TTL_MINUTES = int(os.getenv("ANOMALY_TTL_MINUTES", "30"))

# Data Estate — SQLite local o PostgreSQL (Supabase) en producción
# (tickets, config, canal, KB — NO es el padrón BillTrack de clientes)
DATABASE_URL = normalizar_database_url(os.getenv("DATABASE_URL", "sqlite:///./data/estate.db"))
DATABASE_SSLMODE = os.getenv("DATABASE_SSLMODE", "require")

# BillTrack — Postgres externo de solo lectura para que el bot consulte clientes
# (separado del Data Estate; no escribir tickets/config ahí)
BILLTRACK_DATABASE_URL = normalizar_database_url(os.getenv("BILLTRACK_DATABASE_URL", "")) if os.getenv(
    "BILLTRACK_DATABASE_URL", ""
).strip() else ""
BILLTRACK_SSLMODE = os.getenv("BILLTRACK_SSLMODE", "disable").strip() or "disable"
BILLTRACK_HOST = os.getenv("BILLTRACK_HOST", "").strip()
BILLTRACK_PORT = os.getenv("BILLTRACK_PORT", "5432").strip() or "5432"
BILLTRACK_USER = os.getenv("BILLTRACK_USER", "").strip()
BILLTRACK_PASSWORD = os.getenv("BILLTRACK_PASSWORD", "")
BILLTRACK_DBNAME = os.getenv("BILLTRACK_DBNAME", "billtrack").strip() or "billtrack"
BILLTRACK_ENABLED = os.getenv("BILLTRACK_ENABLED", "false").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# Radius / NAS API (Batan) — estado PPPoE para el bot
RADIUS_API_BASE_URL = os.getenv(
    "RADIUS_API_BASE_URL", "https://radius.api.batan.coop"
).strip() or "https://radius.api.batan.coop"
RADIUS_API_KEY = os.getenv("RADIUS_API_KEY", "").strip()
RADIUS_API_TOKEN = os.getenv("RADIUS_API_TOKEN", "").strip()
RADIUS_API_ENABLED = os.getenv("RADIUS_API_ENABLED", "false").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
try:
    RADIUS_API_TIMEOUT = float(os.getenv("RADIUS_API_TIMEOUT", "8") or "8")
except (TypeError, ValueError):
    RADIUS_API_TIMEOUT = 8.0

KNOWLEDGE_MAX_FRAGMENT_CHARS = int(os.getenv("KNOWLEDGE_MAX_FRAGMENT_CHARS", "1800"))
KNOWLEDGE_MAX_SYSTEM_TOKENS = int(os.getenv("KNOWLEDGE_MAX_SYSTEM_TOKENS", "4500"))

# WhatsApp Cloud API (Meta)
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "").strip()
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "ops-hub-wa-verify").strip()
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "").strip()
# Org por defecto para webhook (slug cooperativa)
WHATSAPP_DEFAULT_ORG_SLUG = os.getenv("WHATSAPP_DEFAULT_ORG_SLUG", "coop-batan").strip()

# Telegram Bot API
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
TELEGRAM_DEFAULT_ORG_SLUG = os.getenv("TELEGRAM_DEFAULT_ORG_SLUG", "coop-batan").strip()

# Whisper STT (contenedor aislado; backend nativo apunta a localhost)
# Levantar: docker compose -f docker-compose.whisper.yml up -d --build
WHISPER_URL = os.getenv("WHISPER_URL", "http://localhost:9000").strip().rstrip("/")
WHISPER_ENABLED = os.getenv("WHISPER_ENABLED", "false").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
try:
    WHISPER_TIMEOUT_S = float(os.getenv("WHISPER_TIMEOUT_S", "30") or "30")
except ValueError:
    WHISPER_TIMEOUT_S = 30.0

# Piper TTS (contenedor aislado; respuesta en audio WA si el abonado mandó nota de voz)
# Levantar: docker compose -f docker-compose.tts.yml up -d --build
TTS_URL = os.getenv("TTS_URL", "http://localhost:9100").strip().rstrip("/")
TTS_ENABLED = os.getenv("TTS_ENABLED", "false").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
try:
    TTS_TIMEOUT_S = float(os.getenv("TTS_TIMEOUT_S", "45") or "45")
except ValueError:
    TTS_TIMEOUT_S = 45.0

ESTADOS_TICKET_VALIDOS = ("Abierto", "En Revisión", "Cerrado")

_DEFAULT_MOCK_USERS = {
    "admin": {
        "password": "admin",
        "rol": "admin",
        "cooperativa": None,
        "nombre": "Administración Batán",
        "org_slug": "imowi",
    },
    "batan": {
        "password": "batan",
        "rol": "agente",
        "cooperativa": "Cooperativa Batán",
        "nombre": "Agente Batán",
        "org_slug": "coop-batan",
    },
    "supervisor": {
        "password": "supervisor",
        "rol": "supervisor",
        "cooperativa": "Cooperativa Batán",
        "nombre": "Supervisor Batán",
        "org_slug": "coop-batan",
    },
    "ejecutivo": {
        "password": "ejecutivo",
        "rol": "ejecutivo",
        "cooperativa": "Cooperativa Batán",
        "nombre": "Ejecutivo Batán",
        "org_slug": "coop-batan",
    },
    "viamonte": {
        "password": "viamonte",
        "rol": "agente",
        "cooperativa": "Cooperativa Viamonte",
        "nombre": "Agente Viamonte",
        "org_slug": "coop-viamonte",
    },
    "coop_prueba": {
        "password": "prueba",
        "rol": "agente",
        "cooperativa": "Cooperativa Prueba",
        "nombre": "Agente Prueba",
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


def demo_users_disabled() -> bool:
    """En production los MOCK_USERS están desactivados salvo override explícito."""
    if DISABLE_DEMO_USERS:
        return True
    if es_produccion():
        # En prod: desactivar a menos que DISABLE_DEMO_USERS=false explícito
        raw = os.getenv("DISABLE_DEMO_USERS", "").strip().lower()
        if raw in ("0", "false", "no", "off"):
            return False
        return True
    return False


def _usuarios_desde_env() -> dict:
    """Usuarios demo configurables por variables de entorno."""
    if demo_users_disabled():
        return {}

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
            "nombre": "Administración",
            "org_slug": "imowi",
        },
        coop_user: {
            "password": coop_pass,
            "rol": "agente",
            "cooperativa": coop_cooperativa,
            "nombre": coop_nombre,
            "org_slug": "coop-batan",
        },
    }
    for user, cred in _DEFAULT_MOCK_USERS.items():
        users.setdefault(user, cred)
    return users


MOCK_USERS = _usuarios_desde_env()


_AUTH_SECRETS_DEBILES = frozenset(
    {
        "",
        "change-me",
        "change-me-in-production",
        "secret",
        "password",
        "ci-test-auth-secret-min-32-chars!!",
        "ci-test-portal-secret-min-32!!",
    }
)


def allow_insecure_prod() -> bool:
    """Escape hatch de emergencia: ALLOW_INSECURE_PROD=true (solo rescate)."""
    return os.getenv("ALLOW_INSECURE_PROD", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def errores_config_produccion() -> list[str]:
    """Errores fatales: la API no debe arrancar en production con estos.

    Avisos no bloqueantes: ver `avisos_config_produccion`.
    Override de emergencia: ALLOW_INSECURE_PROD=true.
    """
    errores: list[str] = []
    if not es_produccion():
        return errores
    if allow_insecure_prod():
        return errores

    secret = (AUTH_SECRET or "").strip()
    if not secret or secret in _AUTH_SECRETS_DEBILES or len(secret) < 32:
        errores.append(
            "AUTH_SECRET ausente, débil o corto (<32) — generá uno con openssl rand -hex 32"
        )
    portal_sec = (PORTAL_AUTH_SECRET or "").strip()
    if not portal_sec or portal_sec in _AUTH_SECRETS_DEBILES or len(portal_sec) < 32:
        errores.append(
            "PORTAL_AUTH_SECRET ausente, débil o corto (<32) — distinto de AUTH_SECRET"
        )
    elif portal_sec == secret:
        errores.append("PORTAL_AUTH_SECRET debe ser distinto de AUTH_SECRET")
    if not es_postgres():
        errores.append(
            "DATABASE_URL debe ser PostgreSQL en production (no SQLite)"
        )
    if CORS_ORIGINS == ["*"] or not CORS_ORIGINS:
        errores.append(
            "CORS_ORIGINS=* o vacío — restringí al dominio público (ej. https://ibot.ecolan.com)"
        )
    if MOCK_USERS or not demo_users_disabled():
        errores.append(
            "Usuarios demo activos — set DISABLE_DEMO_USERS=true"
        )
    if ENABLE_DEMO_RESET:
        errores.append(
            "ENABLE_DEMO_RESET=true — peligroso en production (set false)"
        )
    return errores


def avisos_config_produccion() -> list[str]:
    """Advertencias no bloqueantes de configuración incompleta."""
    avisos: list[str] = []
    if not es_produccion():
        return avisos

    if allow_insecure_prod():
        avisos.append(
            "ALLOW_INSECURE_PROD=true — fail-fast desactivado (solo rescate temporal)"
        )
    if es_postgres() and not supabase_configurado():
        avisos.append(
            "SUPABASE_URL/SERVICE_KEY opcionales si DATABASE_URL ya es Postgres del mismo proyecto"
        )
    if AI_API_KEY in ("", "ollama", "tu-api-key"):
        avisos.append("AI_API_KEY no configurada")
    if not SMTP_HOST:
        avisos.append("SMTP_HOST no configurado — invites/OTP por email no funcionarán")
    if PORTAL_ALLOW_GUEST:
        avisos.append("PORTAL_ALLOW_GUEST=true — guest anónimo habilitado en production")
    if ENABLE_LEGACY_API:
        avisos.append("ENABLE_LEGACY_API=true — /api/chat legacy expuesto sin endurecer")
    if ENABLE_API_DOCS:
        avisos.append("ENABLE_API_DOCS=true — /docs y OpenAPI públicos")
    if WHATSAPP_TOKEN and not WHATSAPP_APP_SECRET:
        avisos.append("WHATSAPP_APP_SECRET vacío con token WA — webhook sin firma HMAC")
    if WHATSAPP_TOKEN and not WHATSAPP_VERIFY_TOKEN:
        avisos.append("WHATSAPP_VERIFY_TOKEN vacío — Meta no podrá verificar el webhook")
    if not WHATSAPP_TOKEN:
        avisos.append(
            "WHATSAPP_TOKEN vacío — canal WhatsApp no operativo (OK si aún no lo usan)"
        )
    if TELEGRAM_BOT_TOKEN and not TELEGRAM_WEBHOOK_SECRET:
        avisos.append("TELEGRAM_WEBHOOK_SECRET vacío con bot token — webhook sin secret token")
    if not (os.getenv("SENTRY_DSN") or "").strip():
        if os.getenv("SENTRY_RISK_ACCEPTED", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        ):
            avisos.append(
                "SENTRY_DSN vacío con SENTRY_RISK_ACCEPTED=true — sin reporte de errores"
            )
        else:
            avisos.append(
                "SENTRY_DSN vacío — errores de prod no se reportan a Sentry "
                "(o set SENTRY_RISK_ACCEPTED=true)"
            )

    return avisos


def validar_config_produccion() -> list[str]:
    """Compat: errores fatales + avisos (para logs). Preferí errores_/avisos_ separados."""
    return errores_config_produccion() + avisos_config_produccion()
