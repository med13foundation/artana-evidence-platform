"""Add immutable graph-owned source evidence snapshots."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_db.schema_support import graph_schema_name
from sqlalchemy.dialects import postgresql

revision = "036_source_evidence_snapshots"
down_revision = "035_dict_proposal_open_uq"
branch_labels = None
depends_on = None

_UPDATE_TRIGGER = "trg_source_evidence_snapshots_no_update"
_DELETE_TRIGGER = "trg_source_evidence_snapshots_no_delete"
_PG_FUNCTION = "reject_source_evidence_snapshot_mutation"


def _has_table(conn: sa.Connection, table: str, schema: str | None) -> bool:
    return sa.inspect(conn).has_table(table, schema=schema)


def _has_column(
    conn: sa.Connection,
    table: str,
    column: str,
    schema: str | None,
) -> bool:
    return any(
        item["name"] == column
        for item in sa.inspect(conn).get_columns(table, schema=schema)
    )


def _has_index(
    conn: sa.Connection,
    table: str,
    index: str,
    schema: str | None,
) -> bool:
    return any(
        item["name"] == index
        for item in sa.inspect(conn).get_indexes(table, schema=schema)
    )


def _has_source_snapshot_foreign_key(
    conn: sa.Connection,
    table: str,
    schema: str | None,
) -> bool:
    return any(
        item["constrained_columns"] == ["source_snapshot_id"]
        and item["referred_table"] == "source_evidence_snapshots"
        for item in sa.inspect(conn).get_foreign_keys(table, schema=schema)
    )


def _source_snapshot_foreign_key_name(
    conn: sa.Connection,
    table: str,
    schema: str | None,
) -> str | None:
    for item in sa.inspect(conn).get_foreign_keys(table, schema=schema):
        if (
            item["constrained_columns"] == ["source_snapshot_id"]
            and item["referred_table"] == "source_evidence_snapshots"
        ):
            name = item.get("name")
            return str(name) if name is not None else None
    return None


def upgrade() -> None:
    schema = graph_schema_name()
    conn = op.get_bind()
    if not _has_table(conn, "source_evidence_snapshots", schema):
        op.create_table(
            "source_evidence_snapshots",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("research_space_id", sa.Uuid(), nullable=False),
            sa.Column("upstream_service", sa.String(64), nullable=False),
            sa.Column("upstream_research_space_id", sa.Uuid(), nullable=False),
            sa.Column("upstream_document_id", sa.Uuid(), nullable=False),
            sa.Column("attested_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("identity_fingerprint", sa.String(64), nullable=False),
            sa.Column("source_kind", sa.String(32), nullable=False),
            sa.Column("authoritative_identifier", sa.String(512), nullable=False),
            sa.Column("canonical_url", sa.Text(), nullable=False),
            sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("content_sha256", sa.String(64), nullable=False),
            sa.Column("version", sa.String(255), nullable=True),
            sa.Column("artifact_sha256", sa.String(64), nullable=True),
            sa.Column("canonical_text", sa.Text(), nullable=False),
            sa.Column(
                "source_identity_payload",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.ForeignKeyConstraint(
                ["research_space_id"],
                [_qualified_target(schema, "graph_spaces.id")],
                ondelete="RESTRICT",
                name="fk_source_evidence_snapshots_space",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "research_space_id",
                "identity_fingerprint",
                name="uq_source_evidence_snapshots_space_identity",
            ),
            schema=schema,
        )
    if not _has_index(
        conn,
        "source_evidence_snapshots",
        "idx_source_evidence_snapshots_space_authority",
        schema,
    ):
        op.create_index(
            "idx_source_evidence_snapshots_space_authority",
            "source_evidence_snapshots",
            ["research_space_id", "source_kind", "authoritative_identifier"],
            schema=schema,
        )
    if not _has_index(
        conn,
        "source_evidence_snapshots",
        "idx_source_evidence_snapshots_content_sha256",
        schema,
    ):
        op.create_index(
            "idx_source_evidence_snapshots_content_sha256",
            "source_evidence_snapshots",
            ["content_sha256"],
            schema=schema,
        )

    with op.batch_alter_table("claim_evidence", schema=schema) as batch_op:
        if not _has_column(conn, "claim_evidence", "source_snapshot_id", schema):
            batch_op.add_column(
                sa.Column("source_snapshot_id", sa.Uuid(), nullable=True),
            )
        if not _has_column(
            conn,
            "claim_evidence",
            "evidence_locator_payload",
            schema,
        ):
            batch_op.add_column(
                sa.Column(
                    "evidence_locator_payload",
                    postgresql.JSONB(astext_type=sa.Text()),
                    nullable=True,
                ),
            )
        if not _has_column(conn, "claim_evidence", "provenance_status", schema):
            batch_op.add_column(
                sa.Column(
                    "provenance_status",
                    sa.String(32),
                    nullable=False,
                    server_default="LEGACY_UNVERIFIED",
                ),
            )
        if not _has_column(
            conn,
            "claim_evidence",
            "provenance_reason_codes",
            schema,
        ):
            batch_op.add_column(
                sa.Column(
                    "provenance_reason_codes",
                    postgresql.JSONB(astext_type=sa.Text()),
                    nullable=False,
                    server_default='["legacy_evidence_without_typed_provenance"]',
                ),
            )
        if not _has_source_snapshot_foreign_key(conn, "claim_evidence", schema):
            batch_op.create_foreign_key(
                "fk_claim_evidence_source_snapshot",
                "source_evidence_snapshots",
                ["source_snapshot_id"],
                ["id"],
                referent_schema=schema,
                ondelete="RESTRICT",
            )
        if not _has_index(
            conn,
            "claim_evidence",
            "idx_claim_evidence_source_snapshot_id",
            schema,
        ):
            batch_op.create_index(
                "idx_claim_evidence_source_snapshot_id",
                ["source_snapshot_id"],
            )

    with op.batch_alter_table("relation_evidence", schema=schema) as batch_op:
        if not _has_column(conn, "relation_evidence", "source_snapshot_id", schema):
            batch_op.add_column(
                sa.Column("source_snapshot_id", sa.Uuid(), nullable=True),
            )
        if not _has_source_snapshot_foreign_key(conn, "relation_evidence", schema):
            batch_op.create_foreign_key(
                "fk_relation_evidence_source_snapshot",
                "source_evidence_snapshots",
                ["source_snapshot_id"],
                ["id"],
                referent_schema=schema,
                ondelete="RESTRICT",
            )
        if not _has_index(
            conn,
            "relation_evidence",
            "idx_relation_evidence_source_snapshot_id",
            schema,
        ):
            batch_op.create_index(
                "idx_relation_evidence_source_snapshot_id",
                ["source_snapshot_id"],
            )

    _create_immutability_guards(schema=schema)


def downgrade() -> None:
    schema = graph_schema_name()
    conn = op.get_bind()
    _drop_immutability_guards(schema=schema)
    with op.batch_alter_table("relation_evidence", schema=schema) as batch_op:
        if _has_index(
            conn,
            "relation_evidence",
            "idx_relation_evidence_source_snapshot_id",
            schema,
        ):
            batch_op.drop_index("idx_relation_evidence_source_snapshot_id")
        relation_foreign_key = _source_snapshot_foreign_key_name(
            conn,
            "relation_evidence",
            schema,
        )
        if relation_foreign_key is not None:
            batch_op.drop_constraint(relation_foreign_key, type_="foreignkey")
        if _has_column(conn, "relation_evidence", "source_snapshot_id", schema):
            batch_op.drop_column("source_snapshot_id")
    with op.batch_alter_table("claim_evidence", schema=schema) as batch_op:
        if _has_index(
            conn,
            "claim_evidence",
            "idx_claim_evidence_source_snapshot_id",
            schema,
        ):
            batch_op.drop_index("idx_claim_evidence_source_snapshot_id")
        claim_foreign_key = _source_snapshot_foreign_key_name(
            conn,
            "claim_evidence",
            schema,
        )
        if claim_foreign_key is not None:
            batch_op.drop_constraint(claim_foreign_key, type_="foreignkey")
        for column in (
            "provenance_reason_codes",
            "provenance_status",
            "evidence_locator_payload",
            "source_snapshot_id",
        ):
            if _has_column(conn, "claim_evidence", column, schema):
                batch_op.drop_column(column)
    if _has_index(
        conn,
        "source_evidence_snapshots",
        "idx_source_evidence_snapshots_content_sha256",
        schema,
    ):
        op.drop_index(
            "idx_source_evidence_snapshots_content_sha256",
            table_name="source_evidence_snapshots",
            schema=schema,
        )
    if _has_index(
        conn,
        "source_evidence_snapshots",
        "idx_source_evidence_snapshots_space_authority",
        schema,
    ):
        op.drop_index(
            "idx_source_evidence_snapshots_space_authority",
            table_name="source_evidence_snapshots",
            schema=schema,
        )
    if _has_table(conn, "source_evidence_snapshots", schema):
        op.drop_table("source_evidence_snapshots", schema=schema)


def _qualified_target(schema: str | None, target: str) -> str:
    if schema is None:
        return target
    return f"{schema}.{target}"


def _create_immutability_guards(*, schema: str | None) -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        function_name = _qualified_name(schema, _PG_FUNCTION)
        table_name = _qualified_name(schema, "source_evidence_snapshots")
        op.execute(
            f"""
            CREATE FUNCTION {function_name}() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'source evidence snapshots are immutable';
            END;
            $$ LANGUAGE plpgsql
            """,
        )
        for trigger_name, operation in (
            (_UPDATE_TRIGGER, "UPDATE"),
            (_DELETE_TRIGGER, "DELETE"),
        ):
            op.execute(
                f"CREATE TRIGGER {trigger_name} BEFORE {operation} ON {table_name} "
                f"FOR EACH ROW EXECUTE FUNCTION {function_name}()",
            )
        return
    if conn.dialect.name == "sqlite":
        for trigger_name, operation in (
            (_UPDATE_TRIGGER, "UPDATE"),
            (_DELETE_TRIGGER, "DELETE"),
        ):
            op.execute(
                f"CREATE TRIGGER {trigger_name} BEFORE {operation} "
                "ON source_evidence_snapshots BEGIN "
                "SELECT RAISE(ABORT, 'source evidence snapshots are immutable'); END",
            )


def _drop_immutability_guards(*, schema: str | None) -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        table_name = _qualified_name(schema, "source_evidence_snapshots")
        for trigger_name in (_UPDATE_TRIGGER, _DELETE_TRIGGER):
            op.execute(f"DROP TRIGGER IF EXISTS {trigger_name} ON {table_name}")
        op.execute(
            f"DROP FUNCTION IF EXISTS {_qualified_name(schema, _PG_FUNCTION)}()",
        )
        return
    if conn.dialect.name == "sqlite":
        for trigger_name in (_UPDATE_TRIGGER, _DELETE_TRIGGER):
            op.execute(f"DROP TRIGGER IF EXISTS {trigger_name}")


def _qualified_name(schema: str | None, name: str) -> str:
    if schema is None:
        return name
    return f'"{schema}"."{name}"'
