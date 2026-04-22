"""Add unified graph workflow ledgers."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_db.schema_support import (
    graph_schema_name,
    qualify_graph_foreign_key_target,
)
from sqlalchemy.dialects import postgresql

revision = "033_graph_workflows"
down_revision = "032_ai_full_mode_governance"
branch_labels = None
depends_on = None


def _has_table(conn: sa.Connection, table: str, schema: str | None) -> bool:
    inspector = sa.inspect(conn)
    return table in inspector.get_table_names(schema=schema)


def upgrade() -> None:
    schema = graph_schema_name()
    conn = op.get_bind()
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    graph_spaces_fk = qualify_graph_foreign_key_target(
        "graph_spaces.id",
        schema=schema,
    )
    graph_workflows_fk = qualify_graph_foreign_key_target(
        "graph_workflows.id",
        schema=schema,
    )

    if not _has_table(conn, "graph_workflows", schema):
        op.create_table(
            "graph_workflows",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("research_space_id", sa.UUID(), nullable=False),
            sa.Column("kind", sa.String(length=48), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("operating_mode", sa.String(length=48), nullable=False),
            sa.Column(
                "input_payload",
                json_type,
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.Column(
                "plan_payload",
                json_type,
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.Column(
                "generated_resources_payload",
                json_type,
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.Column(
                "decision_payload",
                json_type,
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.Column(
                "policy_payload",
                json_type,
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.Column(
                "explanation_payload",
                json_type,
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.Column("source_ref", sa.String(length=1024), nullable=True),
            sa.Column("workflow_hash", sa.String(length=64), nullable=False),
            sa.Column("created_by", sa.String(length=128), nullable=False),
            sa.Column("updated_by", sa.String(length=128), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.PrimaryKeyConstraint("id", name="pk_graph_workflows"),
            sa.ForeignKeyConstraint(
                ["research_space_id"],
                [graph_spaces_fk],
                name="fk_graph_workflows_space",
            ),
            sa.UniqueConstraint(
                "research_space_id",
                "source_ref",
                name="uq_graph_workflows_space_source_ref",
            ),
            sa.CheckConstraint(
                "kind IN ('evidence_approval', 'batch_review', "
                "'ai_evidence_decision', 'conflict_resolution', "
                "'continuous_learning_review', 'bootstrap_review')",
                name="ck_graph_workflows_kind",
            ),
            sa.CheckConstraint(
                "status IN ('SUBMITTED', 'PLAN_READY', 'WAITING_REVIEW', "
                "'APPLIED', 'REJECTED', 'CHANGES_REQUESTED', 'BLOCKED', 'FAILED')",
                name="ck_graph_workflows_status",
            ),
            sa.CheckConstraint(
                "operating_mode IN ('manual', 'ai_assist_human_batch', "
                "'human_evidence_ai_graph', 'ai_full_graph', 'ai_full_evidence', "
                "'continuous_learning')",
                name="ck_graph_workflows_operating_mode",
            ),
            schema=schema,
        )
        op.create_index(
            "idx_graph_workflows_space_status",
            "graph_workflows",
            ["research_space_id", "status"],
            schema=schema,
        )
        op.create_index(
            "idx_graph_workflows_space_kind",
            "graph_workflows",
            ["research_space_id", "kind"],
            schema=schema,
        )
        op.create_index(
            "idx_graph_workflows_space_source_ref",
            "graph_workflows",
            ["research_space_id", "source_ref"],
            schema=schema,
        )

    if not _has_table(conn, "graph_workflow_events", schema):
        op.create_table(
            "graph_workflow_events",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("workflow_id", sa.UUID(), nullable=False),
            sa.Column("research_space_id", sa.UUID(), nullable=False),
            sa.Column("actor", sa.String(length=128), nullable=False),
            sa.Column("action", sa.String(length=64), nullable=False),
            sa.Column("before_status", sa.String(length=32), nullable=True),
            sa.Column("after_status", sa.String(length=32), nullable=False),
            sa.Column("risk_tier", sa.String(length=16), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("input_hash", sa.String(length=64), nullable=True),
            sa.Column(
                "policy_outcome_payload",
                json_type,
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.Column(
                "generated_resources_payload",
                json_type,
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column(
                "event_payload",
                json_type,
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.PrimaryKeyConstraint("id", name="pk_graph_workflow_events"),
            sa.ForeignKeyConstraint(
                ["workflow_id"],
                [graph_workflows_fk],
                name="fk_graph_workflow_events_workflow",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["research_space_id"],
                [graph_spaces_fk],
                name="fk_graph_workflow_events_space",
            ),
            sa.CheckConstraint(
                "after_status IN ('SUBMITTED', 'PLAN_READY', 'WAITING_REVIEW', "
                "'APPLIED', 'REJECTED', 'CHANGES_REQUESTED', 'BLOCKED', 'FAILED')",
                name="ck_graph_workflow_events_after_status",
            ),
            sa.CheckConstraint(
                "before_status IS NULL OR before_status IN ('SUBMITTED', "
                "'PLAN_READY', 'WAITING_REVIEW', 'APPLIED', 'REJECTED', "
                "'CHANGES_REQUESTED', 'BLOCKED', 'FAILED')",
                name="ck_graph_workflow_events_before_status",
            ),
            sa.CheckConstraint(
                "risk_tier IS NULL OR risk_tier IN ('low', 'medium', 'high')",
                name="ck_graph_workflow_events_risk_tier",
            ),
            sa.CheckConstraint(
                "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
                name="ck_graph_workflow_events_confidence",
            ),
            schema=schema,
        )
        op.create_index(
            "idx_graph_workflow_events_workflow",
            "graph_workflow_events",
            ["workflow_id", "created_at"],
            schema=schema,
        )
        op.create_index(
            "idx_graph_workflow_events_space",
            "graph_workflow_events",
            ["research_space_id", "created_at"],
            schema=schema,
        )


def downgrade() -> None:
    schema = graph_schema_name()
    conn = op.get_bind()
    drops = (
        (
            "graph_workflow_events",
            (
                "idx_graph_workflow_events_space",
                "idx_graph_workflow_events_workflow",
            ),
        ),
        (
            "graph_workflows",
            (
                "idx_graph_workflows_space_source_ref",
                "idx_graph_workflows_space_kind",
                "idx_graph_workflows_space_status",
            ),
        ),
    )
    for table_name, index_names in drops:
        if not _has_table(conn, table_name, schema):
            continue
        for index_name in index_names:
            op.drop_index(index_name, table_name=table_name, schema=schema)
        op.drop_table(table_name, schema=schema)
