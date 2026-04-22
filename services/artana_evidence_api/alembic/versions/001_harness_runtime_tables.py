"""Add durable graph-harness runtime tables."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_api.db_schema import harness_schema_name

revision = "001_harness_runtime_tables"
down_revision = None
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
        "harness_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("space_id", sa.UUID(), nullable=False),
        sa.Column("harness_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column(
            "input_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("graph_service_status", sa.String(length=64), nullable=False),
        sa.Column("graph_service_version", sa.String(length=128), nullable=False),
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
        comment="Durable graph-harness run metadata.",
    )
    op.create_index(
        "idx_harness_runs_space_id",
        "harness_runs",
        ["space_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_runs_harness_id",
        "harness_runs",
        ["harness_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_runs_status",
        "harness_runs",
        ["status"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_runs_space_created_at",
        "harness_runs",
        ["space_id", "created_at"],
        unique=False,
        schema=schema,
    )

    op.create_table(
        "harness_run_artifacts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("space_id", sa.UUID(), nullable=False),
        sa.Column("artifact_key", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=128), nullable=False),
        sa.Column(
            "content",
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
        sa.UniqueConstraint(
            "run_id",
            "artifact_key",
            name="uq_harness_run_artifacts_run_id_artifact_key",
        ),
        schema=schema,
        comment="Artifacts written by graph-harness runs.",
    )
    op.create_index(
        "idx_harness_run_artifacts_run_id",
        "harness_run_artifacts",
        ["run_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_run_artifacts_space_id",
        "harness_run_artifacts",
        ["space_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_run_artifacts_space_run",
        "harness_run_artifacts",
        ["space_id", "run_id"],
        unique=False,
        schema=schema,
    )

    op.create_table(
        "harness_run_workspaces",
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("space_id", sa.UUID(), nullable=False),
        sa.Column(
            "snapshot",
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
        comment="Workspace snapshots for graph-harness runs.",
    )
    op.create_index(
        "idx_harness_run_workspaces_space_id",
        "harness_run_workspaces",
        ["space_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_run_workspaces_space_run",
        "harness_run_workspaces",
        ["space_id", "run_id"],
        unique=False,
        schema=schema,
    )

    op.create_table(
        "harness_run_intents",
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("space_id", sa.UUID(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "proposed_actions_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
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
            ["run_id"],
            [_qualify("harness_runs", "id")],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("run_id"),
        schema=schema,
        comment="Intent plans for graph-harness runs.",
    )
    op.create_index(
        "idx_harness_run_intents_space_id",
        "harness_run_intents",
        ["space_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_run_intents_space_run",
        "harness_run_intents",
        ["space_id", "run_id"],
        unique=False,
        schema=schema,
    )

    op.create_table(
        "harness_run_approvals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("space_id", sa.UUID(), nullable=False),
        sa.Column("approval_key", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("target_type", sa.String(length=128), nullable=False),
        sa.Column("target_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("decision_reason", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "approval_key",
            name="uq_harness_run_approvals_run_id_approval_key",
        ),
        schema=schema,
        comment="Approval decisions for graph-harness runs.",
    )
    op.create_index(
        "idx_harness_run_approvals_run_id",
        "harness_run_approvals",
        ["run_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_run_approvals_space_id",
        "harness_run_approvals",
        ["space_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_run_approvals_status",
        "harness_run_approvals",
        ["status"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_run_approvals_space_run",
        "harness_run_approvals",
        ["space_id", "run_id"],
        unique=False,
        schema=schema,
    )


def downgrade() -> None:
    schema = harness_schema_name()

    op.drop_index(
        "idx_harness_run_approvals_space_run",
        table_name="harness_run_approvals",
        schema=schema,
    )
    op.drop_index(
        "idx_harness_run_approvals_status",
        table_name="harness_run_approvals",
        schema=schema,
    )
    op.drop_index(
        "idx_harness_run_approvals_space_id",
        table_name="harness_run_approvals",
        schema=schema,
    )
    op.drop_index(
        "idx_harness_run_approvals_run_id",
        table_name="harness_run_approvals",
        schema=schema,
    )
    op.drop_table("harness_run_approvals", schema=schema)

    op.drop_index(
        "idx_harness_run_intents_space_run",
        table_name="harness_run_intents",
        schema=schema,
    )
    op.drop_index(
        "idx_harness_run_intents_space_id",
        table_name="harness_run_intents",
        schema=schema,
    )
    op.drop_table("harness_run_intents", schema=schema)

    op.drop_index(
        "idx_harness_run_workspaces_space_run",
        table_name="harness_run_workspaces",
        schema=schema,
    )
    op.drop_index(
        "idx_harness_run_workspaces_space_id",
        table_name="harness_run_workspaces",
        schema=schema,
    )
    op.drop_table("harness_run_workspaces", schema=schema)

    op.drop_index(
        "idx_harness_run_artifacts_space_run",
        table_name="harness_run_artifacts",
        schema=schema,
    )
    op.drop_index(
        "idx_harness_run_artifacts_space_id",
        table_name="harness_run_artifacts",
        schema=schema,
    )
    op.drop_index(
        "idx_harness_run_artifacts_run_id",
        table_name="harness_run_artifacts",
        schema=schema,
    )
    op.drop_table("harness_run_artifacts", schema=schema)

    op.drop_index(
        "idx_harness_runs_space_created_at",
        table_name="harness_runs",
        schema=schema,
    )
    op.drop_index(
        "idx_harness_runs_status",
        table_name="harness_runs",
        schema=schema,
    )
    op.drop_index(
        "idx_harness_runs_harness_id",
        table_name="harness_runs",
        schema=schema,
    )
    op.drop_index(
        "idx_harness_runs_space_id",
        table_name="harness_runs",
        schema=schema,
    )
    op.drop_table("harness_runs", schema=schema)
