"""Add audit timestamps to graph-owned source documents."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_db.schema_support import graph_schema_name

revision = "024_source_document_audit"
down_revision = "023_graph_source_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    schema = graph_schema_name()
    if not inspector.has_table("source_documents", schema=schema):
        return

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("source_documents", schema=schema)
    }
    if "created_at" not in existing_columns:
        op.add_column(
            "source_documents",
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            schema=schema,
        )
    if "updated_at" not in existing_columns:
        op.add_column(
            "source_documents",
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            schema=schema,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    schema = graph_schema_name()
    if not inspector.has_table("source_documents", schema=schema):
        return

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("source_documents", schema=schema)
    }
    if "updated_at" in existing_columns:
        op.drop_column("source_documents", "updated_at", schema=schema)
    if "created_at" in existing_columns:
        op.drop_column("source_documents", "created_at", schema=schema)
