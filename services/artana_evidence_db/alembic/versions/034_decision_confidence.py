"""Add DB-computed confidence fields for governed AI decisions."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_db.schema_support import graph_schema_name
from sqlalchemy.dialects import postgresql

revision = "034_decision_confidence"
down_revision = "033_graph_workflows"
branch_labels = None
depends_on = None


def _has_table(conn: sa.Connection, table: str, schema: str | None) -> bool:
    inspector = sa.inspect(conn)
    return table in inspector.get_table_names(schema=schema)


def _has_column(
    conn: sa.Connection,
    table: str,
    column: str,
    schema: str | None,
) -> bool:
    inspector = sa.inspect(conn)
    return any(item["name"] == column for item in inspector.get_columns(table, schema=schema))


def _add_if_missing(
    conn: sa.Connection,
    table: str,
    column: sa.Column,
    schema: str | None,
) -> None:
    if _has_table(conn, table, schema) and not _has_column(
        conn,
        table,
        column.name,
        schema,
    ):
        op.add_column(table, column, schema=schema)


def upgrade() -> None:
    schema = graph_schema_name()
    conn = op.get_bind()
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

    _add_if_missing(
        conn,
        "ai_full_mode_decisions",
        sa.Column("computed_confidence", sa.Float(), nullable=False, server_default="0.0"),
        schema,
    )
    _add_if_missing(
        conn,
        "ai_full_mode_decisions",
        sa.Column(
            "confidence_assessment_payload",
            json_type,
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        schema,
    )
    _add_if_missing(
        conn,
        "ai_full_mode_decisions",
        sa.Column("confidence_model_version", sa.String(length=64), nullable=True),
        schema,
    )
    _add_if_missing(
        conn,
        "graph_workflow_events",
        sa.Column("computed_confidence", sa.Float(), nullable=True),
        schema,
    )
    _add_if_missing(
        conn,
        "graph_workflow_events",
        sa.Column(
            "confidence_assessment_payload",
            json_type,
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        schema,
    )
    _add_if_missing(
        conn,
        "graph_workflow_events",
        sa.Column("confidence_model_version", sa.String(length=64), nullable=True),
        schema,
    )


def downgrade() -> None:
    schema = graph_schema_name()
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        return
    for table, column in [
        ("graph_workflow_events", "confidence_model_version"),
        ("graph_workflow_events", "confidence_assessment_payload"),
        ("graph_workflow_events", "computed_confidence"),
        ("ai_full_mode_decisions", "confidence_model_version"),
        ("ai_full_mode_decisions", "confidence_assessment_payload"),
        ("ai_full_mode_decisions", "computed_confidence"),
    ]:
        if _has_table(conn, table, schema) and _has_column(conn, table, column, schema):
            op.drop_column(table, column, schema=schema)
