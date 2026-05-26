"""Add structured study-outcome storage for clinical trial documents."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_api.db_schema import harness_schema_name

revision = "023_harness_study_outcomes"
down_revision = "022_evidence_grade_proposals_review_items"
branch_labels = None
depends_on = None


def _harness_fk_target(*, schema: str | None, table: str, column: str) -> str:
    if schema is None:
        return f"{table}.{column}"
    return f"{schema}.{table}.{column}"


def upgrade() -> None:
    harness_schema = harness_schema_name()

    op.create_table(
        "harness_study_outcomes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("space_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=True),
        sa.Column("intervention", sa.String(length=256), nullable=False),
        sa.Column("comparator", sa.String(length=256), nullable=True),
        sa.Column("outcome_metric", sa.String(length=96), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=64), nullable=False),
        sa.Column("confidence_interval_low", sa.Float(), nullable=True),
        sa.Column("confidence_interval_high", sa.Float(), nullable=True),
        sa.Column("population", sa.String(length=256), nullable=False),
        sa.Column("n", sa.Integer(), nullable=True),
        sa.Column("source_pmid", sa.String(length=64), nullable=False),
        sa.Column("source_quote", sa.Text(), nullable=False),
        sa.Column(
            "metadata_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("outcome_fingerprint", sa.String(length=64), nullable=False),
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
            ["document_id"],
            [
                _harness_fk_target(
                    schema=harness_schema,
                    table="harness_documents",
                    column="id",
                ),
            ],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            [
                _harness_fk_target(
                    schema=harness_schema,
                    table="harness_runs",
                    column="id",
                ),
            ],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "space_id",
            "outcome_fingerprint",
            name="uq_harness_study_outcomes_space_outcome_fingerprint",
        ),
        schema=harness_schema,
        comment="Quantitative trial outcomes extracted from harness documents.",
    )
    op.create_index(
        "ix_harness_study_outcomes_space_id",
        "harness_study_outcomes",
        ["space_id"],
        unique=False,
        schema=harness_schema,
    )
    op.create_index(
        "ix_harness_study_outcomes_document_id",
        "harness_study_outcomes",
        ["document_id"],
        unique=False,
        schema=harness_schema,
    )
    op.create_index(
        "ix_harness_study_outcomes_run_id",
        "harness_study_outcomes",
        ["run_id"],
        unique=False,
        schema=harness_schema,
    )
    op.create_index(
        "ix_harness_study_outcomes_intervention",
        "harness_study_outcomes",
        ["intervention"],
        unique=False,
        schema=harness_schema,
    )
    op.create_index(
        "ix_harness_study_outcomes_outcome_metric",
        "harness_study_outcomes",
        ["outcome_metric"],
        unique=False,
        schema=harness_schema,
    )
    op.create_index(
        "ix_harness_study_outcomes_population",
        "harness_study_outcomes",
        ["population"],
        unique=False,
        schema=harness_schema,
    )
    op.create_index(
        "ix_harness_study_outcomes_source_pmid",
        "harness_study_outcomes",
        ["source_pmid"],
        unique=False,
        schema=harness_schema,
    )
    op.create_index(
        "idx_harness_study_outcomes_space_intervention",
        "harness_study_outcomes",
        ["space_id", "intervention"],
        unique=False,
        schema=harness_schema,
    )
    op.create_index(
        "idx_harness_study_outcomes_space_metric",
        "harness_study_outcomes",
        ["space_id", "outcome_metric"],
        unique=False,
        schema=harness_schema,
    )
    op.create_index(
        "idx_harness_study_outcomes_document_created_at",
        "harness_study_outcomes",
        ["document_id", "created_at"],
        unique=False,
        schema=harness_schema,
    )


def downgrade() -> None:
    harness_schema = harness_schema_name()

    op.drop_index(
        "idx_harness_study_outcomes_document_created_at",
        table_name="harness_study_outcomes",
        schema=harness_schema,
    )
    op.drop_index(
        "idx_harness_study_outcomes_space_metric",
        table_name="harness_study_outcomes",
        schema=harness_schema,
    )
    op.drop_index(
        "idx_harness_study_outcomes_space_intervention",
        table_name="harness_study_outcomes",
        schema=harness_schema,
    )
    op.drop_index(
        "ix_harness_study_outcomes_source_pmid",
        table_name="harness_study_outcomes",
        schema=harness_schema,
    )
    op.drop_index(
        "ix_harness_study_outcomes_population",
        table_name="harness_study_outcomes",
        schema=harness_schema,
    )
    op.drop_index(
        "ix_harness_study_outcomes_outcome_metric",
        table_name="harness_study_outcomes",
        schema=harness_schema,
    )
    op.drop_index(
        "ix_harness_study_outcomes_intervention",
        table_name="harness_study_outcomes",
        schema=harness_schema,
    )
    op.drop_index(
        "ix_harness_study_outcomes_run_id",
        table_name="harness_study_outcomes",
        schema=harness_schema,
    )
    op.drop_index(
        "ix_harness_study_outcomes_document_id",
        table_name="harness_study_outcomes",
        schema=harness_schema,
    )
    op.drop_index(
        "ix_harness_study_outcomes_space_id",
        table_name="harness_study_outcomes",
        schema=harness_schema,
    )
    op.drop_table("harness_study_outcomes", schema=harness_schema)
