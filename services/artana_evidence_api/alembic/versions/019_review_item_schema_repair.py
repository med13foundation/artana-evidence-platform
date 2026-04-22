"""Repair harness review-item schema drift on older local databases."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_api.db_schema import harness_schema_name
from sqlalchemy import inspect

revision = "019_review_item_schema_repair"
down_revision = "018_harness_review_items"
branch_labels = None
depends_on = None


def _table_name() -> str:
    schema = harness_schema_name()
    if schema is None:
        return "harness_review_items"
    return f"{schema}.harness_review_items"


def _has_column(inspector: sa.Inspector, *, schema: str | None, column_name: str) -> bool:
    columns = inspector.get_columns("harness_review_items", schema=schema)
    return any(column["name"] == column_name for column in columns)


def _has_index(inspector: sa.Inspector, *, schema: str | None, index_name: str) -> bool:
    indexes = inspector.get_indexes("harness_review_items", schema=schema)
    return any(index["name"] == index_name for index in indexes)


def upgrade() -> None:
    schema = harness_schema_name()
    bind = op.get_bind()
    inspector = inspect(bind)

    if not _has_column(inspector, schema=schema, column_name="source_family"):
        op.add_column(
            "harness_review_items",
            sa.Column("source_family", sa.String(length=64), nullable=True),
            schema=schema,
        )
        op.execute(
            sa.text(
                f"""
                UPDATE {_table_name()}
                SET source_family = lower(source_kind)
                WHERE source_family IS NULL AND source_kind IS NOT NULL
                """,
            ),
        )
        op.execute(
            sa.text(
                f"""
                UPDATE {_table_name()}
                SET source_family = 'review_item'
                WHERE source_family IS NULL
                """,
            ),
        )
        op.alter_column(
            "harness_review_items",
            "source_family",
            existing_type=sa.String(length=64),
            nullable=False,
            schema=schema,
        )

    if not _has_column(inspector, schema=schema, column_name="linked_proposal_id"):
        op.add_column(
            "harness_review_items",
            sa.Column("linked_proposal_id", sa.UUID(), nullable=True),
            schema=schema,
        )

    if not _has_column(inspector, schema=schema, column_name="linked_approval_key"):
        op.add_column(
            "harness_review_items",
            sa.Column("linked_approval_key", sa.String(length=255), nullable=True),
            schema=schema,
        )

    inspector = inspect(bind)

    if not _has_index(
        inspector,
        schema=schema,
        index_name="ix_harness_review_items_source_family",
    ):
        op.create_index(
            "ix_harness_review_items_source_family",
            "harness_review_items",
            ["source_family"],
            unique=False,
            schema=schema,
        )

    if not _has_index(
        inspector,
        schema=schema,
        index_name="ix_harness_review_items_linked_proposal_id",
    ):
        op.create_index(
            "ix_harness_review_items_linked_proposal_id",
            "harness_review_items",
            ["linked_proposal_id"],
            unique=False,
            schema=schema,
        )

    if not _has_index(
        inspector,
        schema=schema,
        index_name="ix_harness_review_items_linked_approval_key",
    ):
        op.create_index(
            "ix_harness_review_items_linked_approval_key",
            "harness_review_items",
            ["linked_approval_key"],
            unique=False,
            schema=schema,
        )

    if not _has_index(
        inspector,
        schema=schema,
        index_name="uq_harness_review_items_space_review_fingerprint",
    ):
        op.create_index(
            "uq_harness_review_items_space_review_fingerprint",
            "harness_review_items",
            ["space_id", "review_fingerprint"],
            unique=True,
            schema=schema,
            postgresql_where=sa.text("review_fingerprint IS NOT NULL"),
        )

    if not _has_index(
        inspector,
        schema=schema,
        index_name="uq_harness_review_items_space_type_source_key_null_fp",
    ):
        op.create_index(
            "uq_harness_review_items_space_type_source_key_null_fp",
            "harness_review_items",
            ["space_id", "review_type", "source_key"],
            unique=True,
            schema=schema,
            postgresql_where=sa.text("review_fingerprint IS NULL"),
        )


def downgrade() -> None:
    schema = harness_schema_name()
    bind = op.get_bind()
    inspector = inspect(bind)

    if _has_index(
        inspector,
        schema=schema,
        index_name="uq_harness_review_items_space_type_source_key_null_fp",
    ):
        op.drop_index(
            "uq_harness_review_items_space_type_source_key_null_fp",
            table_name="harness_review_items",
            schema=schema,
        )

    if _has_index(
        inspector,
        schema=schema,
        index_name="uq_harness_review_items_space_review_fingerprint",
    ):
        op.drop_index(
            "uq_harness_review_items_space_review_fingerprint",
            table_name="harness_review_items",
            schema=schema,
        )

    if _has_index(
        inspector,
        schema=schema,
        index_name="ix_harness_review_items_linked_approval_key",
    ):
        op.drop_index(
            "ix_harness_review_items_linked_approval_key",
            table_name="harness_review_items",
            schema=schema,
        )

    if _has_index(
        inspector,
        schema=schema,
        index_name="ix_harness_review_items_linked_proposal_id",
    ):
        op.drop_index(
            "ix_harness_review_items_linked_proposal_id",
            table_name="harness_review_items",
            schema=schema,
        )

    if _has_index(
        inspector,
        schema=schema,
        index_name="ix_harness_review_items_source_family",
    ):
        op.drop_index(
            "ix_harness_review_items_source_family",
            table_name="harness_review_items",
            schema=schema,
        )

    inspector = inspect(bind)
    if _has_column(inspector, schema=schema, column_name="linked_approval_key"):
        op.drop_column("harness_review_items", "linked_approval_key", schema=schema)
    if _has_column(inspector, schema=schema, column_name="linked_proposal_id"):
        op.drop_column("harness_review_items", "linked_proposal_id", schema=schema)
    if _has_column(inspector, schema=schema, column_name="source_family"):
        op.drop_column("harness_review_items", "source_family", schema=schema)
