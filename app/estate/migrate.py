"""Migraciones ligeras — agrega columnas nuevas sin perder datos (SQLite y PostgreSQL)."""

from __future__ import annotations

import logging
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger("imowi")

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
}

_CASO_COLUMNS: dict[str, str] = {
    "linea_msisdn": "VARCHAR(16) DEFAULT ''",
    "intencion_pendiente": "VARCHAR(32) DEFAULT ''",
}


def _add_column(engine: Engine, tabla: str, col: str, ddl: str) -> None:
    dialect = engine.dialect.name
    if dialect == "postgresql":
        sql = f"ALTER TABLE {tabla} ADD COLUMN IF NOT EXISTS {col} {ddl}"
    else:
        sql = f"ALTER TABLE {tabla} ADD COLUMN {col} {ddl}"
    with engine.begin() as conn:
        conn.execute(text(sql))


def migrate_schema(engine: Engine) -> list[str]:
    """Agrega columnas faltantes en tablas existentes. Retorna lista de cambios."""
    cambios: list[str] = []
    insp = inspect(engine)
    if not insp.has_table("tickets_estate"):
        return cambios

    existentes = {c["name"] for c in insp.get_columns("tickets_estate")}
    for col, ddl in _TICKET_COLUMNS.items():
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

    return cambios
