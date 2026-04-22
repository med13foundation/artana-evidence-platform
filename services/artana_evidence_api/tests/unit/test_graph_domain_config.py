"""Unit tests for harness-owned graph-domain configuration."""

from __future__ import annotations

from artana_evidence_api.graph_domain_config import (
    ARTANA_EVIDENCE_API_CONNECTION_PROMPTS,
    ARTANA_EVIDENCE_API_SEARCH_CONFIG,
)


def test_graph_search_config_uses_local_prompt() -> None:
    assert ARTANA_EVIDENCE_API_SEARCH_CONFIG.step_key == "graph.search.v1"
    assert (
        "Artana Graph Search Agent" in ARTANA_EVIDENCE_API_SEARCH_CONFIG.system_prompt
    )


def test_graph_connection_prompt_config_defaults_to_clinvar() -> None:
    assert ARTANA_EVIDENCE_API_CONNECTION_PROMPTS.resolve_source_type(None) == "clinvar"
    assert ARTANA_EVIDENCE_API_CONNECTION_PROMPTS.resolve_source_type("  ") == "clinvar"


def test_graph_connection_prompt_config_normalizes_source_types() -> None:
    assert (
        ARTANA_EVIDENCE_API_CONNECTION_PROMPTS.resolve_source_type(" PubMed ")
        == "pubmed"
    )
    assert ARTANA_EVIDENCE_API_CONNECTION_PROMPTS.supported_source_types() == frozenset(
        {"clinvar", "pubmed"},
    )
    pubmed_prompt = ARTANA_EVIDENCE_API_CONNECTION_PROMPTS.system_prompt_for(" PUBMED ")
    assert pubmed_prompt is not None
    assert "PubMed-backed research spaces" in pubmed_prompt
