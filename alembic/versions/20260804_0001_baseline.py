"""baseline Data Estate — marca el esquema actual sin recrear tablas.

Revision ID: 20260804_0001
Revises:
Create Date: 2026-08-04

Bases ya existentes en producción: ejecutar
  alembic stamp head
Nuevos entornos pueden seguir usando create_all + migrate_schema en boot
hasta consolidar el esquema solo con Alembic.
"""

from __future__ import annotations

from typing import Sequence, Union

revision: str = "20260804_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Baseline vacío: el esquema vivo se gestiona hoy con
    # Base.metadata.create_all + app.estate.migrate.migrate_schema.
    # Próximos cambios de columnas van como revisiones Alembic reales.
    pass


def downgrade() -> None:
    pass
