"""Move graph control-plane tables into the configured graph schema."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_db.schema_support import graph_schema_name

revision = "008_graph_cp_schema"
down_revision = "007_graph_space_sync_metadata"
branch_labels = None
depends_on = None

_GRAPH_CONTROL_PLANE_TABLES: tuple[str, ...] = (
    "graph_spaces",
    "graph_space_memberships",
    "graph_operation_runs",
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    target_schema = graph_schema_name()
    if target_schema is None:
        return

    inspector = sa.inspect(bind)
    op.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{target_schema}"'))

    for table_name in _GRAPH_CONTROL_PLANE_TABLES:
        if inspector.has_table(table_name, schema=target_schema):
            continue
        if not inspector.has_table(table_name, schema="public"):
            continue
        op.execute(
            sa.text(
                f'ALTER TABLE public."{table_name}" SET SCHEMA "{target_schema}"',
            ),
        )
        inspector = sa.inspect(bind)


def downgrade() -> None:
    return None
