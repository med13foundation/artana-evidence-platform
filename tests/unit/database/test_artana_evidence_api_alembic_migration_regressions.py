"""Smoke tests for the artana-evidence-api Alembic history."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CURRENT_HEAD_REVISION = "025_proposal_source_provenance"
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


def _run_alembic_process(
    *,
    database_url: str,
    command: str,
    revision: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["ALEMBIC_DATABASE_URL"] = database_url
    env["ARTANA_EVIDENCE_API_DATABASE_URL"] = database_url
    env["ARTANA_REPOSITORY_ROOT"] = str(REPOSITORY_ROOT)
    if database_url.startswith("sqlite"):
        env["ARTANA_EVIDENCE_API_DB_SCHEMA"] = "public"
        env["ALEMBIC_ARTANA_EVIDENCE_API_DB_SCHEMA"] = "public"
    return subprocess.run(
        _build_alembic_subprocess_command(command=command, revision=revision),
        check=check,
        cwd=REPOSITORY_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def _run_alembic(*, database_url: str, command: str, revision: str) -> None:
    _run_alembic_process(
        database_url=database_url,
        command=command,
        revision=revision,
    )


def _seed_harness_run_and_duplicate_proposals(
    *,
    database_url: str,
    space_id: str,
    run_id: str,
    claim_fingerprint: str,
    proposals: tuple[dict[str, str], ...],
) -> None:
    engine = create_engine(database_url, future=True)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO harness_runs (
                        id, space_id, harness_id, title, status, input_payload,
                        graph_service_status, graph_service_version,
                        created_at, updated_at
                    )
                    VALUES (
                        :run_id, :space_id, 'harness', 'Run', 'completed', '{}',
                        'available', 'test', '2026-07-03 10:00:00',
                        '2026-07-03 10:00:00'
                    )
                    """,
                ),
                {"run_id": run_id, "space_id": space_id},
            )
            for proposal in proposals:
                connection.execute(
                    text(
                        """
                        INSERT INTO harness_proposals (
                            id, space_id, run_id, proposal_type, source_kind,
                            source_key, title, summary, status, confidence,
                            ranking_score, reasoning_path, evidence_bundle_payload,
                            payload, metadata_payload, decision_reason, decided_at,
                            created_at, updated_at, claim_fingerprint, evidence_grade
                        )
                        VALUES (
                            :id, :space_id, :run_id, 'candidate_claim',
                            'document_extraction', :source_key, :title, :title,
                            :status, 0.8, 0.8, '{}', '[]', '{}', '{}',
                            NULL, NULL, :created_at, :updated_at,
                            :claim_fingerprint, NULL
                        )
                        """,
                    ),
                    {
                        **proposal,
                        "space_id": space_id,
                        "run_id": run_id,
                        "claim_fingerprint": claim_fingerprint,
                    },
                )
    finally:
        engine.dispose()


def _proposal_rows(
    *,
    database_url: str,
    claim_fingerprint: str,
) -> list[dict[str, str | None]]:
    engine = create_engine(database_url, future=True)
    try:
        with engine.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    text(
                        """
                        SELECT id, status, decision_reason
                        FROM harness_proposals
                        WHERE claim_fingerprint = :claim_fingerprint
                        ORDER BY created_at
                        """,
                    ),
                    {"claim_fingerprint": claim_fingerprint},
                )
                .mappings()
                .all()
            ]
    finally:
        engine.dispose()


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


