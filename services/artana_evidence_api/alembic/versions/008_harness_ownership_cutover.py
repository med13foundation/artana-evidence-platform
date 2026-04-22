"""Copy legacy harness data into the standalone harness schema and drop old tables."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_api.db_schema import harness_schema_name

revision = "008_harness_ownership_cutover"
down_revision = "007_harness_artana_cleanup"
branch_labels = None
depends_on = None

_CURRENT_HARNESS_TABLES: tuple[str, ...] = (
    "harness_runs",
    "harness_run_intents",
    "harness_run_approvals",
    "harness_proposals",
    "harness_schedules",
    "harness_research_state",
    "harness_graph_snapshots",
    "harness_chat_sessions",
    "harness_chat_messages",
)

_LEGACY_ONLY_TABLES: tuple[str, ...] = (
    "harness_run_artifacts",
    "harness_run_workspaces",
    "harness_run_progress",
    "harness_run_events",
)

_DROP_ORDER: tuple[str, ...] = (
    "harness_chat_messages",
    "harness_chat_sessions",
    "harness_graph_snapshots",
    "harness_research_state",
    "harness_schedules",
    "harness_proposals",
    "harness_run_approvals",
    "harness_run_intents",
    "harness_run_artifacts",
    "harness_run_workspaces",
    "harness_run_progress",
    "harness_run_events",
    "harness_runs",
)


def _schema_name(raw_schema: str | None) -> str | None:
    if raw_schema in (None, "", "public"):
        return None
    return raw_schema


def _qualified_table(schema: str | None, table_name: str) -> str:
    if schema is None:
        return f'"{table_name}"'
    return f'"{schema}"."{table_name}"'


def _column_names(
    inspector: sa.Inspector,
    table_name: str,
    *,
    schema: str | None,
) -> list[str]:
    return [
        column["name"] for column in inspector.get_columns(table_name, schema=schema)
    ]


def _resolve_legacy_source_schema(inspector: sa.Inspector) -> str | None:
    target_schema = harness_schema_name()
    for candidate in ("graph_runtime", "public"):
        candidate_schema = _schema_name(candidate)
        if candidate_schema == target_schema:
            continue
        if any(
            inspector.has_table(table_name, schema=candidate_schema)
            for table_name in (*_CURRENT_HARNESS_TABLES, *_LEGACY_ONLY_TABLES)
        ):
            return candidate_schema
    return None


def _copy_table(
    inspector: sa.Inspector,
    table_name: str,
    *,
    source_schema: str | None,
    target_schema: str | None,
) -> None:
    if not inspector.has_table(table_name, schema=source_schema):
        return
    if not inspector.has_table(table_name, schema=target_schema):
        return

    source_columns = set(_column_names(inspector, table_name, schema=source_schema))
    target_columns = [
        column_name
        for column_name in _column_names(inspector, table_name, schema=target_schema)
        if column_name in source_columns
    ]
    if not target_columns:
        return

    quoted_columns = ", ".join(f'"{column_name}"' for column_name in target_columns)
    op.execute(
        sa.text(
            f"""
            INSERT INTO {_qualified_table(target_schema, table_name)} ({quoted_columns})
            SELECT {quoted_columns}
            FROM {_qualified_table(source_schema, table_name)}
            ON CONFLICT DO NOTHING
            """,
        ),
    )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    inspector = sa.inspect(bind)
    source_schema = _resolve_legacy_source_schema(inspector)
    if source_schema is None:
        return

    target_schema = harness_schema_name()
    for table_name in _CURRENT_HARNESS_TABLES:
        _copy_table(
            inspector,
            table_name,
            source_schema=source_schema,
            target_schema=target_schema,
        )

    for table_name in _DROP_ORDER:
        if not inspector.has_table(table_name, schema=source_schema):
            continue
        op.execute(
            sa.text(
                f"DROP TABLE IF EXISTS {_qualified_table(source_schema, table_name)} CASCADE",
            ),
        )
        inspector = sa.inspect(bind)


def downgrade() -> None:
    return None
