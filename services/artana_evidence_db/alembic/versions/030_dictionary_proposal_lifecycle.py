"""Expand dictionary proposal lifecycle and merge tracking."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_db.schema_support import graph_schema_name

revision = "030_proposal_lifecycle"
down_revision = "029_claim_idempotency"
branch_labels = None
depends_on = None


def _has_table(conn: sa.Connection, table: str, schema: str | None) -> bool:
    inspector = sa.inspect(conn)
    return table in inspector.get_table_names(schema=schema)


def _has_column(
    conn: sa.Connection,
    table: str,
    column: str,
    schema: str | None,
) -> bool:
    inspector = sa.inspect(conn)
    return any(
        existing["name"] == column
        for existing in inspector.get_columns(table, schema=schema)
    )


def upgrade() -> None:
    schema = graph_schema_name()
    conn = op.get_bind()
    if not _has_table(conn, "dictionary_proposals", schema):
        return
    is_sqlite = conn.dialect.name == "sqlite"

    if is_sqlite:
        with op.batch_alter_table("dictionary_proposals", schema=schema) as batch_op:
            if not _has_column(conn, "dictionary_proposals", "merge_target_type", schema):
                batch_op.add_column(
                    sa.Column("merge_target_type", sa.String(length=64), nullable=True)
                )
            if not _has_column(conn, "dictionary_proposals", "merge_target_id", schema):
                batch_op.add_column(
                    sa.Column("merge_target_id", sa.String(length=128), nullable=True)
                )
            batch_op.drop_constraint(
                "ck_dictionary_proposals_status",
                type_="check",
            )
            batch_op.create_check_constraint(
                "ck_dictionary_proposals_status",
                (
                    "status IN ("
                    "'SUBMITTED', 'CHANGES_REQUESTED', 'APPROVED', 'REJECTED', "
                    "'MERGED'"
                    ")"
                ),
            )
        return

    if not _has_column(conn, "dictionary_proposals", "merge_target_type", schema):
        op.add_column(
            "dictionary_proposals",
            sa.Column("merge_target_type", sa.String(length=64), nullable=True),
            schema=schema,
        )
    if not _has_column(conn, "dictionary_proposals", "merge_target_id", schema):
        op.add_column(
            "dictionary_proposals",
            sa.Column("merge_target_id", sa.String(length=128), nullable=True),
            schema=schema,
        )

    op.drop_constraint(
        "ck_dictionary_proposals_status",
        "dictionary_proposals",
        schema=schema,
        type_="check",
    )
    op.create_check_constraint(
        "ck_dictionary_proposals_status",
        "dictionary_proposals",
        (
            "status IN ("
            "'SUBMITTED', 'CHANGES_REQUESTED', 'APPROVED', 'REJECTED', 'MERGED'"
            ")"
        ),
        schema=schema,
    )


def downgrade() -> None:
    schema = graph_schema_name()
    conn = op.get_bind()
    if not _has_table(conn, "dictionary_proposals", schema):
        return
    is_sqlite = conn.dialect.name == "sqlite"

    if is_sqlite:
        with op.batch_alter_table("dictionary_proposals", schema=schema) as batch_op:
            batch_op.drop_constraint(
                "ck_dictionary_proposals_status",
                type_="check",
            )
            batch_op.create_check_constraint(
                "ck_dictionary_proposals_status",
                "status IN ('SUBMITTED', 'APPROVED', 'REJECTED')",
            )
            if _has_column(conn, "dictionary_proposals", "merge_target_id", schema):
                batch_op.drop_column("merge_target_id")
            if _has_column(conn, "dictionary_proposals", "merge_target_type", schema):
                batch_op.drop_column("merge_target_type")
        return

    op.drop_constraint(
        "ck_dictionary_proposals_status",
        "dictionary_proposals",
        schema=schema,
        type_="check",
    )
    op.create_check_constraint(
        "ck_dictionary_proposals_status",
        "dictionary_proposals",
        "status IN ('SUBMITTED', 'APPROVED', 'REJECTED')",
        schema=schema,
    )

    if _has_column(conn, "dictionary_proposals", "merge_target_id", schema):
        op.drop_column("dictionary_proposals", "merge_target_id", schema=schema)
    if _has_column(conn, "dictionary_proposals", "merge_target_type", schema):
        op.drop_column("dictionary_proposals", "merge_target_type", schema=schema)
