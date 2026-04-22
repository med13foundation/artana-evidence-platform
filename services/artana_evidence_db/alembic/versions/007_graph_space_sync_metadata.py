"""Add graph-owned tenant sync metadata to graph_spaces."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_db.schema_support import graph_schema_name

revision = "007_graph_space_sync_metadata"
down_revision = "006_graph_external_document_refs"
branch_labels = None
depends_on = None


def _has_column(
    inspector: sa.Inspector,
    table_name: str,
    column_name: str,
    *,
    schema: str | None,
) -> bool:
    return any(
        column["name"] == column_name
        for column in inspector.get_columns(table_name, schema=schema)
    )


def _has_index(
    inspector: sa.Inspector,
    table_name: str,
    index_name: str,
    *,
    schema: str | None,
) -> bool:
    return any(
        index["name"] == index_name
        for index in inspector.get_indexes(table_name, schema=schema)
    )


def upgrade() -> None:
    bind = op.get_bind()
    graph_schema = graph_schema_name()
    if graph_schema is not None and bind.dialect.name == "postgresql":
        op.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{graph_schema}"'))
    inspector = sa.inspect(bind)

    additions = (
        ("sync_source", sa.String(length=64), "idx_graph_spaces_sync_source"),
        ("sync_fingerprint", sa.String(length=64), "idx_graph_spaces_sync_fingerprint"),
        (
            "source_updated_at",
            sa.DateTime(timezone=True),
            "idx_graph_spaces_source_updated_at",
        ),
        (
            "last_synced_at",
            sa.DateTime(timezone=True),
            "idx_graph_spaces_last_synced_at",
        ),
    )

    for column_name, column_type, index_name in additions:
        if not _has_column(
            inspector,
            "graph_spaces",
            column_name,
            schema=graph_schema,
        ):
            op.add_column(
                "graph_spaces",
                sa.Column(column_name, column_type, nullable=True),
                schema=graph_schema,
            )
        inspector = sa.inspect(bind)
        if not _has_index(
            inspector,
            "graph_spaces",
            index_name,
            schema=graph_schema,
        ):
            op.create_index(
                index_name,
                "graph_spaces",
                [column_name],
                unique=False,
                schema=graph_schema,
            )
        inspector = sa.inspect(bind)


def downgrade() -> None:
    return None
