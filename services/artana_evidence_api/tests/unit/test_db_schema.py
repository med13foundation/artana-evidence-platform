from __future__ import annotations

import pytest
from artana_evidence_api import db_schema


def test_harness_runtime_search_path_defaults_to_harness_and_graph_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ARTANA_EVIDENCE_API_DB_SCHEMA", raising=False)
    monkeypatch.delenv("GRAPH_DB_SCHEMA", raising=False)

    assert db_schema.harness_runtime_postgres_search_path() == (
        '"artana_evidence_api", "graph_runtime", public'
    )


def test_harness_runtime_search_path_omits_public_duplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARTANA_EVIDENCE_API_DB_SCHEMA", "public")
    monkeypatch.setenv("GRAPH_DB_SCHEMA", "public")

    assert db_schema.harness_runtime_postgres_search_path() == "public"


def test_harness_runtime_search_path_keeps_distinct_non_public_schemas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARTANA_EVIDENCE_API_DB_SCHEMA", "artana_evidence_api")
    monkeypatch.setenv("GRAPH_DB_SCHEMA", "graph_runtime")

    assert db_schema.harness_runtime_postgres_search_path() == (
        '"artana_evidence_api", "graph_runtime", public'
    )
