"""Add graph-owned external document reference fields."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_db.schema_support import graph_schema_name

revision = "006_graph_external_document_refs"
down_revision = "005_graph_operation_runs"
branch_labels = None
depends_on = None


def _has_column(
    inspector: sa.Inspector,
    table_name: str,
    column_name: str,
    *,
    schema: str | None,
) -> bool:
    return any(
        column["name"] == column_name
        for column in inspector.get_columns(table_name, schema=schema)
    )


def _has_index(
    inspector: sa.Inspector,
    table_name: str,
    index_name: str,
    *,
    schema: str | None,
) -> bool:
    return any(
        index["name"] == index_name
        for index in inspector.get_indexes(table_name, schema=schema)
    )


def _has_table(
    inspector: sa.Inspector,
    table_name: str,
    *,
    schema: str | None,
) -> bool:
    return inspector.has_table(table_name, schema=schema)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    schema = graph_schema_name()
    ref_column = sa.Column("source_document_ref", sa.String(length=512), nullable=True)

    additions = (
        ("relation_claims", "idx_relation_claims_source_document_ref"),
        ("claim_evidence", "idx_claim_evidence_source_document_ref"),
        ("claim_relations", "idx_claim_relations_source_document_ref"),
        (
            "relation_projection_sources",
            "idx_relation_projection_sources_source_document_ref",
        ),
        ("relation_evidence", "idx_relation_evidence_source_document_ref"),
    )
    for table_name, index_name in additions:
        if not _has_table(inspector, table_name, schema=schema):
            continue
        if not _has_column(
            inspector,
            table_name,
            "source_document_ref",
            schema=schema,
        ):
            op.add_column(table_name, ref_column.copy(), schema=schema)
        inspector = sa.inspect(bind)
        if not _has_index(inspector, table_name, index_name, schema=schema):
            op.create_index(
                index_name,
                table_name,
                ["source_document_ref"],
                unique=False,
                schema=schema,
            )
        inspector = sa.inspect(bind)


def downgrade() -> None:
    return None
