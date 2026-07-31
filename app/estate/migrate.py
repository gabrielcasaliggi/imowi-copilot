"""Migraciones ligeras — agrega columnas nuevas sin perder datos (SQLite y PostgreSQL)."""

from __future__ import annotations

import logging
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger("operations_hub")

_TICKET_COLUMNS: dict[str, str] = {
    "nivel": "VARCHAR(16) DEFAULT 'N1'",
    "destino": "VARCHAR(32) DEFAULT 'cooperativa'",
    "proveedor": "VARCHAR(120) DEFAULT ''",
    "motivo_escalamiento": "TEXT DEFAULT ''",
    "evidencia": "TEXT DEFAULT ''",
    "acciones_n1_realizadas": "TEXT DEFAULT ''",
    "estado_sla": "VARCHAR(32) DEFAULT 'Pendiente'",
    "ticket_externo_id": "VARCHAR(64) DEFAULT ''",
    "regla_clasificacion": "VARCHAR(64) DEFAULT ''",
    "asignado_a": "VARCHAR(120) DEFAULT ''",
}

_CASO_COLUMNS: dict[str, str] = {
    "linea_msisdn": "VARCHAR(16) DEFAULT ''",
    "intencion_pendiente": "VARCHAR(32) DEFAULT ''",
}

_USER_COLUMNS: dict[str, str] = {
    "telefono": "VARCHAR(32) DEFAULT ''",
    "linea_principal": "VARCHAR(16) DEFAULT ''",
    "must_change_password": "VARCHAR(8) DEFAULT 'No'",
    "activo": "VARCHAR(8) DEFAULT 'Sí'",
    "disponibilidad": "VARCHAR(24) DEFAULT 'disponible'",
    "last_login_at": "DATETIME",
    "token_version": "INTEGER DEFAULT 0",
    "email_verified_at": "DATETIME",
}

_INVITE_COLUMNS: dict[str, str] = {
    "purpose": "VARCHAR(32) DEFAULT 'invite'",
}

_SLA_COLUMNS: dict[str, str] = {
    "sla_policy": "VARCHAR(32) DEFAULT ''",
    "sla_due_at": "DATETIME",
    "sla_breached_at": "DATETIME",
}

_AUTH_TABLES = (
    ("auth_login_events", "AuthLoginEvent"),
    ("auth_lockouts", "AuthLockout"),
    ("auth_token_denylist", "AuthTokenDenylist"),
    ("user_invites", "UserInvite"),
    ("portal_abonado_links", "PortalAbonadoLink"),
    ("portal_otp_challenges", "PortalOtpChallenge"),
)


def _ddl_for_dialect(engine: Engine, ddl: str) -> str:
    """Normaliza tipos datetime entre SQLite (DATETIME) y PostgreSQL (TIMESTAMPTZ)."""
    dialect = engine.dialect.name
    if dialect == "postgresql":
        return ddl.replace("DATETIME", "TIMESTAMP WITH TIME ZONE")
    return ddl.replace("TIMESTAMP WITH TIME ZONE", "DATETIME")


def _add_column(engine: Engine, tabla: str, col: str, ddl: str) -> None:
    ddl = _ddl_for_dialect(engine, ddl)
    if engine.dialect.name == "postgresql":
        sql = f"ALTER TABLE {tabla} ADD COLUMN IF NOT EXISTS {col} {ddl}"
    else:
        sql = f"ALTER TABLE {tabla} ADD COLUMN {col} {ddl}"
    with engine.begin() as conn:
        conn.execute(text(sql))


