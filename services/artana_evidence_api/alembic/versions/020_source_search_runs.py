"""Add durable direct source-search run storage."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_api.db_schema import harness_schema_name

revision = "020_source_search_runs"
down_revision = "019_review_item_schema_repair"
branch_labels = None
depends_on = None


def upgrade() -> None:
    harness_schema = harness_schema_name()

    op.create_table(
        "source_search_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("space_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("source_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column(
            "query_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "result_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "response_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "source_capture",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema=harness_schema,
    )
    op.create_index(
        "idx_source_search_runs_space_source_created",
        "source_search_runs",
        ["space_id", "source_key", "created_at"],
        unique=False,
        schema=harness_schema,
    )
    op.create_index(
        "idx_source_search_runs_source_key",
        "source_search_runs",
        ["source_key"],
        unique=False,
        schema=harness_schema,
    )
    op.create_index(
        "idx_source_search_runs_status",
        "source_search_runs",
        ["status"],
        unique=False,
        schema=harness_schema,
    )


def downgrade() -> None:
    harness_schema = harness_schema_name()

    op.drop_index(
        "idx_source_search_runs_status",
        table_name="source_search_runs",
        schema=harness_schema,
    )
    op.drop_index(
        "idx_source_search_runs_source_key",
        table_name="source_search_runs",
        schema=harness_schema,
    )
    op.drop_index(
        "idx_source_search_runs_space_source_created",
        table_name="source_search_runs",
        schema=harness_schema,
    )
    op.drop_table("source_search_runs", schema=harness_schema)
