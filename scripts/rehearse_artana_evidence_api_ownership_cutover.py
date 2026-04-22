"""Rehearse the artana-evidence-api ownership cutover on a PostgreSQL database.

This script simulates the legacy state where harness-owned tables still live in
the graph schema, then runs the standalone harness Alembic chain into a target
schema and verifies that data is copied across and the legacy tables are
dropped.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import sqlalchemy as sa

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LEGACY_SETUP_SCHEMA = "graph_runtime"
LEGACY_SOURCE_SCHEMA_CANDIDATES: tuple[str | None, ...] = ("graph_runtime", None)
DEFAULT_TARGET_SCHEMA = "artana_evidence_api_rehearsal"
HARNESS_HEAD_REVISION = "head"
HARNESS_VERSION_TABLE = "alembic_version_artana_evidence_api"
CURRENT_HARNESS_TABLES: tuple[str, ...] = (
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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Rehearse the graph-harness ownership cutover by moving legacy "
            "graph-owned harness tables into a standalone harness schema."
        ),
    )
    parser.add_argument(
        "--database-url",
        default=(
            os.getenv("ARTANA_EVIDENCE_API_DATABASE_URL")
            or os.getenv("ALEMBIC_DATABASE_URL")
            or os.getenv("DATABASE_URL")
        ),
        help="PostgreSQL database URL to use for the rehearsal.",
    )
    parser.add_argument(
        "--target-schema",
        default=DEFAULT_TARGET_SCHEMA,
        help="Target standalone harness schema used for the rehearsal.",
    )
    parser.add_argument(
        "--keep-schemas",
        action="store_true",
        help="Keep the rehearsal schemas after success for inspection.",
    )
    parser.add_argument(
        "--force-clean",
        action="store_true",
        help=(
            "Drop any pre-existing rehearsal harness tables in the legacy "
            "candidate schemas before running. Use only with a scratch database."
        ),
    )
    return parser.parse_args()


def _subprocess_env(*, database_url: str, schema: str) -> dict[str, str]:
    env = dict(os.environ)
    env["ALEMBIC_DATABASE_URL"] = database_url
    env["ARTANA_EVIDENCE_API_DATABASE_URL"] = database_url
    env["ARTANA_EVIDENCE_API_DB_SCHEMA"] = schema
    env["ALEMBIC_ARTANA_EVIDENCE_API_DB_SCHEMA"] = schema
    env["ARTANA_REPOSITORY_ROOT"] = str(REPOSITORY_ROOT)

    pythonpath_parts = [
        str(REPOSITORY_ROOT / "services"),
    ]
    existing_pythonpath = env.get("PYTHONPATH", "").strip()
    if existing_pythonpath != "":
        pythonpath_parts.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    return env


def _run_alembic_upgrade(*, database_url: str, schema: str, revision: str) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "services/artana_evidence_api/alembic.ini",
            "upgrade",
            revision,
        ],
        cwd=REPOSITORY_ROOT,
        env=_subprocess_env(database_url=database_url, schema=schema),
        check=True,
    )


def _create_legacy_tables(*, database_url: str, schema: str) -> None:
    env = _subprocess_env(database_url=database_url, schema="public")
    subprocess.run(
        [
            sys.executable,
            "-c",
            """
import os
import sqlalchemy as sa

from artana_evidence_api.models import Base

database_url = os.environ["ARTANA_EVIDENCE_API_DATABASE_URL"]
schema = os.environ["REHEARSAL_LEGACY_SCHEMA"]
engine = sa.create_engine(database_url, future=True)
with engine.begin() as connection:
    if schema != "public":
        connection.execute(
            sa.text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'),
        )
