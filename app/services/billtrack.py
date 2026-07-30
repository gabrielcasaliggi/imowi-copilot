"""BillTrack — Postgres externo de solo lectura (padrón de clientes para el bot).

Independiente del Data Estate. No persistir tickets ni config de plataforma ahí.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus, urlparse

from sqlalchemy.orm import Session


def build_postgres_url(
    *,
    host: str,
    port: int | str = 5432,
    user: str,
    password: str,
    dbname: str,
) -> str:
    """Arma una URL postgresql+psycopg con user/password escapados."""
    host = (host or "").strip()
    user = (user or "").strip()
    dbname = (dbname or "").strip() or "postgres"
    if not host or not user:
        return ""
    try:
        port_n = int(port or 5432)
    except (TypeError, ValueError):
        port_n = 5432
    return (
        f"postgresql+psycopg://{quote_plus(user)}:{quote_plus(password or '')}"
        f"@{host}:{port_n}/{quote_plus(dbname)}"
    )


def parse_postgres_url(url: str) -> dict[str, str]:
    """Extrae host/port/user/dbname de una URL (password no se expone)."""
    raw = (url or "").strip()
    if not raw:
        return {}
    for prefix in ("postgresql+psycopg://", "postgres://"):
        if raw.startswith(prefix):
            raw = "postgresql://" + raw[len(prefix) :]
            break
    try:
        p = urlparse(raw)
    except Exception:
        return {}
    return {
        "host": p.hostname or "",
        "port": str(p.port or 5432),
        "user": p.username or "",
        "dbname": (p.path or "/").lstrip("/") or "postgres",
    }


def connection_params(cfg: dict[str, Any]) -> dict[str, Any]:
    """Resuelve URL + sslmode desde campos discretos o url completa."""
    host = str(cfg.get("host") or "").strip()
    user = str(cfg.get("user") or "").strip()
    password = str(cfg.get("password") or "")
    dbname = str(cfg.get("dbname") or "").strip() or "postgres"
    port = cfg.get("port") or 5432
    sslmode = str(cfg.get("sslmode") or "disable").strip() or "disable"
    url = str(cfg.get("url") or "").strip()

    if host and user and password and "***" not in password:
        url = build_postgres_url(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=dbname,
        )

    return {
        "url": url,
        "sslmode": sslmode,
        "host": host,
        "port": str(port),
        "user": user,
        "dbname": dbname,
    }


def resolve_connection(db: Session | None = None) -> dict[str, Any]:
    from app.services.platform_settings import resolve_billtrack

    cfg = resolve_billtrack(db)
    params = connection_params(cfg)
    params["enabled"] = bool(cfg.get("enabled"))
    return params
