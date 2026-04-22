"""Move remaining graph kernel tables into the configured graph schema."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_db.schema_support import graph_schema_name

revision = "010_graph_kernel_schema"
down_revision = "009_graph_gov_schema"
branch_labels = None
depends_on = None

_GRAPH_KERNEL_TABLES: tuple[str, ...] = (
    "entities",
    "entity_identifiers",
    "entity_embeddings",
    "provenance",
    "observations",
    "relation_claims",
    "claim_participants",
    "claim_evidence",
    "claim_relations",
    "relations",
    "relation_evidence",
    "relation_projection_sources",
    "reasoning_paths",
    "reasoning_path_steps",
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

    for table_name in _GRAPH_KERNEL_TABLES:
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
