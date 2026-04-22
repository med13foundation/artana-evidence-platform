"""Add claim and proposal idempotency constraints."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_db.schema_support import graph_schema_name

revision = "029_claim_idempotency"
down_revision = "028_variable_proposals"
branch_labels = None
depends_on = None


def _has_table(conn: sa.Connection, table: str, schema: str | None) -> bool:
    inspector = sa.inspect(conn)
    return table in inspector.get_table_names(schema=schema)


def _has_column(
    conn: sa.Connection,
    *,
    table: str,
    column: str,
    schema: str | None,
) -> bool:
    inspector = sa.inspect(conn)
    return any(
        existing["name"] == column
        for existing in inspector.get_columns(table, schema=schema)
    )


def _has_unique_constraint(
    conn: sa.Connection,
    *,
    table: str,
    name: str,
    schema: str | None,
) -> bool:
    inspector = sa.inspect(conn)
    return any(
        constraint["name"] == name
        for constraint in inspector.get_unique_constraints(table, schema=schema)
    )


def _has_index(
    conn: sa.Connection,
    *,
    table: str,
    name: str,
    schema: str | None,
) -> bool:
    inspector = sa.inspect(conn)
    return any(index["name"] == name for index in inspector.get_indexes(table, schema=schema))


def upgrade() -> None:
    schema = graph_schema_name()
    conn = op.get_bind()

    if _has_table(conn, "dictionary_proposals", schema) and not _has_unique_constraint(
        conn,
        table="dictionary_proposals",
        name="uq_dictionary_proposals_source_ref",
        schema=schema,
    ):
        op.create_unique_constraint(
            "uq_dictionary_proposals_source_ref",
            "dictionary_proposals",
            ["source_ref"],
            schema=schema,
        )

    if not _has_table(conn, "relation_claims", schema):
        return

    if not _has_column(conn, table="relation_claims", column="source_ref", schema=schema):
        op.add_column(
            "relation_claims",
            sa.Column("source_ref", sa.String(length=1024), nullable=True),
            schema=schema,
        )

    if not _has_unique_constraint(
        conn,
        table="relation_claims",
        name="uq_relation_claims_space_source_ref",
        schema=schema,
    ):
        op.create_unique_constraint(
            "uq_relation_claims_space_source_ref",
            "relation_claims",
            ["research_space_id", "source_ref"],
            schema=schema,
        )

    if not _has_index(
        conn,
        table="relation_claims",
        name="idx_relation_claims_source_ref",
        schema=schema,
    ):
        op.create_index(
            "idx_relation_claims_source_ref",
            "relation_claims",
            ["source_ref"],
            schema=schema,
        )


def downgrade() -> None:
    schema = graph_schema_name()
    conn = op.get_bind()

    if _has_table(conn, "relation_claims", schema):
        if _has_index(
            conn,
            table="relation_claims",
            name="idx_relation_claims_source_ref",
            schema=schema,
        ):
            op.drop_index(
                "idx_relation_claims_source_ref",
                table_name="relation_claims",
                schema=schema,
            )
        if _has_unique_constraint(
            conn,
            table="relation_claims",
            name="uq_relation_claims_space_source_ref",
            schema=schema,
        ):
            op.drop_constraint(
                "uq_relation_claims_space_source_ref",
                "relation_claims",
                schema=schema,
                type_="unique",
            )
        if _has_column(conn, table="relation_claims", column="source_ref", schema=schema):
            op.drop_column("relation_claims", "source_ref", schema=schema)

    if _has_table(conn, "dictionary_proposals", schema) and _has_unique_constraint(
        conn,
        table="dictionary_proposals",
        name="uq_dictionary_proposals_source_ref",
        schema=schema,
    ):
        op.drop_constraint(
            "uq_dictionary_proposals_source_ref",
            "dictionary_proposals",
            schema=schema,
            type_="unique",
        )
