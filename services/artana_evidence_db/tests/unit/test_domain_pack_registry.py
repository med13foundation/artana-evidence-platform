"""Unit tests for graph domain-pack registry selection."""

from __future__ import annotations

from dataclasses import fields

import pytest
from artana_evidence_db.runtime import GraphDomainPack
from artana_evidence_db.runtime.pack_registry import (
    list_graph_domain_packs,
    resolve_graph_domain_pack,
)


def test_graph_domain_pack_registry_lists_builtin_packs() -> None:
    packs = list_graph_domain_packs()

    pack_names = {pack.name for pack in packs}
    assert pack_names == {"biomedical", "sports"}


def test_graph_domain_pack_registry_resolves_env_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_DOMAIN_PACK", "sports")

    pack = resolve_graph_domain_pack()

    assert pack.name == "sports"
    assert pack.runtime_identity.service_name == "Sports Graph Service"
    assert pack.dictionary_loading_extension.builtin_domain_contexts[1].id == (
        "competition"
    )
    assert pack.agent_capabilities.graph_connection.supported_source_types == (
        "match_report",
        "roster",
    )


def test_graph_domain_pack_registry_rejects_unknown_pack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_DOMAIN_PACK", "legal")

    with pytest.raises(RuntimeError, match="Supported packs: biomedical, sports"):
        resolve_graph_domain_pack()


def test_graph_domain_pack_does_not_expose_ai_runtime_config() -> None:
    pack_fields = {field.name for field in fields(GraphDomainPack)}

    assert "agent_capabilities" in pack_fields
    assert "entity_recognition_prompt" not in pack_fields
    assert "entity_recognition_payload" not in pack_fields
    assert "entity_recognition_fallback" not in pack_fields
    assert "entity_recognition_bootstrap" not in pack_fields
    assert "extraction_prompt" not in pack_fields
    assert "extraction_payload" not in pack_fields
    assert "extraction_fallback" not in pack_fields
    assert "graph_connection_prompt" not in pack_fields
    assert "search_extension" not in pack_fields


def test_biomedical_pack_exposes_only_opaque_agent_capabilities() -> None:
    pack = resolve_graph_domain_pack("biomedical")

    assert pack.agent_capabilities.entity_recognition.supported_source_types == (
        "clinvar",
        "file_upload",
        "marrvel",
        "pubmed",
    )
    assert pack.agent_capabilities.extraction.supported_source_types == (
        "clinvar",
        "marrvel",
        "pubmed",
    )
    assert pack.agent_capabilities.graph_connection.default_source_type == "clinvar"
    assert pack.agent_capabilities.graph_search.supported_source_types == ("graph",)
