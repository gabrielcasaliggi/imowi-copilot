"""baseline Data Estate — marca el esquema actual sin recrear tablas.

Revision ID: 20260804_0001
Revises:
Create Date: 2026-08-04

Production postgres con estate: el boot hace stamp head si no hay
alembic_version. SQLite (tests/dev) sigue en create_all + migrate_schema.
"""

from __future__ import annotations

from typing import Sequence, Union

revision: str = "20260804_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Baseline vacío: el esquema vivo ya estaba en production.
    # Columnas nuevas: revisión Alembic + (mientras tanto) migrate_schema.
    pass


def downgrade() -> None:
    pass
