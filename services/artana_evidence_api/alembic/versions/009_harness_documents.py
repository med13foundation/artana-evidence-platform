"""Add tracked harness documents and document-linked proposals."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_api.db_schema import harness_schema_name

revision = "009_harness_documents"
down_revision = "008_harness_ownership_cutover"
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
        "harness_documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("space_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=True),
        sa.Column("media_type", sa.String(length=128), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("text_content", sa.Text(), nullable=False),
        sa.Column("text_excerpt", sa.Text(), nullable=False),
        sa.Column("ingestion_run_id", sa.UUID(), nullable=False),
        sa.Column("last_extraction_run_id", sa.UUID(), nullable=True),
        sa.Column("enrichment_status", sa.String(length=32), nullable=False),
        sa.Column("extraction_status", sa.String(length=32), nullable=False),
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
            ["ingestion_run_id"],
            [_qualify("harness_runs", "id")],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["last_extraction_run_id"],
            [_qualify("harness_runs", "id")],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=schema,
        comment="Tracked harness-side source documents.",
    )
    op.create_index(
        "ix_harness_documents_space_id",
        "harness_documents",
        ["space_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_documents_created_by",
        "harness_documents",
        ["created_by"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_documents_source_type",
        "harness_documents",
        ["source_type"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_documents_sha256",
        "harness_documents",
        ["sha256"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_documents_ingestion_run_id",
        "harness_documents",
        ["ingestion_run_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_documents_last_extraction_run_id",
        "harness_documents",
        ["last_extraction_run_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_documents_enrichment_status",
        "harness_documents",
        ["enrichment_status"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_harness_documents_extraction_status",
        "harness_documents",
        ["extraction_status"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_harness_documents_space_updated_at",
        "harness_documents",
        ["space_id", "updated_at"],
        unique=False,
        schema=schema,
    )

    with op.batch_alter_table("harness_proposals", schema=schema) as batch_op:
        batch_op.add_column(sa.Column("document_id", sa.UUID(), nullable=True))
        batch_op.create_foreign_key(
            "fk_harness_proposals_document_id_harness_documents",
            "harness_documents",
            ["document_id"],
            ["id"],
            referent_schema=schema,
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_harness_proposals_document_id",
            ["document_id"],
            unique=False,
        )
        batch_op.create_index(
            "idx_harness_proposals_document_id",
            ["document_id"],
            unique=False,
        )


def downgrade() -> None:
    schema = harness_schema_name()

    with op.batch_alter_table("harness_proposals", schema=schema) as batch_op:
        batch_op.drop_index("idx_harness_proposals_document_id")
        batch_op.drop_index("ix_harness_proposals_document_id")
        batch_op.drop_constraint(
            "fk_harness_proposals_document_id_harness_documents",
            type_="foreignkey",
        )
        batch_op.drop_column("document_id")

    op.drop_index(
        "idx_harness_documents_space_updated_at",
        table_name="harness_documents",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_documents_extraction_status",
        table_name="harness_documents",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_documents_enrichment_status",
        table_name="harness_documents",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_documents_last_extraction_run_id",
        table_name="harness_documents",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_documents_ingestion_run_id",
        table_name="harness_documents",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_documents_sha256",
        table_name="harness_documents",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_documents_source_type",
        table_name="harness_documents",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_documents_created_by",
        table_name="harness_documents",
        schema=schema,
    )
    op.drop_index(
        "ix_harness_documents_space_id",
        table_name="harness_documents",
        schema=schema,
    )
    op.drop_table("harness_documents", schema=schema)
