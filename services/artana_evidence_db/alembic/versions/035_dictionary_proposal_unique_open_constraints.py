"""Uniquely guard open relation-constraint proposals."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_db.schema_support import graph_schema_name

revision = "035_dict_proposal_open_uq"
down_revision = "034_decision_confidence"
branch_labels = None
depends_on = None

_INDEX_NAME = "uq_dictionary_proposals_open_relation_constraint_triple"
_PREDICATE = (
    "proposal_type = 'RELATION_CONSTRAINT' "
    "AND status IN ('SUBMITTED', 'CHANGES_REQUESTED')"
)


def _has_table(conn: sa.Connection, table: str, schema: str | None) -> bool:
    inspector = sa.inspect(conn)
    return table in inspector.get_table_names(schema=schema)


def _has_index(
    conn: sa.Connection,
    *,
    table: str,
    schema: str | None,
    index_name: str,
) -> bool:
    inspector = sa.inspect(conn)
    return any(
        item["name"] == index_name
        for item in inspector.get_indexes(table, schema=schema)
    )


def upgrade() -> None:
    schema = graph_schema_name()
    conn = op.get_bind()
    if not _has_table(conn, "dictionary_proposals", schema):
        return
    if _has_index(
        conn,
        table="dictionary_proposals",
        schema=schema,
        index_name=_INDEX_NAME,
    ):
        return

    op.create_index(
        _INDEX_NAME,
        "dictionary_proposals",
        ["source_type", "relation_type", "target_type"],
        unique=True,
        schema=schema,
        postgresql_where=sa.text(_PREDICATE),
        sqlite_where=sa.text(_PREDICATE),
    )


def downgrade() -> None:
    schema = graph_schema_name()
    conn = op.get_bind()
    if not _has_table(conn, "dictionary_proposals", schema):
        return
    if not _has_index(
        conn,
        table="dictionary_proposals",
        schema=schema,
        index_name=_INDEX_NAME,
    ):
        return
    op.drop_index(
        _INDEX_NAME,
        table_name="dictionary_proposals",
        schema=schema,
    )
