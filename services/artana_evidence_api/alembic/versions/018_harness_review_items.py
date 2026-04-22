"""Add harness-owned review items for the unified review queue."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_api.db_schema import harness_schema_name

revision = "018_harness_review_items"
down_revision = "017_add_review_timestamps"
branch_labels = None
depends_on = None


def _qualify(table_name: str, column_name: str) -> str:
    schema = harness_schema_name()
    if schema is None:
        return f"{table_name}.{column_name}"
    return f"{schema}.{table_name}.{column_name}"


def upgrade() -> None:
    schema = harness_schema_name()
    op.create_table(
        "harness_review_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("space_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("review_type", sa.String(length=64), nullable=False),
        sa.Column("source_family", sa.String(length=64), nullable=False),
        sa.Column("source_kind", sa.String(length=64), nullable=False),
        sa.Column("source_key", sa.String(length=255), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("ranking_score", sa.Float(), nullable=False),
        sa.Column(
            "evidence_bundle_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "metadata_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("review_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("linked_proposal_id", sa.UUID(), nullable=True),
        sa.Column("linked_approval_key", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            [_qualify("harness_runs", "id")],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            [_qualify("harness_documents", "id")],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=schema,
        comment="Review-only items staged by graph-harness runs.",
    )
    op.create_index(
        "ix_harness_review_items_space_id",
        "harness_review_items",
        ["space_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "uq_harness_review_items_space_review_fingerprint",
        "harness_review_items",
        ["space_id", "review_fingerprint"],
        unique=True,
        schema=schema,
        postgresql_where=sa.text("review_fingerprint IS NOT NULL"),
    )
    op.create_index(
        "uq_harness_review_items_space_type_source_key_null_fp",
        "harness_review_items",
        ["space_id", "review_type", "source_key"],
        unique=True,
        schema=schema,
        postgresql_where=sa.text("review_fingerprint IS NULL"),
    )
    op.create_index(
        "ix_harness_review_items_run_id",
        "harness_review_items",
        ["run_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_review_items_review_type",
        "harness_review_items",
        ["review_type"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_review_items_source_family",
        "harness_review_items",
        ["source_family"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_review_items_source_kind",
        "harness_review_items",
        ["source_kind"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_review_items_source_key",
        "harness_review_items",
        ["source_key"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_review_items_document_id",
        "harness_review_items",
        ["document_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_review_items_priority",
        "harness_review_items",
        ["priority"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_review_items_status",
        "harness_review_items",
        ["status"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_review_items_linked_proposal_id",
        "harness_review_items",
        ["linked_proposal_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_review_items_linked_approval_key",
        "harness_review_items",
        ["linked_approval_key"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_review_items_ranking_score",
        "harness_review_items",
        ["ranking_score"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_review_items_space_status",
        "harness_review_items",
        ["space_id", "status"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_review_items_space_rank",
        "harness_review_items",
        ["space_id", "ranking_score"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_review_items_document_id",
        "harness_review_items",
        ["document_id"],
        unique=False,
        schema=schema,
    )


def downgrade() -> None:
    schema = harness_schema_name()
    op.drop_index(
        "uq_harness_review_items_space_type_source_key_null_fp",
        table_name="harness_review_items",
        schema=schema,
    )
    op.drop_index(
        "uq_harness_review_items_space_review_fingerprint",
        table_name="harness_review_items",
        schema=schema,
    )
    op.drop_index(
        "idx_harness_review_items_document_id",
        table_name="harness_review_items",
        schema=schema,
    )
    op.drop_index(
        "idx_harness_review_items_space_rank",
        table_name="harness_review_items",
        schema=schema,
    )
    op.drop_index(
        "idx_harness_review_items_space_status",
        table_name="harness_review_items",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_review_items_linked_approval_key",
        table_name="harness_review_items",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_review_items_linked_proposal_id",
        table_name="harness_review_items",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_review_items_ranking_score",
        table_name="harness_review_items",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_review_items_status",
        table_name="harness_review_items",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_review_items_priority",
        table_name="harness_review_items",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_review_items_document_id",
        table_name="harness_review_items",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_review_items_source_key",
        table_name="harness_review_items",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_review_items_source_kind",
        table_name="harness_review_items",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_review_items_review_type",
        table_name="harness_review_items",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_review_items_source_family",
        table_name="harness_review_items",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_review_items_run_id",
        table_name="harness_review_items",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_review_items_space_id",
        table_name="harness_review_items",
        schema=schema,
    )
    op.drop_table("harness_review_items", schema=schema)
