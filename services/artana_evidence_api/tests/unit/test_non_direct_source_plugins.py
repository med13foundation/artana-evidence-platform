"""Tests for non-direct evidence-source plugin contracts."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from artana_evidence_api.source_plugins.authority.hgnc import HgncAuthorityPlugin
from artana_evidence_api.source_plugins.authority.mondo import MondoAuthorityPlugin
from artana_evidence_api.source_plugins.ingestion.pdf import PdfIngestionPlugin
from artana_evidence_api.source_plugins.ingestion.text import TextIngestionPlugin
from artana_evidence_api.source_plugins.registry import (
    authority_source_plugin,
    authority_source_plugin_keys,
    authority_source_plugins,
    document_ingestion_source_plugin,
    document_ingestion_source_plugin_keys,
    document_ingestion_source_plugins,
    evidence_source_plugin_keys,
    source_plugin_keys,
    validate_source_plugin_registry,
)
from artana_evidence_api.source_registry import (
    direct_search_source_keys,
    get_source_definition,
    research_plan_source_keys,
)
from artana_evidence_api.types.common import JSONObject


@dataclass(frozen=True, slots=True)
class _GroundingInput:
    source_key: str
    entity_kind: str
    query: str
    identifiers: JSONObject
    context: JSONObject


@dataclass(frozen=True, slots=True)
class _DocumentInput:
    source_key: str
    document_kind: str
    content_type: str
    filename: str | None
    metadata: JSONObject


def test_non_direct_plugin_registry_is_explicit_and_separate() -> None:
    validate_source_plugin_registry()

    assert authority_source_plugin_keys() == ("mondo", "hgnc")
    assert document_ingestion_source_plugin_keys() == ("pdf", "text")
    assert [plugin.source_key for plugin in authority_source_plugins()] == [
        "mondo",
        "hgnc",
    ]
    assert [plugin.source_key for plugin in document_ingestion_source_plugins()] == [
        "pdf",
        "text",
    ]
    assert not set(authority_source_plugin_keys()) & set(source_plugin_keys())
    assert not set(document_ingestion_source_plugin_keys()) & set(source_plugin_keys())
    assert not set(authority_source_plugin_keys()) & set(direct_search_source_keys())
    assert not set(document_ingestion_source_plugin_keys()) & set(
        direct_search_source_keys(),
    )
    assert evidence_source_plugin_keys() == research_plan_source_keys()


@pytest.mark.parametrize(
    "source_key",
    ["mondo", "hgnc"],
)
def test_authority_plugins_match_public_source_definitions(source_key: str) -> None:
    plugin = authority_source_plugin(source_key)
    definition = get_source_definition(source_key)

    assert plugin is not None
    assert definition is not None
    assert plugin.source_definition() == definition
    assert plugin.metadata.source_key == source_key
    assert plugin.metadata.direct_search_supported is False
    assert plugin.metadata.research_plan_supported is True


@pytest.mark.asyncio
async def test_mondo_plugin_resolves_identifier_grounding() -> None:
    plugin = MondoAuthorityPlugin()

    context = await plugin.resolve_entity(
        _GroundingInput(
            source_key="mondo",
            entity_kind="disease",
            query="congenital heart disease",
            identifiers={"mondo_id": "0007947"},
            context={"aliases": ["CHD"], "confidence": 0.91},
        ),
    )

    payload = context.to_json()
    assert payload["status"] == "resolved"
    assert payload["authority_reference"]["normalized_id"] == "MONDO:0007947"
    assert payload["authority_reference"]["label"] == "congenital heart disease"
    assert payload["authority_reference"]["aliases"] == ["CHD"]
    assert payload["confidence"] == 0.91


@pytest.mark.asyncio
async def test_mondo_plugin_represents_not_found_grounding() -> None:
    plugin = MondoAuthorityPlugin()

    context = await plugin.resolve_entity(
        _GroundingInput(
            source_key="mondo",
            entity_kind="disease",
            query="unknown disease",
            identifiers={},
            context={},
        ),
    )

    assert context.status == "not_found"
    assert context.authority_reference is None
    assert context.candidate_references == ()


@pytest.mark.asyncio
async def test_mondo_plugin_represents_ambiguous_grounding() -> None:
    plugin = MondoAuthorityPlugin()

    context = await plugin.resolve_entity(
        _GroundingInput(
            source_key="mondo",
            entity_kind="disease",
            query="cardiomyopathy",
            identifiers={},
            context={
                "candidates": [
                    {"mondo_id": "0004994", "label": "cardiomyopathy"},
                    {"mondo_id": "0005201", "label": "dilated cardiomyopathy"},
                ],
            },
        ),
    )

    payload = context.to_json()
    assert payload["status"] == "ambiguous"
    assert payload["authority_reference"] is None
    assert [candidate["normalized_id"] for candidate in payload["candidate_references"]] == [
        "MONDO:0004994",
        "MONDO:0005201",
    ]


@pytest.mark.asyncio
async def test_hgnc_plugin_resolves_identifier_grounding() -> None:
    plugin = HgncAuthorityPlugin()

    context = await plugin.resolve_entity(
        _GroundingInput(
            source_key="hgnc",
            entity_kind="gene",
            query="MED13",
            identifiers={"hgnc_id": "4073"},
            context={"symbol": "MED13", "aliases": ["THRAP1"], "confidence": 0.94},
        ),
    )

    payload = context.to_json()
    assert payload["status"] == "resolved"
    assert payload["authority_reference"]["normalized_id"] == "HGNC:4073"
    assert payload["authority_reference"]["label"] == "MED13"
    assert payload["authority_reference"]["aliases"] == ["THRAP1"]
    assert payload["confidence"] == 0.94


@pytest.mark.asyncio
async def test_hgnc_plugin_represents_not_found_grounding() -> None:
    plugin = HgncAuthorityPlugin()

    context = await plugin.resolve_entity(
        _GroundingInput(
            source_key="hgnc",
            entity_kind="gene",
            query="UNKNOWN1",
            identifiers={},
            context={},
        ),
    )

    assert context.status == "not_found"
    assert context.authority_reference is None
    assert context.candidate_references == ()


@pytest.mark.asyncio
async def test_hgnc_plugin_represents_ambiguous_grounding() -> None:
    plugin = HgncAuthorityPlugin()

    context = await plugin.resolve_entity(
        _GroundingInput(
            source_key="hgnc",
            entity_kind="gene",
            query="A",
            identifiers={},
            context={
                "candidates": [
                    {"hgnc_id": "HGNC:5", "symbol": "A1BG", "aliases": ["A1B"]},
                    {"hgnc_id": "HGNC:7", "symbol": "A2M", "aliases": ["A2MD"]},
                ],
            },
        ),
    )

    payload = context.to_json()
    assert payload["status"] == "ambiguous"
    assert payload["authority_reference"] is None
    assert [candidate["normalized_id"] for candidate in payload["candidate_references"]] == [
        "HGNC:5",
        "HGNC:7",
    ]


@pytest.mark.asyncio
async def test_authority_plugin_rejects_wrong_source_key() -> None:
    plugin = MondoAuthorityPlugin()

    with pytest.raises(ValueError, match="cannot ground"):
        await plugin.resolve_entity(
            _GroundingInput(
                source_key="hgnc",
                entity_kind="gene",
                query="A1BG",
                identifiers={"hgnc_id": "HGNC:5"},
                context={},
            ),
        )


@pytest.mark.parametrize(
    "source_key",
    ["pdf", "text"],
)
def test_ingestion_plugins_match_public_source_definitions(source_key: str) -> None:
    plugin = document_ingestion_source_plugin(source_key)
    definition = get_source_definition(source_key)

    assert plugin is not None
    assert definition is not None
    assert plugin.source_definition() == definition
    assert plugin.metadata.source_key == source_key
    assert plugin.metadata.direct_search_supported is False
    assert plugin.metadata.research_plan_supported is True


def test_pdf_plugin_builds_extraction_context_without_dispatch() -> None:
    plugin = PdfIngestionPlugin()

    context = plugin.build_extraction_context(
        _DocumentInput(
            source_key="pdf",
            document_kind="pdf",
            content_type="application/pdf",
            filename="paper.pdf",
            metadata={"title": "MED13 paper", "page_count": 12},
        ),
    )

    assert context.to_json() == {
        "source_key": "pdf",
        "source_family": "document",
        "display_name": "PDF Uploads",
        "document_kind": "pdf",
        "content_type": "application/pdf",
        "normalized_metadata": {
            "title": "MED13 paper",
            "page_count": 12,
            "filename": "paper.pdf",
            "document_kind": "pdf",
            "content_type": "application/pdf",
        },
        "extraction_entrypoint": "document_extraction",
        "limitations": [
            "Uploaded PDFs must be parsed, extracted, and reviewed before promotion.",
        ],
    }


def test_text_plugin_builds_extraction_context_without_dispatch() -> None:
    plugin = TextIngestionPlugin()

    context = plugin.build_extraction_context(
        _DocumentInput(
            source_key="text",
            document_kind="text",
            content_type="text/plain",
            filename=None,
            metadata={"title": "Copied abstract"},
        ),
    )

    assert context.to_json() == {
        "source_key": "text",
        "source_family": "document",
        "display_name": "Text Evidence",
        "document_kind": "text",
        "content_type": "text/plain",
        "normalized_metadata": {
            "title": "Copied abstract",
            "document_kind": "text",
            "content_type": "text/plain",
        },
        "extraction_entrypoint": "document_extraction",
        "limitations": [
            "User-provided text must be extracted and reviewed before promotion.",
        ],
    }


def test_ingestion_plugin_rejects_wrong_content_type() -> None:
    plugin = PdfIngestionPlugin()

    with pytest.raises(ValueError, match="content_type"):
        plugin.validate_document_input(
            _DocumentInput(
                source_key="pdf",
                document_kind="pdf",
                content_type="text/plain",
                filename="paper.txt",
                metadata={},
            ),
        )


def test_text_ingestion_plugin_rejects_wrong_content_type() -> None:
    plugin = TextIngestionPlugin()

    with pytest.raises(ValueError, match="content_type"):
        plugin.validate_document_input(
            _DocumentInput(
                source_key="text",
                document_kind="text",
                content_type="application/pdf",
                filename="paper.pdf",
                metadata={},
            ),
        )


def test_ingestion_plugin_rejects_wrong_document_kind() -> None:
    plugin = TextIngestionPlugin()

    with pytest.raises(ValueError, match="document_kind"):
        plugin.validate_document_input(
            _DocumentInput(
                source_key="text",
                document_kind="pdf",
                content_type="text/plain",
                filename="paper.txt",
                metadata={},
            ),
        )
