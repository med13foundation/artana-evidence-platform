"""Smoke tests for the artana-evidence-api Alembic history."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CURRENT_HEAD_REVISION = "017_add_review_timestamps"
HARNESS_ALEMBIC_VERSION_TABLE = "alembic_version_artana_evidence_api"
_ALEMBIC_SUBPROCESS_TEMPLATE = """
import os
import sys

repo_root = os.environ["ARTANA_REPOSITORY_ROOT"]
normalized_repo_root = os.path.normcase(os.path.abspath(repo_root))

def _normalized(path: str) -> str:
    resolved = path if path else os.getcwd()
    return os.path.normcase(os.path.abspath(resolved))

sys.path = [
    path for path in sys.path
    if _normalized(path) != normalized_repo_root
]

from alembic.config import main

main(argv=["-c", "services/artana_evidence_api/alembic.ini", {command!r}, {revision!r}])
""".strip()


def _build_alembic_subprocess_command(*, command: str, revision: str) -> list[str]:
    script = _ALEMBIC_SUBPROCESS_TEMPLATE.format(
        command=command,
        revision=revision,
    )
    return [sys.executable, "-c", script]


def _run_alembic(*, database_url: str, command: str, revision: str) -> None:
    env = dict(os.environ)
    env["ALEMBIC_DATABASE_URL"] = database_url
    env["ARTANA_EVIDENCE_API_DATABASE_URL"] = database_url
    env["ARTANA_REPOSITORY_ROOT"] = str(REPOSITORY_ROOT)
    if database_url.startswith("sqlite"):
        env["ARTANA_EVIDENCE_API_DB_SCHEMA"] = "public"
        env["ALEMBIC_ARTANA_EVIDENCE_API_DB_SCHEMA"] = "public"
    subprocess.run(
        _build_alembic_subprocess_command(command=command, revision=revision),
        check=True,
        cwd=REPOSITORY_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def test_upgrade_head_creates_current_harness_schema(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'harness_head.db'}"
    _run_alembic(database_url=database_url, command="upgrade", revision="head")

    engine = create_engine(database_url, future=True)
    try:
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
        assert {
            "harness_runs",
            "harness_run_intents",
            "harness_run_approvals",
            "harness_proposals",
            "harness_schedules",
            "harness_research_state",
            "harness_graph_snapshots",
            "harness_chat_sessions",
            "harness_chat_messages",
            "harness_documents",
            "reviews",
        }.issubset(table_names)

        with engine.connect() as connection:
            versions = (
                connection.execute(
                    text(
                        f"SELECT version_num FROM {HARNESS_ALEMBIC_VERSION_TABLE}",
                    ),
                )
                .scalars()
                .all()
            )
            review_columns = {
                column["name"] for column in inspector.get_columns("reviews")
            }
    finally:
        engine.dispose()

    assert versions == [CURRENT_HEAD_REVISION]
    assert {"created_at", "updated_at", "last_updated"}.issubset(review_columns)


def test_upgrade_head_and_downgrade_base_round_trip(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'harness_round_trip.db'}"
    _run_alembic(database_url=database_url, command="upgrade", revision="head")
    _run_alembic(database_url=database_url, command="downgrade", revision="base")

    engine = create_engine(database_url, future=True)
    try:
        table_names = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert "harness_runs" not in table_names
    assert "harness_proposals" not in table_names
    assert "harness_chat_sessions" not in table_names
    assert "reviews" not in table_names
