"""Add evidence-grade fields to proposals and review items."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_api.db_schema import harness_schema_name

revision = "022_evidence_grade_proposals_review_items"
down_revision = "021_source_search_handoffs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    harness_schema = harness_schema_name()

    op.add_column(
        "harness_proposals",
        sa.Column("evidence_grade", sa.String(length=96), nullable=True),
        schema=harness_schema,
    )
    op.create_index(
        "ix_harness_proposals_evidence_grade",
        "harness_proposals",
        ["evidence_grade"],
        unique=False,
        schema=harness_schema,
    )
    op.add_column(
        "harness_review_items",
        sa.Column("evidence_grade", sa.String(length=96), nullable=True),
        schema=harness_schema,
    )
    op.create_index(
        "ix_harness_review_items_evidence_grade",
        "harness_review_items",
        ["evidence_grade"],
        unique=False,
        schema=harness_schema,
    )


def downgrade() -> None:
    harness_schema = harness_schema_name()

    op.drop_index(
        "ix_harness_review_items_evidence_grade",
        table_name="harness_review_items",
        schema=harness_schema,
    )
    op.drop_column(
        "harness_review_items",
        "evidence_grade",
        schema=harness_schema,
    )
    op.drop_index(
        "ix_harness_proposals_evidence_grade",
        table_name="harness_proposals",
        schema=harness_schema,
    )
    op.drop_column(
        "harness_proposals",
        "evidence_grade",
        schema=harness_schema,
    )
