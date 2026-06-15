"""Verificación de conectividad del Data Estate."""

from __future__ import annotations

from sqlalchemy import inspect, text

from app.config import es_postgres
from app.estate.database import get_engine


def verificar_database() -> dict:
    """Ping a la base y conteo básico de tablas clave."""
    out: dict = {
        "connected": False,
        "dialect": "postgresql" if es_postgres() else "sqlite",
    }
    try:
        engine = get_engine()
        insp = inspect(engine)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        out["connected"] = True
        if insp.has_table("organizations"):
            with engine.connect() as conn:
                n = conn.execute(text("SELECT COUNT(*) FROM organizations")).scalar()
            out["organizations"] = int(n or 0)
        if insp.has_table("tickets_estate"):
            with engine.connect() as conn:
                n = conn.execute(text("SELECT COUNT(*) FROM tickets_estate")).scalar()
            out["tickets"] = int(n or 0)
    except Exception as exc:
        out["error"] = str(exc)[:240]
    return out