def test_024_deduplicates_historical_active_proposal_fingerprints(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'harness_024_duplicates.db'}"
    _run_alembic(
        database_url=database_url,
        command="upgrade",
        revision="023_harness_study_outcomes",
    )

    space_id = str(uuid4())
    run_id = str(uuid4())
    older_id = str(uuid4())
    newer_id = str(uuid4())
    claim_fingerprint = "a" * 32

    engine = create_engine(database_url, future=True)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO harness_runs (
                        id, space_id, harness_id, title, status, input_payload,
                        graph_service_status, graph_service_version,
                        created_at, updated_at
                    )
                    VALUES (
                        :run_id, :space_id, 'harness', 'Run', 'completed', '{}',
                        'available', 'test', '2026-07-03 10:00:00',
                        '2026-07-03 10:00:00'
                    )
                    """,
                ),
                {"run_id": run_id, "space_id": space_id},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO harness_proposals (
                        id, space_id, run_id, proposal_type, source_kind,
                        source_key, title, summary, status, confidence,
                        ranking_score, reasoning_path, evidence_bundle_payload,
                        payload, metadata_payload, decision_reason, decided_at,
                        created_at, updated_at, claim_fingerprint, evidence_grade
                    )
                    VALUES
                    (
                        :older_id, :space_id, :run_id, 'candidate_claim',
                        'document_extraction', 'older', 'Older', 'Older',
                        'pending_review', 0.8, 0.8, '{}', '[]', '{}', '{}',
                        NULL, NULL, '2026-07-03 10:00:00',
                        '2026-07-03 10:00:00', :claim_fingerprint, NULL
                    ),
                    (
                        :newer_id, :space_id, :run_id, 'candidate_claim',
                        'document_extraction', 'newer', 'Newer', 'Newer',
                        'promoted', 0.9, 0.9, '{}', '[]', '{}', '{}',
                        NULL, NULL, '2026-07-03 11:00:00',
                        '2026-07-03 11:00:00', :claim_fingerprint, NULL
                    )
                    """,
                ),
                {
                    "older_id": older_id,
                    "newer_id": newer_id,
                    "space_id": space_id,
                    "run_id": run_id,
                    "claim_fingerprint": claim_fingerprint,
                },
            )
    finally:
        engine.dispose()

    _run_alembic(
        database_url=database_url,
        command="upgrade",
        revision="024_unique_active_proposal_fingerprints",
    )

    engine = create_engine(database_url, future=True)
    try:
        with engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        """
                        SELECT id, status, decision_reason
                        FROM harness_proposals
                        WHERE claim_fingerprint = :claim_fingerprint
                        ORDER BY created_at
                        """,
                    ),
                    {"claim_fingerprint": claim_fingerprint},
                )
                .mappings()
                .all()
            )
    finally:
        engine.dispose()

    assert [row["id"] for row in rows] == [older_id, newer_id]
    assert rows[0]["status"] == "rejected"
    assert "duplicate active proposal" in rows[0]["decision_reason"]
    assert rows[1]["status"] == "promoted"


def test_024_keeps_older_promoted_proposal_over_newer_pending_duplicate(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'harness_024_promoted_wins.db'}"
    _run_alembic(
        database_url=database_url,
        command="upgrade",
        revision="023_harness_study_outcomes",
    )

    space_id = str(uuid4())
    run_id = str(uuid4())
    promoted_id = str(uuid4())
    pending_id = str(uuid4())
    claim_fingerprint = "b" * 32
    _seed_harness_run_and_duplicate_proposals(
        database_url=database_url,
        space_id=space_id,
        run_id=run_id,
        claim_fingerprint=claim_fingerprint,
        proposals=(
            {
                "id": promoted_id,
                "source_key": "promoted",
                "title": "Promoted",
                "status": "promoted",
                "created_at": "2026-07-03 10:00:00",
                "updated_at": "2026-07-03 10:00:00",
            },
            {
                "id": pending_id,
                "source_key": "pending",
                "title": "Pending",
                "status": "pending_review",
                "created_at": "2026-07-03 11:00:00",
                "updated_at": "2026-07-03 11:00:00",
            },
        ),
    )

    _run_alembic(
        database_url=database_url,
        command="upgrade",
        revision="024_unique_active_proposal_fingerprints",
    )

    rows = _proposal_rows(
        database_url=database_url,
        claim_fingerprint=claim_fingerprint,
    )

    assert [row["id"] for row in rows] == [promoted_id, pending_id]
    assert rows[0]["status"] == "promoted"
    assert rows[1]["status"] == "rejected"
    assert "duplicate active proposal" in str(rows[1]["decision_reason"])


