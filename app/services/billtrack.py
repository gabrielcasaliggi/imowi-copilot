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


def preflight_tcp(host: str, port: int | str = 5432, *, timeout: float = 5.0) -> dict:
    """Comprueba si host:port es alcanzable a nivel TCP (antes de autenticar)."""
    import socket

    host = (host or "").strip()
    try:
        port_n = int(port or 5432)
    except (TypeError, ValueError):
        port_n = 5432
    out: dict = {"host": host, "port": port_n, "tcp_ok": False}
    if not host:
        out["error"] = "host vacío"
        return out
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port_n))
        out["tcp_ok"] = True
    except OSError as exc:
        out["error"] = str(exc)[:160]
        err = str(exc).lower()
        if "unreachable" in err or "timed out" in err or "timeout" in err:
            out["hint"] = (
                "El API no alcanza ese host:puerto. BillTrack suele estar solo en la red "
                "interna/VPN (p. ej. WireGuard). Corré el backend en una máquina con VPN "
                "conectada — un deploy en Render/cloud no puede llegar a esa IP."
            )
    finally:
        sock.close()
    return out


def resolve_connection(db: Session | None = None) -> dict[str, Any]:
    from app.services.platform_settings import resolve_billtrack

    cfg = resolve_billtrack(db)
    params = connection_params(cfg)
    params["enabled"] = bool(cfg.get("enabled"))
    return params


def lookup_abonado_por_dni(
    dni: str,
    *,
    org_slug: str = "",
    linea: str = "",
    db: Session | None = None,
) -> dict[str, Any] | None:
    """Consulta padrón BillTrack (RO). Retorna dict o None.

    SQL configurable vía BILLTRACK_LOOKUP_SQL con placeholders :dni, :org_slug, :linea.
    Columnas esperadas (aliases): ref, email, telefono, activo, nombre.
    """
    from app.config import (
        BILLTRACK_ENABLED,
        BILLTRACK_LOOKUP_READY,
        BILLTRACK_LOOKUP_SQL,
        BILLTRACK_SSLMODE,
        es_produccion,
    )
    from app.estate.security import normalizar_dni, valid_dni_ar

    dni_n = normalizar_dni(dni)
    if not valid_dni_ar(dni_n):
        return None

    # Mock en non-prod cuando no hay BillTrack real
    if not BILLTRACK_ENABLED or not BILLTRACK_LOOKUP_READY:
        if es_produccion():
            return None
        return _mock_lookup(dni_n, org_slug=org_slug, linea=linea, db=db)

    sql = BILLTRACK_LOOKUP_SQL
    if not sql:
        return None

    params = resolve_connection(db)
    url = str(params.get("url") or "").strip()
    if not url:
        return None

    from sqlalchemy import create_engine, text

    sslmode = str(params.get("sslmode") or BILLTRACK_SSLMODE or "require")
    connect_args = {"connect_timeout": 8}
    if "sslmode" not in url:
        connect_args["sslmode"] = sslmode

    engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
    try:
        with engine.connect() as conn:
            # Solo SELECT — no ejecutar DDL/DML
            cleaned = sql.strip().rstrip(";")
            if not cleaned.lower().startswith("select"):
                raise ValueError("BILLTRACK_LOOKUP_SQL debe ser un SELECT")
            row = conn.execute(
                text(cleaned),
                {"dni": dni_n, "org_slug": org_slug or "", "linea": (linea or "").strip()},
            ).mappings().first()
            if not row:
                return None
            activo_raw = str(row.get("activo") or row.get("estado") or "activo").lower()
            activo = activo_raw in ("1", "true", "yes", "si", "sí", "activo", "habilitado", "a")
            return {
                "ref": str(row.get("ref") or row.get("id") or dni_n),
                "email": str(row.get("email") or row.get("correo") or "").strip(),
                "telefono": str(row.get("telefono") or row.get("msisdn") or "").strip(),
                "nombre": str(row.get("nombre") or "").strip(),
                "activo": activo,
                "dni": dni_n,
            }
    finally:
        engine.dispose()


def _mock_lookup(
    dni_n: str,
    *,
    org_slug: str = "",
    linea: str = "",
    db: Session | None = None,
) -> dict[str, Any] | None:
    """Fallback desarrollo: padrón local abonados (NO es auth; solo simula BillTrack)."""
    if db is None:
        # Catálogo fijo para tests sin DB
        catalog = {
            "30111222": {
                "ref": "BT-30111222",
                "email": "maria.gonzalez@example.com",
                "telefono": "5492235551234",
                "nombre": "María González",
                "activo": True,
            },
            "28555666": {
                "ref": "BT-28555666",
                "email": "carlos.perez@example.com",
                "telefono": "5492235555678",
                "nombre": "Carlos Pérez",
                "activo": True,
            },
            "32123456": {
                "ref": "BT-32123456",
                "email": "ana.ruiz@example.com",
                "telefono": "5492235559012",
                "nombre": "Ana Ruiz",
                "activo": False,
            },
            "29888777": {
                "ref": "BT-29888777",
                "email": "laura.diaz@example.com",
                "telefono": "5492235560002",
                "nombre": "Laura Díaz",
                "activo": True,
            },
            "26444555": {
                "ref": "BT-26444555",
                "email": "pedro.ecolan@example.com",
                "telefono": "5492235560099",
                "nombre": "Pedro Ecolan",
                "activo": True,
            },
        }
        hit = catalog.get(dni_n)
        if not hit:
            return None
        if linea and hit.get("telefono") and linea not in str(hit["telefono"]):
            return None
        return {**hit, "dni": dni_n}

    from app.estate import canal_repo as crepo
    from app.estate import repository as repo

    slug = org_slug or "coop-batan"
    org = repo.get_org_by_slug(db, slug)
    if not org:
        return None
    abo = crepo.find_abonado_por_dni(db, org.id, dni_n)
    if not abo:
        return None
    if linea:
        lin = "".join(c for c in linea if c.isdigit())
        tel = "".join(c for c in (abo.telefono_e164 or "") if c.isdigit())
        msisdn = "".join(c for c in (abo.linea_msisdn or "") if c.isdigit())
        if lin and lin not in tel and lin not in msisdn:
            return None
    email = f"{(abo.nombre or 'abonado').split()[0].lower()}.portal@example.com"
    return {
        "ref": abo.id,
        "email": email,
        "telefono": abo.telefono_e164 or "",
        "nombre": abo.nombre or "",
        "activo": (abo.estado or "").lower() in ("activo", "al dia", "al día", ""),
        "dni": dni_n,
    }