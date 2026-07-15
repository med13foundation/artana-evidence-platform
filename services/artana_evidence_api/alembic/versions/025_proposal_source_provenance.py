"""Persist immutable proposal-time source provenance."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_api.db_schema import harness_schema_name

revision = "025_proposal_source_provenance"
down_revision = "024_unique_active_proposal_fingerprints"
branch_labels = None
depends_on = None

_STATUS_INDEX = "idx_harness_proposals_source_provenance_status"
_IMMUTABILITY_TRIGGER = "trg_harness_proposals_source_provenance_immutable"
_PG_FUNCTION = "reject_harness_proposal_source_provenance_mutation"


def upgrade() -> None:
    harness_schema = harness_schema_name()
    op.add_column(
        "harness_proposals",
        sa.Column("source_provenance_payload", sa.JSON(), nullable=True),
        schema=harness_schema,
    )
    op.add_column(
        "harness_proposals",
        sa.Column(
            "source_provenance_status",
            sa.String(length=32),
            nullable=False,
            server_default="unverified",
        ),
        schema=harness_schema,
    )
    op.create_index(
        _STATUS_INDEX,
        "harness_proposals",
        ["source_provenance_status"],
        unique=False,
        schema=harness_schema,
    )
    _create_immutability_guard(schema=harness_schema)


def downgrade() -> None:
    harness_schema = harness_schema_name()
    _drop_immutability_guard(schema=harness_schema)
    op.drop_index(
        _STATUS_INDEX,
        table_name="harness_proposals",
        schema=harness_schema,
    )
    op.drop_column(
        "harness_proposals",
        "source_provenance_status",
        schema=harness_schema,
    )
    op.drop_column(
        "harness_proposals",
        "source_provenance_payload",
        schema=harness_schema,
    )


def _create_immutability_guard(*, schema: str | None) -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        function_name = _qualified_name(schema, _PG_FUNCTION)
        table_name = _qualified_name(schema, "harness_proposals")
        op.execute(
            f"""
            CREATE FUNCTION {function_name}() RETURNS trigger AS $$
            BEGIN
                IF to_jsonb(NEW.source_provenance_payload) IS DISTINCT FROM
                   to_jsonb(OLD.source_provenance_payload)
                   OR NEW.source_provenance_status IS DISTINCT FROM
                      OLD.source_provenance_status THEN
                    RAISE EXCEPTION 'proposal source provenance is immutable';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """,
        )
        op.execute(
            f"CREATE TRIGGER {_IMMUTABILITY_TRIGGER} BEFORE UPDATE OF "
            "source_provenance_payload, source_provenance_status "
            f"ON {table_name} FOR EACH ROW EXECUTE FUNCTION {function_name}()",
        )
        return
    if conn.dialect.name == "sqlite":
        op.execute(
            f"CREATE TRIGGER {_IMMUTABILITY_TRIGGER} BEFORE UPDATE OF "
            "source_provenance_payload, source_provenance_status "
            "ON harness_proposals FOR EACH ROW WHEN "
            "NEW.source_provenance_payload IS NOT OLD.source_provenance_payload "
            "OR NEW.source_provenance_status IS NOT OLD.source_provenance_status "
            "BEGIN SELECT RAISE(ABORT, "
            "'proposal source provenance is immutable'); END",
        )


def _drop_immutability_guard(*, schema: str | None) -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        table_name = _qualified_name(schema, "harness_proposals")
        op.execute(
            f"DROP TRIGGER IF EXISTS {_IMMUTABILITY_TRIGGER} ON {table_name}",
        )
        op.execute(
            f"DROP FUNCTION IF EXISTS {_qualified_name(schema, _PG_FUNCTION)}()",
        )
        return
    if conn.dialect.name == "sqlite":
        op.execute(f"DROP TRIGGER IF EXISTS {_IMMUTABILITY_TRIGGER}")


def _qualified_name(schema: str | None, name: str) -> str:
    if schema is None:
        return name
    return f'"{schema}"."{name}"'
