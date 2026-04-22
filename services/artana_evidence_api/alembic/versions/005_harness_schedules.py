"""Add durable graph-harness schedule table."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_api.db_schema import harness_schema_name

revision = "005_harness_schedules"
down_revision = "004_harness_proposals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = harness_schema_name()

    op.create_table(
        "harness_schedules",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("space_id", sa.UUID(), nullable=False),
        sa.Column("harness_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("cadence", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column(
            "configuration_payload",
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
        sa.Column("last_run_id", sa.UUID(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        schema=schema,
        comment="Schedule definitions for graph-harness workflows.",
    )
    op.create_index(
        "ix_harness_schedules_space_id",
        "harness_schedules",
        ["space_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_schedules_harness_id",
        "harness_schedules",
        ["harness_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_schedules_status",
        "harness_schedules",
        ["status"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_schedules_created_by",
        "harness_schedules",
        ["created_by"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_schedules_last_run_id",
        "harness_schedules",
        ["last_run_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_schedules_space_updated_at",
        "harness_schedules",
        ["space_id", "updated_at"],
        unique=False,
        schema=schema,
    )


def downgrade() -> None:
    schema = harness_schema_name()

    op.drop_index(
        "idx_harness_schedules_space_updated_at",
        table_name="harness_schedules",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_schedules_last_run_id",
        table_name="harness_schedules",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_schedules_created_by",
        table_name="harness_schedules",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_schedules_status",
        table_name="harness_schedules",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_schedules_harness_id",
        table_name="harness_schedules",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_schedules_space_id",
        table_name="harness_schedules",
        schema=schema,
    )
    op.drop_table("harness_schedules", schema=schema)
