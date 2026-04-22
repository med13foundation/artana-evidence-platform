"""Add durable graph-harness proposal table."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_api.db_schema import harness_schema_name

revision = "004_harness_proposals"
down_revision = "003_harness_run_lifecycle"
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
        "harness_proposals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("space_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("proposal_type", sa.String(length=64), nullable=False),
        sa.Column("source_kind", sa.String(length=64), nullable=False),
        sa.Column("source_key", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("ranking_score", sa.Float(), nullable=False),
        sa.Column(
            "reasoning_path",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
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
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        schema=schema,
        comment="Candidate proposals staged by graph-harness runs.",
    )
    op.create_index(
        "ix_harness_proposals_space_id",
        "harness_proposals",
        ["space_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_proposals_run_id",
        "harness_proposals",
        ["run_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_proposals_proposal_type",
        "harness_proposals",
        ["proposal_type"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_proposals_source_kind",
        "harness_proposals",
        ["source_kind"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_proposals_source_key",
        "harness_proposals",
        ["source_key"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_proposals_status",
        "harness_proposals",
        ["status"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_proposals_ranking_score",
        "harness_proposals",
        ["ranking_score"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_proposals_space_status",
        "harness_proposals",
        ["space_id", "status"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_proposals_space_rank",
        "harness_proposals",
        ["space_id", "ranking_score"],
        unique=False,
        schema=schema,
    )


def downgrade() -> None:
    schema = harness_schema_name()

    op.drop_index(
        "idx_harness_proposals_space_rank",
        table_name="harness_proposals",
        schema=schema,
    )
    op.drop_index(
        "idx_harness_proposals_space_status",
        table_name="harness_proposals",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_proposals_ranking_score",
        table_name="harness_proposals",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_proposals_status",
        table_name="harness_proposals",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_proposals_source_key",
        table_name="harness_proposals",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_proposals_source_kind",
        table_name="harness_proposals",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_proposals_proposal_type",
        table_name="harness_proposals",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_proposals_run_id",
        table_name="harness_proposals",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_proposals_space_id",
        table_name="harness_proposals",
        schema=schema,
    )
    op.drop_table("harness_proposals", schema=schema)
