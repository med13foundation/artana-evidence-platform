"""Add graph-owned space registry table."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_db.schema_support import graph_schema_name

revision = "003_graph_spaces"
down_revision = "002_reasoning_paths"
branch_labels = None
depends_on = None


def upgrade() -> None:
    graph_schema = graph_schema_name()
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("graph_spaces", schema=graph_schema):
        return
    if graph_schema is not None:
        op.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{graph_schema}"'))
    uuid_type = sa.Uuid()
    status_enum = sa.Enum(
        "active",
        "inactive",
        "archived",
        "suspended",
        name="graphspacestatusenum",
    )
    status_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "graph_spaces",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("slug", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_id", uuid_type, nullable=False),
        sa.Column("status", status_enum, nullable=False, server_default="active"),
        sa.Column("settings", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_graph_spaces_slug"),
        schema=graph_schema,
        comment="Graph-owned tenant registry for the standalone graph service",
    )
    op.create_index(
        "ix_graph_spaces_slug",
        "graph_spaces",
        ["slug"],
        unique=False,
        schema=graph_schema,
    )
    op.create_index(
        "idx_graph_spaces_owner",
        "graph_spaces",
        ["owner_id"],
        unique=False,
        schema=graph_schema,
    )
    op.create_index(
        "idx_graph_spaces_status",
        "graph_spaces",
        ["status"],
        unique=False,
        schema=graph_schema,
    )


def downgrade() -> None:
    return None
