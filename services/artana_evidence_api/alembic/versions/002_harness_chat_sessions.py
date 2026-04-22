"""Add durable graph-harness chat session tables."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_api.db_schema import harness_schema_name

revision = "002_harness_chat_sessions"
down_revision = "001_harness_runtime_tables"
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
        "harness_chat_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("space_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("last_run_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
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
        comment="Graph-harness chat session metadata.",
    )
    op.create_index(
        "idx_harness_chat_sessions_space_id",
        "harness_chat_sessions",
        ["space_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_chat_sessions_created_by",
        "harness_chat_sessions",
        ["created_by"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_chat_sessions_last_run_id",
        "harness_chat_sessions",
        ["last_run_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_chat_sessions_status",
        "harness_chat_sessions",
        ["status"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_chat_sessions_space_updated_at",
        "harness_chat_sessions",
        ["space_id", "updated_at"],
        unique=False,
        schema=schema,
    )

    op.create_table(
        "harness_chat_messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("space_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=True),
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
            ["session_id"],
            [_qualify("harness_chat_sessions", "id")],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=schema,
        comment="Message history for graph-harness chat sessions.",
    )
    op.create_index(
        "idx_harness_chat_messages_session_id",
        "harness_chat_messages",
        ["session_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_chat_messages_space_id",
        "harness_chat_messages",
        ["space_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_chat_messages_role",
        "harness_chat_messages",
        ["role"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_chat_messages_run_id",
        "harness_chat_messages",
        ["run_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_chat_messages_session_created_at",
        "harness_chat_messages",
        ["session_id", "created_at"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_chat_messages_space_session",
        "harness_chat_messages",
        ["space_id", "session_id"],
        unique=False,
        schema=schema,
    )


def downgrade() -> None:
    schema = harness_schema_name()

    op.drop_index(
        "idx_harness_chat_messages_space_session",
        table_name="harness_chat_messages",
        schema=schema,
    )
    op.drop_index(
        "idx_harness_chat_messages_session_created_at",
        table_name="harness_chat_messages",
        schema=schema,
    )
    op.drop_index(
        "idx_harness_chat_messages_run_id",
        table_name="harness_chat_messages",
        schema=schema,
    )
    op.drop_index(
        "idx_harness_chat_messages_role",
        table_name="harness_chat_messages",
        schema=schema,
    )
    op.drop_index(
        "idx_harness_chat_messages_space_id",
        table_name="harness_chat_messages",
        schema=schema,
    )
    op.drop_index(
        "idx_harness_chat_messages_session_id",
        table_name="harness_chat_messages",
        schema=schema,
    )
    op.drop_table("harness_chat_messages", schema=schema)

    op.drop_index(
        "idx_harness_chat_sessions_space_updated_at",
        table_name="harness_chat_sessions",
        schema=schema,
    )
    op.drop_index(
        "idx_harness_chat_sessions_status",
        table_name="harness_chat_sessions",
        schema=schema,
    )
    op.drop_index(
        "idx_harness_chat_sessions_last_run_id",
        table_name="harness_chat_sessions",
        schema=schema,
    )
    op.drop_index(
        "idx_harness_chat_sessions_created_by",
        table_name="harness_chat_sessions",
        schema=schema,
    )
    op.drop_index(
        "idx_harness_chat_sessions_space_id",
        table_name="harness_chat_sessions",
        schema=schema,
    )
    op.drop_table("harness_chat_sessions", schema=schema)
