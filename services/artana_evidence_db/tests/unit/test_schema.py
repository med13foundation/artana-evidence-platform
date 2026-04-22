from __future__ import annotations

import pytest
from artana_evidence_db import schema_support as schema


def test_resolve_graph_db_schema_defaults_to_public(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GRAPH_DB_SCHEMA", raising=False)

    assert schema.resolve_graph_db_schema() == "graph_runtime"
    assert schema.graph_schema_name() == "graph_runtime"
    assert schema.graph_postgres_search_path() == '"graph_runtime", public'


def test_resolve_graph_db_schema_supports_dedicated_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_DB_SCHEMA", "graph_runtime")

    assert schema.resolve_graph_db_schema() == "graph_runtime"
    assert schema.graph_schema_name() == "graph_runtime"
    assert (
        schema.qualify_graph_table_name("graph_spaces") == "graph_runtime.graph_spaces"
    )
    assert (
        schema.qualify_graph_foreign_key_target("graph_spaces.id")
        == "graph_runtime.graph_spaces.id"
    )
    assert schema.graph_table_options(comment="graph table") == {
        "comment": "graph table",
        "schema": "graph_runtime",
    }
    assert schema.graph_postgres_search_path() == '"graph_runtime", public'


def test_resolve_graph_db_schema_rejects_invalid_identifiers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_DB_SCHEMA", "graph-runtime")

    with pytest.raises(
        ValueError,
        match="GRAPH_DB_SCHEMA must be a valid SQL identifier",
    ):
        schema.resolve_graph_db_schema()
