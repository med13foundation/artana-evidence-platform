"""Backfill review audit timestamps missing from the initial reviews migration."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "017_add_review_timestamps"
down_revision = "016_add_reviews_table"
branch_labels = None
depends_on = None


def _shared_schema() -> str | None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return "public"
    return None


def _has_column(*, table_name: str, column_name: str, schema: str | None) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(
        column.get("name") == column_name
        for column in inspector.get_columns(table_name, schema=schema)
    )


def _add_timestamp_column(
    *, table_name: str, column_name: str, schema: str | None
) -> None:
    if _has_column(table_name=table_name, column_name=column_name, schema=schema):
        return
    op.add_column(
        table_name,
        sa.Column(
            column_name,
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        schema=schema,
    )


def upgrade() -> None:
    schema = _shared_schema()
    _add_timestamp_column(
        table_name="reviews",
        column_name="created_at",
        schema=schema,
    )
    _add_timestamp_column(
        table_name="reviews",
        column_name="updated_at",
        schema=schema,
    )


def downgrade() -> None:
    schema = _shared_schema()
    if _has_column(table_name="reviews", column_name="updated_at", schema=schema):
        op.drop_column("reviews", "updated_at", schema=schema)
    if _has_column(table_name="reviews", column_name="created_at", schema=schema):
        op.drop_column("reviews", "created_at", schema=schema)
