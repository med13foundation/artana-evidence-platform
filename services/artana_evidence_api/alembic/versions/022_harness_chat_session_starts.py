"""Add idempotent first-message chat-session starts."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_api.db_schema import harness_schema_name

revision = "022_harness_chat_session_starts"
down_revision = "021_source_search_handoffs"
branch_labels = None
depends_on = None


def _harness_fk_target(*, schema: str | None, table: str, column: str) -> str:
    if schema is None:
        return f"{table}.{column}"
    return f"{schema}.{table}.{column}"


def upgrade() -> None:
    schema = harness_schema_name()

    op.create_table(
        "harness_chat_session_starts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("space_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column(
            "request_signature_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("session_id", sa.UUID(), nullable=True),
        sa.Column("run_id", sa.UUID(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["session_id"],
            [
                _harness_fk_target(
                    schema=schema,
                    table="harness_chat_sessions",
                    column="id",
                ),
            ],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            [
                _harness_fk_target(
                    schema=schema,
                    table="harness_runs",
                    column="id",
                ),
            ],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "space_id",
            "created_by",
            "idempotency_key",
            name="uq_harness_chat_session_starts_idempotency",
        ),
        schema=schema,
        comment="Idempotent first-message chat-session start requests.",
    )
    op.create_index(
        "ix_harness_chat_session_starts_space_id",
        "harness_chat_session_starts",
        ["space_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_chat_session_starts_created_by",
        "harness_chat_session_starts",
        ["created_by"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_chat_session_starts_session_id",
        "harness_chat_session_starts",
        ["session_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_chat_session_starts_run_id",
        "harness_chat_session_starts",
        ["run_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_chat_session_starts_status",
        "harness_chat_session_starts",
        ["status"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_chat_session_starts_space_created",
        "harness_chat_session_starts",
        ["space_id", "created_at"],
        unique=False,
        schema=schema,
    )


def downgrade() -> None:
    schema = harness_schema_name()
    op.drop_index(
        "idx_harness_chat_session_starts_space_created",
        table_name="harness_chat_session_starts",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_chat_session_starts_status",
        table_name="harness_chat_session_starts",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_chat_session_starts_run_id",
        table_name="harness_chat_session_starts",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_chat_session_starts_session_id",
        table_name="harness_chat_session_starts",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_chat_session_starts_created_by",
        table_name="harness_chat_session_starts",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_chat_session_starts_space_id",
        table_name="harness_chat_session_starts",
        schema=schema,
    )
    op.drop_table("harness_chat_session_starts", schema=schema)
