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
CURRENT_HEAD_REVISION = "030_proposal_identity_collision"
_DECISION_TABLES = (
    "harness_proposals",
    "harness_review_items",
    "harness_run_approvals",
)
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


def test_026_gives_every_decision_table_a_nullable_reviewer(tmp_path: Path) -> None:
    """Decisions carried a written reason but no author until 026.

    The columns are nullable on purpose: rows decided before the migration have
    no attribution, and inventing one would be worse than admitting the gap.
    """
    database_url = f"sqlite:///{tmp_path / 'harness_026_actor.db'}"
    _run_alembic(
        database_url=database_url,
        command="upgrade",
        revision="025_proposal_source_provenance",
    )
    space_id = str(uuid4())
    run_id = str(uuid4())
    proposal_id = str(uuid4())
    _seed_harness_run_and_duplicate_proposals(
        database_url=database_url,
        space_id=space_id,
        run_id=run_id,
        claim_fingerprint="f" * 32,
        proposals=(
            {
                "id": proposal_id,
                "source_key": "pre-attribution",
                "title": "Decided before anyone was recorded",
                "status": "pending_review",
                "created_at": "2026-07-03 10:00:00",
                "updated_at": "2026-07-03 10:00:00",
            },
        ),
    )

    _run_alembic(
        database_url=database_url,
        command="upgrade",
        revision="026_review_decision_actor",
    )

    engine = create_engine(database_url, future=True)
    try:
        inspector = inspect(engine)
        columns_by_table = {
            table_name: {
                column["name"]: column for column in inspector.get_columns(table_name)
            }
            for table_name in _DECISION_TABLES
        }
        with engine.connect() as connection:
            legacy_row = (
                connection.execute(
                    text(
                        """
                        SELECT decided_by_user_id, decided_by_email
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

    for table_name, columns in columns_by_table.items():
        assert "decided_by_user_id" in columns, table_name
        assert "decided_by_email" in columns, table_name
        assert columns["decided_by_user_id"]["nullable"], table_name
        assert columns["decided_by_email"]["nullable"], table_name
    assert legacy_row["decided_by_user_id"] is None
    assert legacy_row["decided_by_email"] is None


def test_027_gives_an_approval_its_own_superseded_decision_column(
    tmp_path: Path,
) -> None:
    """The decision trail must not share a column with caller-supplied metadata.

    It was first written into metadata_payload, which callers populate freely --
    so a caller could have its own data read back as decision history.
    """
    database_url = f"sqlite:///{tmp_path / 'harness_027_superseded.db'}"
    _run_alembic(
        database_url=database_url,
        command="upgrade",
        revision=CURRENT_HEAD_REVISION,
    )

    engine = create_engine(database_url, future=True)
    try:
        columns = {
            column["name"]: column
            for column in inspect(engine).get_columns("harness_run_approvals")
        }
    finally:
        engine.dispose()

    assert "superseded_decisions_payload" in columns
    assert columns["superseded_decisions_payload"]["nullable"]
    assert "metadata_payload" in columns


def test_028_widens_both_fingerprint_columns_without_losing_their_indexes(
    tmp_path: Path,
) -> None:
    """Three writers outgrew these columns, so nothing they wrote could persist.

    A ClaimFrame's dedupe identity is 64 characters and evidence-selection
    staging writes 83 and 90, against declared widths of 32 and 64.  Postgres
    rejected all of them.  Both columns carry a partial unique index that the
    rebuild must not drop, and the seeded row must survive untouched -- this is
    a width change, not a data change.
    """
    database_url = f"sqlite:///{tmp_path / 'harness_028_fingerprints.db'}"
    _run_alembic(
        database_url=database_url,
        command="upgrade",
        revision="027_approval_superseded_decisions",
    )
    fingerprint = "c" * 32
    proposal_id = str(uuid4())
    _seed_harness_run_and_duplicate_proposals(
        database_url=database_url,
        space_id=str(uuid4()),
        run_id=str(uuid4()),
        claim_fingerprint=fingerprint,
        proposals=(
            {
                "id": proposal_id,
                "source_key": "narrow-column-era",
                "title": "Written while the column was still varchar(32)",
                "status": "pending_review",
                "created_at": "2026-07-03 10:00:00",
                "updated_at": "2026-07-03 10:00:00",
            },
        ),
    )

    _run_alembic(
        database_url=database_url,
        command="upgrade",
        revision="028_widen_fingerprint_columns",
    )

    engine = create_engine(database_url, future=True)
    try:
        inspector = inspect(engine)
        widths = {
            (table_name, column_name): inspector.get_columns(table_name)
            for table_name, column_name in (
                ("harness_proposals", "claim_fingerprint"),
                ("harness_review_items", "review_fingerprint"),
            )
        }
        index_names = {
            table_name: {
                index["name"] for index in inspector.get_indexes(table_name)
            }
            for table_name in ("harness_proposals", "harness_review_items")
        }
    finally:
        engine.dispose()

    for (table_name, column_name), columns in widths.items():
        column = next(
            candidate for candidate in columns if candidate["name"] == column_name
        )
        assert column["type"].length == 128, (table_name, column_name)

    assert (
        "uq_harness_proposals_active_space_claim_fingerprint"
        in index_names["harness_proposals"]
    )
    assert (
        "uq_harness_review_items_space_review_fingerprint"
        in index_names["harness_review_items"]
    )
    assert _proposal_rows(
        database_url=database_url,
        claim_fingerprint=fingerprint,
    ) == [{"id": proposal_id, "status": "pending_review", "decision_reason": None}]


def test_028_downgrade_refuses_to_truncate_a_stored_identity(
    tmp_path: Path,
) -> None:
    """Narrowing back must fail loudly rather than shorten a fingerprint.

    A truncated fingerprint is not a shorter name for the same claim; it is a
    different identity that will collide with strangers.
    """
    database_url = f"sqlite:///{tmp_path / 'harness_028_downgrade.db'}"
    _run_alembic(
        database_url=database_url,
        command="upgrade",
        revision="028_widen_fingerprint_columns",
    )
    _seed_harness_run_and_duplicate_proposals(
        database_url=database_url,
        space_id=str(uuid4()),
        run_id=str(uuid4()),
        claim_fingerprint="d" * 64,
        proposals=(
            {
                "id": str(uuid4()),
                "source_key": "frame-backed",
                "title": "Carries a full ClaimFrame dedupe identity",
                "status": "pending_review",
                "created_at": "2026-07-03 10:00:00",
                "updated_at": "2026-07-03 10:00:00",
            },
        ),
    )

    completed = _run_alembic_process(
        database_url=database_url,
        command="downgrade",
        revision="027_approval_superseded_decisions",
        check=False,
    )

    assert completed.returncode != 0
    assert "Cannot narrow" in completed.stderr


def test_029_gives_a_parked_proposal_its_own_adjudication_column(
    tmp_path: Path,
) -> None:
    """An identity adjudication must not share a column with caller metadata.

    A reviewer settling a parked fingerprint collision (ART-DATA-001) is making
    a system-recorded judgement, so it cannot live in metadata_payload, which
    callers populate freely. It also has to outlive the later promote or reject
    of a released proposal, which overwrites decision_reason and decided_by.
    """
    database_url = f"sqlite:///{tmp_path / 'harness_029_adjudication.db'}"
    _run_alembic(
        database_url=database_url,
        command="upgrade",
        revision=CURRENT_HEAD_REVISION,
    )

    engine = create_engine(database_url, future=True)
    try:
        columns = {
            column["name"]: column
            for column in inspect(engine).get_columns("harness_proposals")
        }
    finally:
        engine.dispose()

    assert "identity_adjudication_payload" in columns
    assert columns["identity_adjudication_payload"]["nullable"]
    assert "metadata_payload" in columns


def test_030_records_what_a_parked_proposal_collided_with(
    tmp_path: Path,
) -> None:
    """A reviewer cannot judge "same fact?" against a counterpart nobody stored.

    Migration 029 gave a parked proposal an exit; the evidence to take it lived
    only in a prose decision_reason on one path and nowhere at all on the
    intra-batch path. The collision gets its own column, separate from the
    adjudication because it records what the system observed rather than what a
    reviewer concluded, and it exists before any reviewer sees the row.
    """
    database_url = f"sqlite:///{tmp_path / 'harness_030_collision.db'}"
    _run_alembic(
        database_url=database_url,
        command="upgrade",
        revision=CURRENT_HEAD_REVISION,
    )

    engine = create_engine(database_url, future=True)
    try:
        columns = {
            column["name"]: column
            for column in inspect(engine).get_columns("harness_proposals")
        }
    finally:
        engine.dispose()

    assert "identity_collision_payload" in columns
    assert columns["identity_collision_payload"]["nullable"]
    assert "identity_adjudication_payload" in columns, (
        "the collision must not replace the adjudication trail"
    )

    _run_alembic(
        database_url=database_url,
        command="downgrade",
        revision="029_proposal_identity_adjudication",
    )
    engine = create_engine(database_url, future=True)
    try:
        remaining = {
            column["name"]
            for column in inspect(engine).get_columns("harness_proposals")
        }
    finally:
        engine.dispose()
    assert "identity_collision_payload" not in remaining
    assert "identity_adjudication_payload" in remaining
