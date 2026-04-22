"""Add durable graph-harness research-state and graph-snapshot tables."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_api.db_schema import harness_schema_name

revision = "006_harness_research_memory"
down_revision = "005_harness_schedules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = harness_schema_name()

    op.create_table(
        "harness_research_state",
        sa.Column("space_id", sa.UUID(), nullable=False),
        sa.Column("objective", sa.Text(), nullable=True),
        sa.Column(
            "current_hypotheses_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "explored_questions_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "pending_questions_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("last_graph_snapshot_id", sa.UUID(), nullable=True),
        sa.Column("last_learning_cycle_at", sa.DateTime(), nullable=True),
        sa.Column(
            "active_schedules_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "confidence_model_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "budget_policy_payload",
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
        sa.PrimaryKeyConstraint("space_id"),
        schema=schema,
        comment="Structured research-state snapshots per space.",
    )
    op.create_index(
        "idx_harness_research_state_updated_at",
        "harness_research_state",
        ["updated_at"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_research_state_last_graph_snapshot_id",
        "harness_research_state",
        ["last_graph_snapshot_id"],
        unique=False,
        schema=schema,
    )

    op.create_table(
        "harness_graph_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("space_id", sa.UUID(), nullable=False),
        sa.Column("source_run_id", sa.UUID(), nullable=False),
        sa.Column(
            "claim_ids_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "relation_ids_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("graph_document_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "summary_payload",
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
            ["source_run_id"],
            ["harness_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=schema,
        comment="Run-scoped graph-context snapshots.",
    )
    op.create_index(
        "ix_harness_graph_snapshots_space_id",
        "harness_graph_snapshots",
        ["space_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_graph_snapshots_source_run_id",
        "harness_graph_snapshots",
        ["source_run_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_graph_snapshots_space_created_at",
        "harness_graph_snapshots",
        ["space_id", "created_at"],
        unique=False,
        schema=schema,
    )


def downgrade() -> None:
    schema = harness_schema_name()

    op.drop_index(
        "idx_harness_graph_snapshots_space_created_at",
        table_name="harness_graph_snapshots",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_graph_snapshots_source_run_id",
        table_name="harness_graph_snapshots",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_graph_snapshots_space_id",
        table_name="harness_graph_snapshots",
        schema=schema,
    )
    op.drop_table("harness_graph_snapshots", schema=schema)

    op.drop_index(
        "ix_harness_research_state_last_graph_snapshot_id",
        table_name="harness_research_state",
        schema=schema,
    )
    op.drop_index(
        "idx_harness_research_state_updated_at",
        table_name="harness_research_state",
        schema=schema,
    )
    op.drop_table("harness_research_state", schema=schema)
