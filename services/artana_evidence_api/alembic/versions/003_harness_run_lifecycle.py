"""Add durable graph-harness run progress and event tables."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_api.db_schema import harness_schema_name

revision = "003_harness_run_lifecycle"
down_revision = "002_harness_chat_sessions"
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
        "harness_run_progress",
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("space_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("phase", sa.String(length=128), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("progress_percent", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("completed_steps", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_steps", sa.Integer(), nullable=True),
        sa.Column("resume_point", sa.String(length=128), nullable=True),
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
            ["run_id"],
            [_qualify("harness_runs", "id")],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("run_id"),
        schema=schema,
        comment="Progress snapshots for graph-harness runs.",
    )
    op.create_index(
        "idx_harness_run_progress_space_id",
        "harness_run_progress",
        ["space_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_run_progress_status",
        "harness_run_progress",
        ["status"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_run_progress_space_run",
        "harness_run_progress",
        ["space_id", "run_id"],
        unique=False,
        schema=schema,
    )

    op.create_table(
        "harness_run_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("space_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("progress_percent", sa.Float(), nullable=True),
        sa.Column(
            "payload",
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
            ["run_id"],
            [_qualify("harness_runs", "id")],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=schema,
        comment="Lifecycle events for graph-harness runs.",
    )
    op.create_index(
        "idx_harness_run_events_run_id",
        "harness_run_events",
        ["run_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_run_events_space_id",
        "harness_run_events",
        ["space_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_run_events_event_type",
        "harness_run_events",
        ["event_type"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_run_events_status",
        "harness_run_events",
        ["status"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_run_events_space_run_created_at",
        "harness_run_events",
        ["space_id", "run_id", "created_at"],
        unique=False,
        schema=schema,
    )


def downgrade() -> None:
    schema = harness_schema_name()

    op.drop_index(
        "idx_harness_run_events_space_run_created_at",
        table_name="harness_run_events",
        schema=schema,
    )
    op.drop_index(
        "idx_harness_run_events_status",
        table_name="harness_run_events",
        schema=schema,
    )
    op.drop_index(
        "idx_harness_run_events_event_type",
        table_name="harness_run_events",
        schema=schema,
    )
    op.drop_index(
        "idx_harness_run_events_space_id",
        table_name="harness_run_events",
        schema=schema,
    )
    op.drop_index(
        "idx_harness_run_events_run_id",
        table_name="harness_run_events",
        schema=schema,
    )
    op.drop_table("harness_run_events", schema=schema)

    op.drop_index(
        "idx_harness_run_progress_space_run",
        table_name="harness_run_progress",
        schema=schema,
    )
    op.drop_index(
        "idx_harness_run_progress_status",
        table_name="harness_run_progress",
        schema=schema,
    )
    op.drop_index(
        "idx_harness_run_progress_space_id",
        table_name="harness_run_progress",
        schema=schema,
    )
    op.drop_table("harness_run_progress", schema=schema)
