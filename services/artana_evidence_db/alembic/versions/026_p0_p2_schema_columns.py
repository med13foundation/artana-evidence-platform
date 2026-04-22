"""Add P0/P2 schema columns: assertion_class, canonicalization, evidence quality, constraint profile."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_db.schema_support import graph_schema_name

revision = "026_p0_p2_schema_columns"
down_revision = "025_entity_embedding_status"
branch_labels = None
depends_on = None


def _has_column(conn: sa.Connection, table: str, column: str, schema: str) -> bool:
    insp = sa.inspect(conn)
    return any(c["name"] == column for c in insp.get_columns(table, schema=schema))


def _add_if_missing(
    conn: sa.Connection,
    table: str,
    column: sa.Column,
    schema: str,
) -> None:
    if not _has_column(conn, table, column.name, schema):
        op.add_column(table, column, schema=schema)


def upgrade() -> None:
    schema = graph_schema_name()
    conn = op.get_bind()

    # P0.1: assertion_class on relation_claims
    _add_if_missing(
        conn,
        "relation_claims",
        sa.Column(
            "assertion_class",
            sa.String(32),
            nullable=False,
            server_default="SOURCE_BACKED",
        ),
        schema,
    )

    # P0.2: canonicalization_fingerprint on relations
    _add_if_missing(
        conn,
        "relations",
        sa.Column(
            "canonicalization_fingerprint",
            sa.String(128),
            nullable=False,
            server_default="",
        ),
        schema,
    )

    # P2.5: evidence quality fields on relations
    _add_if_missing(
        conn,
        "relations",
        sa.Column("support_confidence", sa.Float, nullable=False, server_default="0.0"),
        schema,
    )
    _add_if_missing(
        conn,
        "relations",
        sa.Column("refute_confidence", sa.Float, nullable=False, server_default="0.0"),
        schema,
    )
    _add_if_missing(
        conn,
        "relations",
        sa.Column(
            "distinct_source_family_count",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        schema,
    )

    # P0.5: profile on relation_constraints
    _add_if_missing(
        conn,
        "relation_constraints",
        sa.Column("profile", sa.String(32), nullable=False, server_default="ALLOWED"),
        schema,
    )


def downgrade() -> None:
    schema = graph_schema_name()
    conn = op.get_bind()
    dialect = conn.dialect.name

    # SQLite does not support DROP COLUMN; skip on test databases.
    if dialect == "sqlite":
        return

    for table, col in [
        ("relation_constraints", "profile"),
        ("relations", "distinct_source_family_count"),
        ("relations", "refute_confidence"),
        ("relations", "support_confidence"),
        ("relations", "canonicalization_fingerprint"),
        ("relation_claims", "assertion_class"),
    ]:
        if _has_column(conn, table, col, schema):
            op.drop_column(table, col, schema=schema)
