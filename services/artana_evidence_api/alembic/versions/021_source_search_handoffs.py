"""Add durable direct source-search handoff storage."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_api.db_schema import harness_schema_name

revision = "021_source_search_handoffs"
down_revision = "020_source_search_runs"
branch_labels = None
depends_on = None


def _harness_fk_target(*, schema: str | None, table: str, column: str) -> str:
    if schema is None:
        return f"{table}.{column}"
    return f"{schema}.{table}.{column}"


def upgrade() -> None:
    harness_schema = harness_schema_name()

    op.create_table(
        "source_search_handoffs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("space_id", sa.UUID(), nullable=False),
        sa.Column("source_key", sa.String(length=64), nullable=False),
        sa.Column("search_id", sa.UUID(), nullable=False),
        sa.Column("target_kind", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column(
            "record_selector_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "search_snapshot_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "source_capture_snapshot",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "handoff_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("target_run_id", sa.UUID(), nullable=True),
        sa.Column("target_document_id", sa.UUID(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["search_id"],
            [
                _harness_fk_target(
                    schema=harness_schema,
                    table="source_search_runs",
                    column="id",
                ),
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_run_id"],
            [
                _harness_fk_target(
                    schema=harness_schema,
                    table="harness_runs",
                    column="id",
                ),
            ],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["target_document_id"],
            [
                _harness_fk_target(
                    schema=harness_schema,
                    table="harness_documents",
                    column="id",
                ),
            ],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "space_id",
            "source_key",
            "search_id",
            "target_kind",
            "idempotency_key",
            name="uq_source_search_handoffs_idempotency",
        ),
        schema=harness_schema,
    )
    op.create_index(
        "idx_source_search_handoffs_space_source_search",
        "source_search_handoffs",
        ["space_id", "source_key", "search_id"],
        unique=False,
        schema=harness_schema,
    )
    op.create_index(
        "ix_source_search_handoffs_created_by",
        "source_search_handoffs",
        ["created_by"],
        unique=False,
        schema=harness_schema,
    )
    op.create_index(
        "ix_source_search_handoffs_search_id",
        "source_search_handoffs",
        ["search_id"],
        unique=False,
        schema=harness_schema,
    )
    op.create_index(
        "ix_source_search_handoffs_source_key",
        "source_search_handoffs",
        ["source_key"],
        unique=False,
        schema=harness_schema,
    )
    op.create_index(
        "ix_source_search_handoffs_space_id",
        "source_search_handoffs",
        ["space_id"],
        unique=False,
        schema=harness_schema,
    )
    op.create_index(
        "ix_source_search_handoffs_status",
        "source_search_handoffs",
        ["status"],
        unique=False,
        schema=harness_schema,
    )
    op.create_index(
        "ix_source_search_handoffs_target_document_id",
        "source_search_handoffs",
        ["target_document_id"],
        unique=False,
        schema=harness_schema,
    )
    op.create_index(
        "ix_source_search_handoffs_target_run_id",
        "source_search_handoffs",
        ["target_run_id"],
        unique=False,
        schema=harness_schema,
    )


def downgrade() -> None:
    harness_schema = harness_schema_name()

    op.drop_index(
        "ix_source_search_handoffs_target_run_id",
        table_name="source_search_handoffs",
        schema=harness_schema,
    )
    op.drop_index(
        "ix_source_search_handoffs_target_document_id",
        table_name="source_search_handoffs",
        schema=harness_schema,
    )
    op.drop_index(
        "ix_source_search_handoffs_status",
        table_name="source_search_handoffs",
        schema=harness_schema,
    )
    op.drop_index(
        "ix_source_search_handoffs_space_id",
        table_name="source_search_handoffs",
        schema=harness_schema,
    )
    op.drop_index(
        "ix_source_search_handoffs_source_key",
        table_name="source_search_handoffs",
        schema=harness_schema,
    )
    op.drop_index(
        "ix_source_search_handoffs_search_id",
        table_name="source_search_handoffs",
        schema=harness_schema,
    )
    op.drop_index(
        "ix_source_search_handoffs_created_by",
        table_name="source_search_handoffs",
        schema=harness_schema,
    )
    op.drop_index(
        "idx_source_search_handoffs_space_source_search",
        table_name="source_search_handoffs",
        schema=harness_schema,
    )
    op.drop_table("source_search_handoffs", schema=harness_schema)