def migrate_schema(engine: Engine) -> list[str]:
    """Agrega columnas faltantes en tablas existentes. Retorna lista de cambios."""
    cambios: list[str] = []
    insp = inspect(engine)

    if not insp.has_table("audit_events"):
        from app.estate.models import AuditEvent

        AuditEvent.__table__.create(bind=engine)
        cambios.append("audit_events")
        logger.info("Migración: tabla creada audit_events")

    if not insp.has_table("tickets_estate"):
        # Aún crear tablas de auth/portal si faltan
        cambios.extend(_ensure_auth_tables(engine, insp))
        return cambios

    existentes = {c["name"] for c in insp.get_columns("tickets_estate")}
    for col, ddl in {**_TICKET_COLUMNS, **_SLA_COLUMNS}.items():
        if col not in existentes:
            _add_column(engine, "tickets_estate", col, ddl)
            cambios.append(f"tickets_estate.{col}")
            logger.info("Migración: columna agregada tickets_estate.%s", col)

    if insp.has_table("casos_conversacion"):
        existentes_caso = {c["name"] for c in insp.get_columns("casos_conversacion")}
        for col, ddl in _CASO_COLUMNS.items():
            if col not in existentes_caso:
                _add_column(engine, "casos_conversacion", col, ddl)
                cambios.append(f"casos_conversacion.{col}")
                logger.info("Migración: columna agregada casos_conversacion.%s", col)

    if insp.has_table("users"):
        existentes_user = {c["name"] for c in insp.get_columns("users")}
        for col, ddl in _USER_COLUMNS.items():
            if col not in existentes_user:
                _add_column(engine, "users", col, ddl)
                cambios.append(f"users.{col}")
                logger.info("Migración: columna agregada users.%s", col)
        cambios.extend(_migrate_legacy_roles(engine))

    if insp.has_table("user_invites"):
        existentes_inv = {c["name"] for c in insp.get_columns("user_invites")}
        for col, ddl in _INVITE_COLUMNS.items():
            if col not in existentes_inv:
                _add_column(engine, "user_invites", col, ddl)
                cambios.append(f"user_invites.{col}")
                logger.info("Migración: columna agregada user_invites.%s", col)
    for tabla, model_name in (
        ("abonados", "Abonado"),
        ("conversaciones_canal", "ConversacionCanal"),
        ("mensajes_canal", "MensajeCanal"),
        ("knowledge_contributions", "KnowledgeContribution"),
    ):
        if not insp.has_table(tabla):
            from app.estate import models as m

            getattr(m, model_name).__table__.create(bind=engine)
            cambios.append(tabla)
            logger.info("Migración: tabla creada %s", tabla)

    insp = inspect(engine)
    cambios.extend(_ensure_auth_tables(engine, insp))
    return cambios


def _ensure_auth_tables(engine: Engine, insp) -> list[str]:
    cambios: list[str] = []
    from app.estate import models as m

    for tabla, model_name in _AUTH_TABLES:
        if not insp.has_table(tabla):
            getattr(m, model_name).__table__.create(bind=engine)
            cambios.append(tabla)
            logger.info("Migración: tabla creada %s", tabla)
    return cambios


def _migrate_legacy_roles(engine: Engine) -> list[str]:
    """Normaliza roles legacy de users al catálogo de consola (docs/RBAC-ROLES-PERMISOS.md)."""
    cambios: list[str] = []
    statements = [
        (
            "UPDATE users SET rol = 'admin' WHERE lower(rol) IN ('admin_sistema', 'admin')",
            "users.rol→admin",
        ),
        (
            "UPDATE users SET rol = 'supervisor' WHERE lower(rol) = 'admin_org'",
            "users.rol admin_org→supervisor",
        ),
        (
            "UPDATE users SET rol = 'agente' WHERE lower(rol) IN ('operador', 'cooperativa', 'cliente')",
            "users.rol legacy→agente",
        ),
    ]
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(
                text(
                    """
                    UPDATE users u
                    SET rol = CASE
                        WHEN o.slug = 'imowi' THEN 'admin'
                        ELSE 'supervisor'
                    END
                    FROM organizations o
                    WHERE u.organizacion_id = o.id AND lower(u.rol) = 'ingeniero_noc'
                    """
                )
            )
        else:
            conn.execute(
                text(
                    """
                    UPDATE users
                    SET rol = CASE
                        WHEN organizacion_id IN (SELECT id FROM organizations WHERE slug = 'imowi')
                        THEN 'admin'
                        ELSE 'supervisor'
                    END
                    WHERE lower(rol) = 'ingeniero_noc'
                    """
                )
            )
        cambios.append("users.rol ingeniero_noc→admin|supervisor")
        for sql, label in statements:
            conn.execute(text(sql))
            cambios.append(label)
    logger.info("Migración: roles de usuario normalizados a catálogo RBAC")
    return cambios
