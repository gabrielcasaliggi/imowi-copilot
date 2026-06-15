"""Configuración de DATABASE_URL para SQLite y PostgreSQL."""

from app.config import database_url_enmascarada, normalizar_database_url


def test_normalizar_postgres_uri():
    url = "postgres://user:secret@host:6543/db"
    assert normalizar_database_url(url) == "postgresql+psycopg://user:secret@host:6543/db"


def test_normalizar_postgresql_uri():
    url = "postgresql://user:secret@host:5432/db"
    assert normalizar_database_url(url) == "postgresql+psycopg://user:secret@host:5432/db"


def test_normalizar_no_toca_driver_explicito():
    url = "postgresql+psycopg://user:secret@host/db"
    assert normalizar_database_url(url) == url


def test_database_url_enmascarada():
    url = "postgresql+psycopg://user:supersecret@host:6543/postgres"
    assert database_url_enmascarada(url) == "postgresql+psycopg://user:***@host:6543/postgres"


def test_normalizar_quita_pgbouncer_prisma():
    url = "postgresql://user:secret@host:6543/postgres?pgbouncer=true"
    assert normalizar_database_url(url) == "postgresql+psycopg://user:secret@host:6543/postgres"


def test_normalizar_quita_comillas_y_prefijo():
    url = 'DATABASE_URL="postgresql://user:secret@host:6543/postgres?pgbouncer=true"'
    assert normalizar_database_url(url) == "postgresql+psycopg://user:secret@host:6543/postgres"


def test_mirror_supabase_desactivado_con_postgres(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setattr(config, "SUPABASE_SERVICE_KEY", "key")
    monkeypatch.setattr(
        config,
        "DATABASE_URL",
        "postgresql+psycopg://user:pass@host:6543/db",
    )
    assert config.es_postgres() is True
    assert config.es_mirror_supabase_activo() is False


def test_postgres_connect_args_desactiva_prepared_statements():
    from app.estate.database import postgres_connect_args

    args = postgres_connect_args()
    assert args["prepare_threshold"] is None
    assert "sslmode" in args


def test_mirror_supabase_activo_sin_postgres(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setattr(config, "SUPABASE_SERVICE_KEY", "key")
    monkeypatch.setattr(config, "DATABASE_URL", "sqlite:///./data/estate.db")
    assert config.es_mirror_supabase_activo() is True
