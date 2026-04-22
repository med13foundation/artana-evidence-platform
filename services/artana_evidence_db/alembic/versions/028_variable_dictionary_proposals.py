"""Add variable proposal fields to governed dictionary proposals."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_db.schema_support import graph_schema_name
from sqlalchemy.dialects import postgresql

revision = "028_variable_proposals"
down_revision = "027_dictionary_proposals"
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


def _constraints_type(conn: sa.Connection) -> sa.TypeEngine[object]:
    if conn.dialect.name == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def _constraints_default(conn: sa.Connection) -> sa.TextClause | str:
    if conn.dialect.name == "postgresql":
        return sa.text("'{}'::jsonb")
    return "{}"


def _recreate_type_constraint(*, schema: str | None, include_variable: bool) -> None:
    proposal_types = (
        "'DOMAIN_CONTEXT', 'ENTITY_TYPE', 'RELATION_TYPE', "
        "'RELATION_CONSTRAINT', 'RELATION_SYNONYM', 'VALUE_SET', 'VALUE_SET_ITEM'"
    )
    if include_variable:
        proposal_types = (
            "'DOMAIN_CONTEXT', 'ENTITY_TYPE', 'VARIABLE', 'RELATION_TYPE', "
            "'RELATION_CONSTRAINT', 'RELATION_SYNONYM', "
            "'VALUE_SET', 'VALUE_SET_ITEM'"
        )
    op.drop_constraint(
        "ck_dictionary_proposals_type",
        "dictionary_proposals",
        schema=schema,
        type_="check",
    )
    op.create_check_constraint(
        "ck_dictionary_proposals_type",
        "dictionary_proposals",
        f"proposal_type IN ({proposal_types})",
        schema=schema,
    )


def upgrade() -> None:
    schema = graph_schema_name()
    conn = op.get_bind()
    if not _has_table(conn, "dictionary_proposals", schema):
        return

    constraints_type = _constraints_type(conn)
    constraints_default = _constraints_default(conn)

    if not _has_column(
        conn,
        table="dictionary_proposals",
        column="canonical_name",
        schema=schema,
    ):
        op.add_column(
            "dictionary_proposals",
            sa.Column("canonical_name", sa.String(length=128), nullable=True),
            schema=schema,
        )
    if not _has_column(
        conn,
        table="dictionary_proposals",
        column="data_type",
        schema=schema,
    ):
        op.add_column(
            "dictionary_proposals",
            sa.Column("data_type", sa.String(length=32), nullable=True),
            schema=schema,
        )
    if not _has_column(
        conn,
        table="dictionary_proposals",
        column="preferred_unit",
        schema=schema,
    ):
        op.add_column(
            "dictionary_proposals",
            sa.Column("preferred_unit", sa.String(length=64), nullable=True),
            schema=schema,
        )
    if not _has_column(
        conn,
        table="dictionary_proposals",
        column="constraints",
        schema=schema,
    ):
        op.add_column(
            "dictionary_proposals",
            sa.Column(
                "constraints",
                constraints_type,
                nullable=False,
                server_default=constraints_default,
            ),
            schema=schema,
        )
    if not _has_column(
        conn,
        table="dictionary_proposals",
        column="sensitivity",
        schema=schema,
    ):
        op.add_column(
            "dictionary_proposals",
            sa.Column("sensitivity", sa.String(length=32), nullable=True),
            schema=schema,
        )
    if not _has_column(
        conn,
        table="dictionary_proposals",
        column="applied_variable_id",
        schema=schema,
    ):
        op.add_column(
            "dictionary_proposals",
            sa.Column("applied_variable_id", sa.String(length=64), nullable=True),
            schema=schema,
        )
        op.create_foreign_key(
            "fk_dictionary_proposals_applied_variable_id",
            "dictionary_proposals",
            "variable_definitions",
            ["applied_variable_id"],
            ["id"],
            source_schema=schema,
            referent_schema=schema,
        )

    if conn.dialect.name != "sqlite":
        _recreate_type_constraint(schema=schema, include_variable=True)


def downgrade() -> None:
    schema = graph_schema_name()
    conn = op.get_bind()
    if not _has_table(conn, "dictionary_proposals", schema):
        return

    if conn.dialect.name != "sqlite":
        _recreate_type_constraint(schema=schema, include_variable=False)

    if _has_column(
        conn,
        table="dictionary_proposals",
        column="applied_variable_id",
        schema=schema,
    ):
        op.drop_constraint(
            "fk_dictionary_proposals_applied_variable_id",
            "dictionary_proposals",
            schema=schema,
            type_="foreignkey",
        )
        op.drop_column("dictionary_proposals", "applied_variable_id", schema=schema)
    if _has_column(
        conn,
        table="dictionary_proposals",
        column="sensitivity",
        schema=schema,
    ):
        op.drop_column("dictionary_proposals", "sensitivity", schema=schema)
    if _has_column(
        conn,
        table="dictionary_proposals",
        column="constraints",
        schema=schema,
    ):
        op.drop_column("dictionary_proposals", "constraints", schema=schema)
    if _has_column(
        conn,
        table="dictionary_proposals",
        column="preferred_unit",
        schema=schema,
    ):
        op.drop_column("dictionary_proposals", "preferred_unit", schema=schema)
    if _has_column(
        conn,
        table="dictionary_proposals",
        column="data_type",
        schema=schema,
    ):
        op.drop_column("dictionary_proposals", "data_type", schema=schema)
    if _has_column(
        conn,
        table="dictionary_proposals",
        column="canonical_name",
        schema=schema,
    ):
        op.drop_column("dictionary_proposals", "canonical_name", schema=schema)