translated_engine = engine.execution_options(
    schema_translate_map={None: None if schema == "public" else schema},
)
Base.metadata.create_all(translated_engine)
engine.dispose()
""".strip(),
        ],
        cwd=REPOSITORY_ROOT,
        env={**env, "REHEARSAL_LEGACY_SCHEMA": schema},
        check=True,
    )


def _quoted_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _qualified_table(schema: str | None, table_name: str) -> str:
    if schema is None:
        return _quoted_identifier(table_name)
    return f"{_quoted_identifier(schema)}.{_quoted_identifier(table_name)}"


def _seed_legacy_tables(
    connection: sa.Connection,
    *,
    source_schema: str | None,
) -> dict[str, str]:
    metadata = sa.MetaData()
    metadata.reflect(
        connection,
        schema=source_schema,
        only=list(CURRENT_HARNESS_TABLES),
    )
    schema_key_prefix = "" if source_schema is None else f"{source_schema}."

    run_id = str(uuid4())
    space_id = str(uuid4())
    approval_id = str(uuid4())
    proposal_id = str(uuid4())
    schedule_id = str(uuid4())
    snapshot_id = str(uuid4())
    chat_session_id = str(uuid4())
    chat_message_id = str(uuid4())
    actor_id = str(uuid4())

    runs_table = metadata.tables[f"{schema_key_prefix}harness_runs"]
    connection.execute(
        runs_table.insert().values(
            id=run_id,
            space_id=space_id,
            harness_id="rehearsal-harness",
            title="Ownership Cutover Rehearsal",
            status="completed",
            input_payload={"mode": "rehearsal"},
            graph_service_status="healthy",
            graph_service_version="rehearsal",
        ),
    )

    intents_table = metadata.tables[f"{schema_key_prefix}harness_run_intents"]
    connection.execute(
        intents_table.insert().values(
            run_id=run_id,
            space_id=space_id,
            summary="Verify legacy harness cutover",
            proposed_actions_payload=[{"kind": "verify"}],
            metadata_payload={"source": "rehearsal"},
        ),
    )

    approvals_table = metadata.tables[f"{schema_key_prefix}harness_run_approvals"]
    connection.execute(
        approvals_table.insert().values(
            id=approval_id,
            run_id=run_id,
            space_id=space_id,
            approval_key="rehearsal-approval",
            title="Approve rehearsal cutover",
            risk_level="low",
            target_type="schema",
            target_id=None,
            status="approved",
            decision_reason="rehearsal",
            metadata_payload={"source": "rehearsal"},
        ),
    )

    proposals_table = metadata.tables[f"{schema_key_prefix}harness_proposals"]
    connection.execute(
        proposals_table.insert().values(
            id=proposal_id,
            space_id=space_id,
            run_id=run_id,
            proposal_type="graph_update",
            source_kind="rehearsal",
            source_key="cutover",
            title="Cutover rehearsal proposal",
            summary="Verify proposal migration",
            status="staged",
            confidence=0.9,
            ranking_score=0.9,
            reasoning_path={"steps": 1},
            evidence_bundle_payload=[{"kind": "rehearsal"}],
            payload={"proposal": "rehearsal"},
            metadata_payload={"source": "rehearsal"},
            decision_reason=None,
            decided_at=None,
        ),
    )

    schedules_table = metadata.tables[f"{schema_key_prefix}harness_schedules"]
    connection.execute(
        schedules_table.insert().values(
            id=schedule_id,
            space_id=space_id,
            harness_id="rehearsal-harness",
            title="Rehearsal schedule",
            cadence="manual",
            status="active",
            created_by=actor_id,
            configuration_payload={"cadence": "manual"},
            metadata_payload={"source": "rehearsal"},
            last_run_id=run_id,
            last_run_at=None,
        ),
    )

    snapshots_table = metadata.tables[f"{schema_key_prefix}harness_graph_snapshots"]
    connection.execute(
        snapshots_table.insert().values(
            id=snapshot_id,
            space_id=space_id,
            source_run_id=run_id,
            claim_ids_payload=[],
            relation_ids_payload=[],
            graph_document_hash="rehearsal-hash",
            summary_payload={"nodes": 0},
            metadata_payload={"source": "rehearsal"},
        ),
    )

    research_state_table = metadata.tables[f"{schema_key_prefix}harness_research_state"]
    connection.execute(
        research_state_table.insert().values(
            space_id=space_id,
            objective="Verify cutover",
            current_hypotheses_payload=[],
            explored_questions_payload=[],
            pending_questions_payload=[],
            last_graph_snapshot_id=snapshot_id,
            last_learning_cycle_at=None,
            active_schedules_payload=[],
            confidence_model_payload={"mode": "rehearsal"},
            budget_policy_payload={"mode": "rehearsal"},
            metadata_payload={"source": "rehearsal"},
        ),
    )

    sessions_table = metadata.tables[f"{schema_key_prefix}harness_chat_sessions"]
    connection.execute(
        sessions_table.insert().values(
            id=chat_session_id,
            space_id=space_id,
            title="Rehearsal chat",
            created_by=actor_id,
            last_run_id=run_id,
            status="active",
        ),
    )

    messages_table = metadata.tables[f"{schema_key_prefix}harness_chat_messages"]
    connection.execute(
        messages_table.insert().values(
            id=chat_message_id,
            session_id=chat_session_id,
            space_id=space_id,
            role="user",
            content="Verify cutover migration",
            run_id=run_id,
            metadata_payload={"source": "rehearsal"},
        ),
    )

    return {
        "run_id": run_id,
        "space_id": space_id,
        "approval_id": approval_id,
        "proposal_id": proposal_id,
        "schedule_id": schedule_id,
        "snapshot_id": snapshot_id,
        "chat_session_id": chat_session_id,
        "chat_message_id": chat_message_id,
    }


def _verify_cutover(
    connection: sa.Connection,
    *,
    source_schema: str | None,
    target_schema: str,
    identifiers: dict[str, str],
) -> None:
    inspector = sa.inspect(connection)
    for table_name in CURRENT_HARNESS_TABLES:
        if not inspector.has_table(table_name, schema=target_schema):
            raise RuntimeError(
                f"Expected target table {target_schema}.{table_name} to exist",
            )
        if inspector.has_table(table_name, schema=source_schema):
            raise RuntimeError(
                "Expected legacy table "
                f"{source_schema or 'public'}.{table_name} to be dropped",
            )

    runs_table = sa.Table(
        "harness_runs",
        sa.MetaData(),
        autoload_with=connection,
        schema=target_schema,
    )
    proposals_table = sa.Table(
        "harness_proposals",
        sa.MetaData(),
        autoload_with=connection,
        schema=target_schema,
    )
    messages_table = sa.Table(
        "harness_chat_messages",
        sa.MetaData(),
        autoload_with=connection,
        schema=target_schema,
    )

    run_count = connection.execute(
        sa.select(sa.func.count())
        .select_from(runs_table)
        .where(
            runs_table.c.id == identifiers["run_id"],
        ),
    ).scalar_one()
    proposal_count = connection.execute(
        sa.select(sa.func.count())
        .select_from(proposals_table)
        .where(
            proposals_table.c.id == identifiers["proposal_id"],
        ),
    ).scalar_one()
    message_count = connection.execute(
        sa.select(sa.func.count())
        .select_from(messages_table)
        .where(
            messages_table.c.id == identifiers["chat_message_id"],
        ),
    ).scalar_one()

    if run_count != 1:
        raise RuntimeError("Expected the harness run row to be copied")
    if proposal_count != 1:
        raise RuntimeError("Expected the proposal row to be copied")
    if message_count != 1:
        raise RuntimeError("Expected the chat message row to be copied")


def _drop_harness_tables(connection: sa.Connection, *, schema: str | None) -> None:
    inspector = sa.inspect(connection)
    drop_order = tuple(reversed(CURRENT_HARNESS_TABLES)) + (HARNESS_VERSION_TABLE,)
    for table_name in drop_order:
        if not inspector.has_table(table_name, schema=schema):
            continue
        qualified_table = _qualified_table(schema, table_name)
        connection.execute(sa.text(f"DROP TABLE IF EXISTS {qualified_table} CASCADE"))
        inspector = sa.inspect(connection)


def _drop_schema_if_non_public(
    connection: sa.Connection,
    schema_name: str | None,
) -> None:
    if schema_name in (None, "public"):
        return
    connection.execute(
        sa.text(f"DROP SCHEMA IF EXISTS {_quoted_identifier(schema_name)} CASCADE"),
    )


def _detect_legacy_source_schema(connection: sa.Connection) -> str | None:
    inspector = sa.inspect(connection)
    for schema in LEGACY_SOURCE_SCHEMA_CANDIDATES:
        if inspector.has_table("harness_runs", schema=schema):
            return schema
    return None


def _existing_harness_tables(
    connection: sa.Connection,
    *,
    target_schema: str,
) -> list[str]:
    inspector = sa.inspect(connection)
    existing: list[str] = []
    for schema in (*LEGACY_SOURCE_SCHEMA_CANDIDATES, target_schema):
        existing.extend(
            [
                f"{schema or 'public'}.{table_name}"
                for table_name in (*CURRENT_HARNESS_TABLES, HARNESS_VERSION_TABLE)
                if inspector.has_table(table_name, schema=schema)
            ],
        )
    return existing


def main() -> int:
    args = _parse_args()
    database_url = args.database_url
    if database_url is None:
        raise SystemExit(
            "A PostgreSQL database URL is required via --database-url, "
            "ARTANA_EVIDENCE_API_DATABASE_URL, ALEMBIC_DATABASE_URL, or DATABASE_URL.",
        )
    if not database_url.startswith("postgresql"):
        raise SystemExit("This rehearsal requires a PostgreSQL database URL.")

    target_schema = args.target_schema.strip()
    if target_schema in {"", LEGACY_SETUP_SCHEMA}:
        raise SystemExit(
            "Choose a non-empty target schema different from graph_runtime.",
        )

    engine = sa.create_engine(database_url, future=True)
    identifiers: dict[str, str]
    legacy_source_schema: str | None = None
    try:
        with engine.begin() as connection:
            existing_tables = _existing_harness_tables(
                connection,
                target_schema=target_schema,
            )
            if existing_tables and not args.force_clean:
                raise SystemExit(
                    "Existing harness tables were found in the rehearsal database: "
                    + ", ".join(existing_tables)
                    + ". Use a scratch database or rerun with --force-clean.",
                )
            if args.force_clean:
                for schema in LEGACY_SOURCE_SCHEMA_CANDIDATES:
                    _drop_harness_tables(connection, schema=schema)
                    _drop_schema_if_non_public(connection, schema)
                _drop_harness_tables(connection, schema=target_schema)
                _drop_schema_if_non_public(connection, target_schema)

        _create_legacy_tables(
            database_url=database_url,
            schema=LEGACY_SETUP_SCHEMA,
        )

        with engine.begin() as connection:
            legacy_source_schema = _detect_legacy_source_schema(connection)
            if legacy_source_schema is None:
                raise SystemExit(
                    "Legacy setup completed but no harness source schema was detected.",
                )
            identifiers = _seed_legacy_tables(
                connection,
                source_schema=legacy_source_schema,
            )

        _run_alembic_upgrade(
            database_url=database_url,
            schema=target_schema,
            revision=HARNESS_HEAD_REVISION,
        )

        with engine.begin() as connection:
            _verify_cutover(
                connection,
                source_schema=legacy_source_schema,
                target_schema=target_schema,
                identifiers=identifiers,
            )

        print(
            "graph_harness_cutover_rehearsal: ok",
            f"source_schema={legacy_source_schema or 'public'}",
            f"target_schema={target_schema}",
        )
        return 0
    finally:
        if not args.keep_schemas:
            with engine.begin() as connection:
                for schema in LEGACY_SOURCE_SCHEMA_CANDIDATES:
                    _drop_harness_tables(connection, schema=schema)
                    _drop_schema_if_non_public(connection, schema)
                _drop_harness_tables(connection, schema=target_schema)
                _drop_schema_if_non_public(connection, target_schema)
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
