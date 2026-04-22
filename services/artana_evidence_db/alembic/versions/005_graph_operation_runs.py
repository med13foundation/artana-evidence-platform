"""Add graph-service operation history table."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_db.schema_support import graph_schema_name

revision = "005_graph_operation_runs"
down_revision = "004_graph_space_memberships"
branch_labels = None
depends_on = None


def upgrade() -> None:
    graph_schema = graph_schema_name()
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("graph_operation_runs", schema=graph_schema):
        return
    if graph_schema is not None:
        op.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{graph_schema}"'))

    uuid_type = sa.Uuid()
    operation_type_enum = sa.Enum(
        "projection_readiness_audit",
        "projection_repair",
        "reasoning_path_rebuild",
        "claim_participant_backfill",
        name="graphoperationruntypeenum",
    )
    status_enum = sa.Enum(
        "succeeded",
        "failed",
        name="graphoperationrunstatusenum",
    )
    operation_type_enum.create(op.get_bind(), checkfirst=True)
    status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "graph_operation_runs",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("operation_type", operation_type_enum, nullable=False),
        sa.Column("status", status_enum, nullable=False),
        sa.Column("research_space_id", uuid_type, nullable=True),
        sa.Column("actor_user_id", uuid_type, nullable=True),
        sa.Column("actor_email", sa.String(length=320), nullable=True),
        sa.Column(
            "dry_run",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("request_payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("summary_payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("failure_detail", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema=graph_schema,
        comment="Standalone graph-service operation history and audit trail",
    )
    op.create_index(
        "idx_graph_operation_runs_started_at",
        "graph_operation_runs",
        ["started_at"],
        unique=False,
        schema=graph_schema,
    )
    op.create_index(
        "idx_graph_operation_runs_type",
        "graph_operation_runs",
        ["operation_type"],
        unique=False,
        schema=graph_schema,
    )
    op.create_index(
        "idx_graph_operation_runs_status",
        "graph_operation_runs",
        ["status"],
        unique=False,
        schema=graph_schema,
    )
    op.create_index(
        "idx_graph_operation_runs_space",
        "graph_operation_runs",
        ["research_space_id"],
        unique=False,
        schema=graph_schema,
    )


def downgrade() -> None:
    return None
