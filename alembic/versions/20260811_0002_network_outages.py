"""network_outages — incidentes masivos por NAS.

Revision ID: 20260811_0002
Revises: 20260804_0001
Create Date: 2026-08-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260811_0002"
down_revision: Union[str, Sequence[str], None] = "20260804_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "network_outages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organizacion_id", sa.String(length=36), nullable=False),
        sa.Column("nas_shortname", sa.String(length=120), nullable=False),
        sa.Column("nas_ip", sa.String(length=64), server_default="", nullable=False),
        sa.Column("alcance", sa.String(length=16), server_default="total", nullable=False),
        sa.Column("tipo", sa.String(length=32), server_default="DOWN", nullable=False),
        sa.Column("comentario", sa.Text(), server_default="", nullable=False),
        sa.Column("mensaje_cliente", sa.Text(), server_default="", nullable=False),
        sa.Column("eta_minutos", sa.Integer(), server_default="45", nullable=False),
        sa.Column(
            "nas_reachable_at_declare",
            sa.String(length=8),
            server_default="",
            nullable=False,
        ),
        sa.Column("estado", sa.String(length=16), server_default="activo", nullable=False),
        sa.Column("fuente", sa.String(length=24), server_default="manual", nullable=False),
        sa.Column("created_by", sa.String(length=120), server_default="", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organizacion_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_network_outages_organizacion_id"),
        "network_outages",
        ["organizacion_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_network_outages_nas_shortname"),
        "network_outages",
        ["nas_shortname"],
        unique=False,
    )
    op.create_index(
        op.f("ix_network_outages_estado"),
        "network_outages",
        ["estado"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_network_outages_estado"), table_name="network_outages")
    op.drop_index(op.f("ix_network_outages_nas_shortname"), table_name="network_outages")
    op.drop_index(op.f("ix_network_outages_organizacion_id"), table_name="network_outages")
    op.drop_table("network_outages")
