"""Verificación de conectividad del Data Estate."""

from __future__ import annotations

import time

from sqlalchemy import create_engine, inspect, text

from app.config import (
    DATABASE_SSLMODE,
    DATABASE_URL,
    database_url_enmascarada,
    es_postgres,
    normalizar_database_url,
)
from app.estate.database import get_engine, postgres_connect_args


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


def probar_conexion_database(
    url: str | None = None,
    *,
    sslmode: str | None = None,
) -> dict:
    """Prueba real de conectividad (SELECT 1) sin alterar el engine global.

    Si `url` es None/vacía, usa la DATABASE_URL activa del proceso.
    """
    raw = (url or "").strip() or DATABASE_URL
    normalized = normalizar_database_url(raw)
    is_pg = normalized.startswith("postgresql")
    testing_active = not (url or "").strip()
    if sslmode is not None and str(sslmode).strip():
        mode = str(sslmode).strip()
    elif testing_active:
        mode = (DATABASE_SSLMODE or "require").strip() or "require"
    else:
        # BillTrack / externos on-prem: sin TLS por defecto
        mode = "disable"
    out: dict = {
        "ok": False,
        "connected": False,
        "dialect": "postgresql" if is_pg else "sqlite",
        "url_masked": database_url_enmascarada(normalized),
        "sslmode": mode if is_pg else None,
        "latency_ms": None,
        "server_version": None,
        "current_database": None,
        "current_user": None,
    }

    engine = None
    t0 = time.perf_counter()
    try:
        if is_pg:
            connect_args = {
                **postgres_connect_args(),
                "sslmode": mode,
                "connect_timeout": 8,
            }
            engine = create_engine(
                normalized,
                pool_pre_ping=True,
                connect_args=connect_args,
            )
        else:
            engine = create_engine(
                normalized,
                connect_args={"check_same_thread": False},
            )

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            if is_pg:
                row = conn.execute(
                    text(
                        "SELECT current_database(), current_user, "
                        "current_setting('server_version')"
                    )
                ).one()
                out["current_database"] = str(row[0])
                out["current_user"] = str(row[1])
                out["server_version"] = str(row[2])[:80]
            else:
                out["current_database"] = "sqlite"
                out["current_user"] = "local"

        out["ok"] = True
        out["connected"] = True
        out["latency_ms"] = int((time.perf_counter() - t0) * 1000)
    except Exception as exc:
        out["latency_ms"] = int((time.perf_counter() - t0) * 1000)
        err = str(exc)[:240]
        out["error"] = err
        low = err.lower()
        if "does not support ssl" in low or "ssl was required" in low:
            out["hint"] = "Este servidor no soporta SSL. Usá sslmode=disable."
        elif "timeout" in low:
            out["hint"] = (
                "Timeout de red: el API no alcanza ese host (hace falta VPN/WireGuard en la "
                "máquina del backend). Un deploy en Render/cloud no llega a IPs internas."
            )
        elif "password authentication failed" in low:
            out["hint"] = "Credenciales rechazadas: revisá usuario/contraseña."
        elif "database" in low and ("does not exist" in low or "no existe" in low):
            out["hint"] = "El nombre de la base (dbname) no existe en ese servidor."
    finally:
        if engine is not None:
            engine.dispose()
    return out
