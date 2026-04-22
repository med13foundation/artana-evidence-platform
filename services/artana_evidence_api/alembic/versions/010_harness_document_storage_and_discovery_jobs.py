"""Add harness document storage columns and discovery job tables."""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op
from artana_evidence_api.db_schema import (
    harness_schema_name,
    qualify_shared_platform_foreign_key_target,
    shared_platform_schema_name,
)

revision = "010_doc_storage_discovery"
down_revision = "009_harness_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    harness_schema = harness_schema_name()
    database_url = (
        os.getenv("ALEMBIC_DATABASE_URL")
        or os.getenv("ARTANA_EVIDENCE_API_DATABASE_URL")
        or os.getenv("DATABASE_URL")
    )
    platform_schema = shared_platform_schema_name(database_url)

    with op.batch_alter_table("harness_documents", schema=harness_schema) as batch_op:
        batch_op.add_column(
            sa.Column("raw_storage_key", sa.String(length=512), nullable=True),
        )
        batch_op.add_column(
            sa.Column("enriched_storage_key", sa.String(length=512), nullable=True),
        )
        batch_op.add_column(
            sa.Column("last_enrichment_run_id", sa.UUID(), nullable=True),
        )
        batch_op.create_foreign_key(
            "fk_harness_documents_last_enrichment_run_id_harness_runs",
            "harness_runs",
            ["last_enrichment_run_id"],
            ["id"],
            referent_schema=harness_schema,
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_harness_documents_last_enrichment_run_id",
            ["last_enrichment_run_id"],
            unique=False,
        )

    op.create_table(
        "data_discovery_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("research_space_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("gene_symbol", sa.String(length=100), nullable=True),
        sa.Column("search_term", sa.Text(), nullable=True),
        sa.Column(
            "selected_sources",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "tested_sources",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "pubmed_search_config",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "total_tests_run",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "successful_tests",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=platform_schema,
    )
    op.create_index(
        "ix_data_discovery_sessions_owner_id",
        "data_discovery_sessions",
        ["owner_id"],
        unique=False,
        schema=platform_schema,
    )
    op.create_index(
        "ix_data_discovery_sessions_research_space_id",
        "data_discovery_sessions",
        ["research_space_id"],
        unique=False,
        schema=platform_schema,
    )

    op.create_table(
        "discovery_search_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("query_preview", sa.Text(), nullable=False),
        sa.Column(
            "parameters",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "total_results",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "result_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("storage_key", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"],
            [
                qualify_shared_platform_foreign_key_target(
                    "data_discovery_sessions.id",
                    database_url=database_url,
                ),
            ],
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=platform_schema,
    )
    op.create_index(
        "ix_discovery_search_jobs_owner_id",
        "discovery_search_jobs",
        ["owner_id"],
        unique=False,
        schema=platform_schema,
    )
    op.create_index(
        "ix_discovery_search_jobs_session_id",
        "discovery_search_jobs",
        ["session_id"],
        unique=False,
        schema=platform_schema,
    )
    op.create_index(
        "ix_discovery_search_jobs_provider",
        "discovery_search_jobs",
        ["provider"],
        unique=False,
        schema=platform_schema,
    )
    op.create_index(
        "ix_discovery_search_jobs_status",
        "discovery_search_jobs",
        ["status"],
        unique=False,
        schema=platform_schema,
    )


def downgrade() -> None:
    harness_schema = harness_schema_name()
    database_url = (
        os.getenv("ALEMBIC_DATABASE_URL")
        or os.getenv("ARTANA_EVIDENCE_API_DATABASE_URL")
        or os.getenv("DATABASE_URL")
    )
    platform_schema = shared_platform_schema_name(database_url)

    op.drop_index(
        "ix_discovery_search_jobs_status",
        table_name="discovery_search_jobs",
        schema=platform_schema,
    )
    op.drop_index(
        "ix_discovery_search_jobs_provider",
        table_name="discovery_search_jobs",
        schema=platform_schema,
    )
    op.drop_index(
        "ix_discovery_search_jobs_session_id",
        table_name="discovery_search_jobs",
        schema=platform_schema,
    )
    op.drop_index(
        "ix_discovery_search_jobs_owner_id",
        table_name="discovery_search_jobs",
        schema=platform_schema,
    )
    op.drop_table("discovery_search_jobs", schema=platform_schema)

    op.drop_index(
        "ix_data_discovery_sessions_research_space_id",
        table_name="data_discovery_sessions",
        schema=platform_schema,
    )
    op.drop_index(
        "ix_data_discovery_sessions_owner_id",
        table_name="data_discovery_sessions",
        schema=platform_schema,
    )
    op.drop_table("data_discovery_sessions", schema=platform_schema)

    with op.batch_alter_table("harness_documents", schema=harness_schema) as batch_op:
        batch_op.drop_index("ix_harness_documents_last_enrichment_run_id")
        batch_op.drop_constraint(
            "fk_harness_documents_last_enrichment_run_id_harness_runs",
            type_="foreignkey",
        )
        batch_op.drop_column("last_enrichment_run_id")
        batch_op.drop_column("enriched_storage_key")
        batch_op.drop_column("raw_storage_key")