def test_024_aborts_when_multiple_promoted_duplicates_exist(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'harness_024_two_promoted.db'}"
    _run_alembic(
        database_url=database_url,
        command="upgrade",
        revision="023_harness_study_outcomes",
    )

    space_id = str(uuid4())
    run_id = str(uuid4())
    claim_fingerprint = "c" * 32
    _seed_harness_run_and_duplicate_proposals(
        database_url=database_url,
        space_id=space_id,
        run_id=run_id,
        claim_fingerprint=claim_fingerprint,
        proposals=(
            {
                "id": str(uuid4()),
                "source_key": "promoted-older",
                "title": "Promoted Older",
                "status": "promoted",
                "created_at": "2026-07-03 10:00:00",
                "updated_at": "2026-07-03 10:00:00",
            },
            {
                "id": str(uuid4()),
                "source_key": "promoted-newer",
                "title": "Promoted Newer",
                "status": "promoted",
                "created_at": "2026-07-03 11:00:00",
                "updated_at": "2026-07-03 11:00:00",
            },
        ),
    )

    result = _run_alembic_process(
        database_url=database_url,
        command="upgrade",
        revision="024_unique_active_proposal_fingerprints",
        check=False,
    )

    assert result.returncode != 0
    assert "multiple promoted proposals" in result.stderr


def test_025_marks_legacy_proposals_unverified_without_inventing_provenance(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'harness_025_provenance.db'}"
    _run_alembic(
        database_url=database_url,
        command="upgrade",
        revision="024_unique_active_proposal_fingerprints",
    )
    space_id = str(uuid4())
    run_id = str(uuid4())
    proposal_id = str(uuid4())
    _seed_harness_run_and_duplicate_proposals(
        database_url=database_url,
        space_id=space_id,
        run_id=run_id,
        claim_fingerprint="d" * 32,
        proposals=(
            {
                "id": proposal_id,
                "source_key": "legacy",
                "title": "Legacy proposal",
                "status": "pending_review",
                "created_at": "2026-07-03 10:00:00",
                "updated_at": "2026-07-03 10:00:00",
            },
        ),
    )

    _run_alembic(
        database_url=database_url,
        command="upgrade",
        revision="025_proposal_source_provenance",
    )

    engine = create_engine(database_url, future=True)
    try:
        columns = {
            column["name"]
            for column in inspect(engine).get_columns("harness_proposals")
        }
        with engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        """
                    SELECT source_provenance_status, source_provenance_payload
                    FROM harness_proposals
                    WHERE id = :proposal_id
                    """,
                    ),
                    {"proposal_id": proposal_id},
                )
                .mappings()
                .one()
            )
    finally:
        engine.dispose()

    assert "source_provenance_status" in columns
    assert "source_provenance_payload" in columns
    assert row["source_provenance_status"] == "unverified"
    assert row["source_provenance_payload"] is None


def test_025_makes_proposal_source_provenance_immutable(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'harness_025_immutable.db'}"
    _run_alembic(
        database_url=database_url,
        command="upgrade",
        revision="024_unique_active_proposal_fingerprints",
    )
    space_id = str(uuid4())
    run_id = str(uuid4())
    proposal_id = str(uuid4())
    _seed_harness_run_and_duplicate_proposals(
        database_url=database_url,
        space_id=space_id,
        run_id=run_id,
        claim_fingerprint="e" * 32,
        proposals=(
            {
                "id": proposal_id,
                "source_key": "immutable",
                "title": "Immutable proposal provenance",
                "status": "pending_review",
                "created_at": "2026-07-03 10:00:00",
                "updated_at": "2026-07-03 10:00:00",
            },
        ),
    )
    _run_alembic(
        database_url=database_url,
        command="upgrade",
        revision="025_proposal_source_provenance",
    )

    engine = create_engine(database_url, future=True)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE harness_proposals SET title = :title WHERE id = :id",
                ),
                {"id": proposal_id, "title": "Review title may change"},
            )
        for mutation in (
            "source_provenance_status = 'verified'",
            "source_provenance_payload = '{}'",
        ):
            with (
                engine.begin() as connection,
                pytest.raises(
                    DBAPIError,
                    match="proposal source provenance is immutable",
                ),
            ):
                connection.execute(
                    text(
                        "UPDATE harness_proposals "
                        f"SET {mutation} WHERE id = :proposal_id",
                    ),
                    {"proposal_id": proposal_id},
                )
        with engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        """
                    SELECT title, source_provenance_status,
                           source_provenance_payload
                    FROM harness_proposals
                    WHERE id = :proposal_id
                    """,
                    ),
                    {"proposal_id": proposal_id},
                )
                .mappings()
                .one()
            )
    finally:
        engine.dispose()

    assert row["title"] == "Review title may change"
    assert row["source_provenance_status"] == "unverified"
    assert row["source_provenance_payload"] is None
