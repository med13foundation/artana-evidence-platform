"""Contract tests for source plugin registry behavior."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace

import pytest
from artana_evidence_api.source_adapters import require_source_adapter
from artana_evidence_api.source_plugins import registry as source_plugin_registry
from artana_evidence_api.source_plugins.contracts import (
    SourceAuthorityReference,
    SourceDocumentIngestionContext,
    SourceGroundingContext,
)
from artana_evidence_api.source_plugins.marrvel import MarrvelSourcePlugin
from artana_evidence_api.source_plugins.pubmed import PubMedSourcePlugin
from artana_evidence_api.source_plugins.registry import (
    source_plugin,
    source_plugin_for_execution,
    source_plugin_keys,
    source_plugins,
    validate_source_plugin_registry,
)
from artana_evidence_api.source_registry import get_source_definition


def test_source_plugin_registry_is_explicit_and_consistent() -> None:
    validate_source_plugin_registry()

    expected_keys = (
        "pubmed",
        "marrvel",
        "clinvar",
        "drugbank",
        "alphafold",
        "gnomad",
        "uniprot",
        "clinical_trials",
        "mgi",
        "zfin",
    )

    assert source_plugin_keys() == expected_keys
    assert tuple(
        plugin.source_definition().source_key for plugin in source_plugins()
    ) == expected_keys
    assert [plugin.source_key for plugin in source_plugins()] == [
        *expected_keys,
    ]
    assert source_plugin("clinical-trials") is source_plugin("clinical_trials")
    assert source_plugin("pubmed") is not None


def test_execution_registry_wraps_only_when_runner_dependencies_are_supplied() -> None:
    pubmed_plugin = source_plugin("pubmed")
    marrvel_plugin = source_plugin("marrvel")

    assert source_plugin_for_execution("pubmed") is pubmed_plugin
    assert source_plugin_for_execution("marrvel") is marrvel_plugin

    def pubmed_factory():
        return nullcontext(object())

    def marrvel_factory():
        return None

    wrapped_pubmed = source_plugin_for_execution(
        "pubmed",
        pubmed_discovery_service_factory=pubmed_factory,
    )
    wrapped_marrvel = source_plugin_for_execution(
        "marrvel",
        marrvel_discovery_service_factory=marrvel_factory,
    )

    assert isinstance(wrapped_pubmed, PubMedSourcePlugin)
    assert isinstance(wrapped_marrvel, MarrvelSourcePlugin)
    assert wrapped_pubmed is not pubmed_plugin
    assert wrapped_marrvel is not marrvel_plugin
    assert wrapped_pubmed.discovery_service_factory is pubmed_factory
    assert wrapped_marrvel.discovery_service_factory is marrvel_factory


def test_source_plugin_registry_rejects_metadata_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    plugin = source_plugin("pubmed")
    assert plugin is not None
    drifted_plugin = _MetadataDriftPlugin(plugin)
    monkeypatch.setattr(
        source_plugin_registry,
        "_SOURCE_PLUGINS",
        (drifted_plugin, *source_plugin_registry._SOURCE_PLUGINS[1:]),
    )

    with pytest.raises(RuntimeError, match="display_name"):
        validate_source_plugin_registry()


class _MetadataDriftPlugin:
    def __init__(self, wrapped: object) -> None:
        self._wrapped = wrapped

    @property
    def metadata(self):
        return replace(self._wrapped.metadata, display_name="Drifted PubMed")

    def __getattr__(self, name: str):
        return getattr(self._wrapped, name)


def test_plugin_backed_adapters_use_plugin_contracts() -> None:
    for source_key in source_plugin_keys():
        adapter = require_source_adapter(source_key)
        plugin = source_plugin(source_key)
        definition = get_source_definition(source_key)

        assert plugin is not None
        assert definition is not None
        assert adapter.__class__.__name__ == "_PluginSourceAdapter"
        assert plugin.metadata.source_key == source_key
        assert plugin.metadata.direct_search_supported is True
        assert adapter.display_name == plugin.display_name == definition.display_name
        assert adapter.source_family == plugin.source_family == definition.source_family
        assert adapter.request_schema_ref == plugin.request_schema_ref
        assert adapter.result_schema_ref == plugin.result_schema_ref
        assert adapter.proposal_type == plugin.review_policy.proposal_type
        assert adapter.review_type == plugin.review_policy.review_type


def test_authority_source_contract_serializes_grounding_context() -> None:
    authority = SourceAuthorityReference(
        source_key="mondo",
        source_family="ontology",
        display_name="MONDO",
        entity_kind="disease",
        normalized_id="MONDO:0007947",
        label="congenital heart disease",
        aliases=("CHD",),
        provenance={"source_url": "https://mondo.example/MONDO_0007947"},
    )
    context = SourceGroundingContext(
        source_key="mondo",
        source_family="ontology",
        display_name="MONDO",
        entity_kind="disease",
        query="CHD",
        status="resolved",
        authority_reference=authority,
        candidate_references=(authority,),
        confidence=0.92,
        limitations=("Ontology grounding is not clinical evidence by itself.",),
    )

    assert context.to_json() == {
        "source_key": "mondo",
        "source_family": "ontology",
        "display_name": "MONDO",
        "entity_kind": "disease",
        "query": "CHD",
        "status": "resolved",
        "authority_reference": {
            "source_key": "mondo",
            "source_family": "ontology",
            "display_name": "MONDO",
            "entity_kind": "disease",
            "normalized_id": "MONDO:0007947",
            "label": "congenital heart disease",
            "aliases": ["CHD"],
            "provenance": {"source_url": "https://mondo.example/MONDO_0007947"},
        },
        "candidate_references": [
            {
                "source_key": "mondo",
                "source_family": "ontology",
                "display_name": "MONDO",
                "entity_kind": "disease",
                "normalized_id": "MONDO:0007947",
                "label": "congenital heart disease",
                "aliases": ["CHD"],
                "provenance": {"source_url": "https://mondo.example/MONDO_0007947"},
            },
        ],
        "confidence": 0.92,
        "limitations": ["Ontology grounding is not clinical evidence by itself."],
    }


def test_authority_source_contract_serializes_unknown_grounding() -> None:
    context = SourceGroundingContext(
        source_key="hgnc",
        source_family="ontology",
        display_name="HGNC",
        entity_kind="gene",
        query="UNKNOWN1",
        status="not_found",
        authority_reference=None,
        candidate_references=(),
        confidence=None,
        limitations=("Unresolved symbols must not create grounded evidence.",),
    )

    assert context.to_json() == {
        "source_key": "hgnc",
        "source_family": "ontology",
        "display_name": "HGNC",
        "entity_kind": "gene",
        "query": "UNKNOWN1",
        "status": "not_found",
        "authority_reference": None,
        "candidate_references": [],
        "confidence": None,
        "limitations": ["Unresolved symbols must not create grounded evidence."],
    }


def test_authority_source_contract_serializes_ambiguous_grounding() -> None:
    first = SourceAuthorityReference(
        source_key="hgnc",
        source_family="ontology",
        display_name="HGNC",
        entity_kind="gene",
        normalized_id="HGNC:1",
        label="A1BG",
        aliases=("A1B",),
        provenance={"rank": 1},
    )
    second = SourceAuthorityReference(
        source_key="hgnc",
        source_family="ontology",
        display_name="HGNC",
        entity_kind="gene",
        normalized_id="HGNC:2",
        label="A2M",
        aliases=("A2MD",),
        provenance={"rank": 2},
    )
    context = SourceGroundingContext(
        source_key="hgnc",
        source_family="ontology",
        display_name="HGNC",
        entity_kind="gene",
        query="A",
        status="ambiguous",
        authority_reference=None,
        candidate_references=(first, second),
        confidence=None,
        limitations=("Ambiguous symbols require review before use.",),
    )

    payload = context.to_json()

    assert payload["status"] == "ambiguous"
    assert payload["authority_reference"] is None
    assert payload["candidate_references"] == [
        {
            "source_key": "hgnc",
            "source_family": "ontology",
            "display_name": "HGNC",
            "entity_kind": "gene",
            "normalized_id": "HGNC:1",
            "label": "A1BG",
            "aliases": ["A1B"],
            "provenance": {"rank": 1},
        },
        {
            "source_key": "hgnc",
            "source_family": "ontology",
            "display_name": "HGNC",
            "entity_kind": "gene",
            "normalized_id": "HGNC:2",
            "label": "A2M",
            "aliases": ["A2MD"],
            "provenance": {"rank": 2},
        },
    ]


def test_document_ingestion_contract_serializes_extraction_context() -> None:
    context = SourceDocumentIngestionContext(
        source_key="pdf",
        source_family="document",
        display_name="PDF Uploads",
        document_kind="pdf",
        content_type="application/pdf",
        normalized_metadata={"filename": "paper.pdf", "page_count": 12},
        extraction_entrypoint="document_extraction",
        limitations=("Uploaded documents require extraction and review.",),
    )

    assert context.to_json() == {
        "source_key": "pdf",
        "source_family": "document",
        "display_name": "PDF Uploads",
        "document_kind": "pdf",
        "content_type": "application/pdf",
        "normalized_metadata": {"filename": "paper.pdf", "page_count": 12},
        "extraction_entrypoint": "document_extraction",
        "limitations": ["Uploaded documents require extraction and review."],
    }
