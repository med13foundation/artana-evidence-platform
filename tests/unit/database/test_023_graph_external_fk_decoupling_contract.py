"""Contract checks for graph schema decoupling from non-graph tables."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _resolve_alembic_binary() -> str:
    candidate_paths = (
        Path(sys.executable).resolve().parent / "alembic",
        REPOSITORY_ROOT / ".venv" / "bin" / "alembic",
        REPOSITORY_ROOT / "venv" / "bin" / "alembic",
    )
    for candidate_path in candidate_paths:
        if candidate_path.exists():
            return candidate_path.as_posix()
    return "alembic"


def _run_alembic_upgrade(*, database_url: str) -> None:
    env = dict(os.environ)
    env["ALEMBIC_DATABASE_URL"] = database_url
    subprocess.run(
        [
            _resolve_alembic_binary(),
            "-c",
            REPOSITORY_ROOT.joinpath(
                "services",
                "artana_evidence_db",
                "alembic.ini",
            ).as_posix(),
            "upgrade",
            "head",
        ],
        check=True,
        cwd=REPOSITORY_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def _foreign_key_targets(database_url: str, table_name: str) -> set[str]:
    engine = create_engine(database_url, future=True)
    try:
        inspector = inspect(engine)
        return {
            foreign_key["referred_table"]
            for foreign_key in inspector.get_foreign_keys(table_name)
            if foreign_key.get("referred_table")
        }
    finally:
        engine.dispose()


def _column_names(database_url: str, table_name: str) -> set[str]:
    engine = create_engine(database_url, future=True)
    try:
        inspector = inspect(engine)
        return {column["name"] for column in inspector.get_columns(table_name)}
    finally:
        engine.dispose()


def test_graph_schema_does_not_fk_to_users_for_actor_tracking(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'graph_actor_fk_contract.db'}"
    _run_alembic_upgrade(database_url=database_url)

    relation_claim_targets = _foreign_key_targets(database_url, "relation_claims")
    relation_targets = _foreign_key_targets(database_url, "relations")

    assert "users" not in relation_claim_targets
    assert "users" not in relation_targets
    assert "research_spaces" not in relation_claim_targets
    assert relation_claim_targets == {"relations"}
    assert {
        "entities",
        "dictionary_relation_types",
        "provenance",
    } == relation_targets
    assert "research_spaces" not in relation_targets


def test_graph_schema_does_not_fk_to_source_documents_for_external_refs(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'graph_document_fk_contract.db'}"
    _run_alembic_upgrade(database_url=database_url)

    claim_relation_targets = _foreign_key_targets(database_url, "claim_relations")
    projection_source_targets = _foreign_key_targets(
        database_url,
        "relation_projection_sources",
    )

    assert "source_documents" not in claim_relation_targets
    assert "source_documents" not in projection_source_targets
    assert "research_spaces" not in claim_relation_targets
    assert "research_spaces" not in projection_source_targets
    assert claim_relation_targets == {"relation_claims"}
    assert projection_source_targets == {"relations", "relation_claims"}


def test_graph_kernel_tables_do_not_fk_to_platform_space_tables(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'graph_space_fk_contract.db'}"
    _run_alembic_upgrade(database_url=database_url)

    graph_owned_tables = (
        "entities",
        "entity_aliases",
        "entity_embeddings",
        "observations",
        "provenance",
        "relations",
        "relation_claims",
        "claim_participants",
        "claim_relations",
        "relation_projection_sources",
        "reasoning_paths",
        "concept_sets",
        "concept_members",
        "concept_aliases",
        "concept_links",
        "concept_policies",
        "concept_decisions",
        "concept_harness_results",
        "graph_operation_runs",
    )

    for table_name in graph_owned_tables:
        foreign_key_targets = _foreign_key_targets(database_url, table_name)
        assert "research_spaces" not in foreign_key_targets
        assert "research_space_memberships" not in foreign_key_targets


def test_graph_space_registry_is_graph_owned_without_external_foreign_keys(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'graph_space_registry_fk_contract.db'}"
    _run_alembic_upgrade(database_url=database_url)

    graph_space_targets = _foreign_key_targets(database_url, "graph_spaces")

    assert graph_space_targets == set()


def test_graph_space_memberships_only_fk_to_graph_space_registry(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'graph_space_membership_fk_contract.db'}"
    _run_alembic_upgrade(database_url=database_url)

    graph_membership_targets = _foreign_key_targets(
        database_url,
        "graph_space_memberships",
    )

    assert graph_membership_targets == {"graph_spaces"}


def test_graph_schema_exposes_external_document_reference_columns(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'graph_document_ref_columns.db'}"
    _run_alembic_upgrade(database_url=database_url)

    assert "source_document_ref" in _column_names(database_url, "relation_claims")
    assert "source_document_ref" in _column_names(database_url, "claim_evidence")
    assert "source_document_ref" in _column_names(database_url, "claim_relations")
    assert "source_document_ref" in _column_names(
        database_url,
        "relation_projection_sources",
    )
    assert "source_document_ref" in _column_names(database_url, "relation_evidence")
