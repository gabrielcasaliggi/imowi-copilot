"""Data Estate — SQLite (dev) o PostgreSQL/Supabase (producción)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_SSLMODE, DATABASE_URL, es_postgres

_engine = None
_SessionLocal = None


class Base(DeclarativeBase):
    pass


def _sqlite_path() -> Path:
    url = DATABASE_URL
    if url.startswith("sqlite:///"):
        raw = url.replace("sqlite:///", "", 1)
        return Path(raw).resolve()
    return Path("data/estate.db").resolve()


def postgres_connect_args() -> dict:
    """Opciones psycopg3 para Postgres gestionado (Supabase/PgBouncer en :6543)."""
    return {
        "sslmode": DATABASE_SSLMODE,
        # PgBouncer en modo transaction no soporta prepared statements de psycopg3.
        "prepare_threshold": None,
    }


def get_engine():
    global _engine
    if _engine is None:
        if es_postgres():
            _engine = create_engine(
                DATABASE_URL,
                pool_pre_ping=True,
                pool_recycle=280,
                connect_args=postgres_connect_args(),
            )
        else:
            path = _sqlite_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            _engine = create_engine(
                DATABASE_URL,
                connect_args={"check_same_thread": False},
            )

            @event.listens_for(_engine, "connect")
            def _fk(dbapi_conn, _):
                dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
    return _SessionLocal


def get_db():
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
