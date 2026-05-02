"""Orphanet source plugin metadata, planning, and execution tests."""

from __future__ import annotations

from uuid import uuid4

import pytest
from artana_evidence_api.direct_source_search import InMemoryDirectSourceSearchStore
from artana_evidence_api.direct_sources.orphanet_gateway import (
    OrphanetGatewayFetchResult,
)
from artana_evidence_api.evidence_selection_source_planning import PlannedSourceIntent
from artana_evidence_api.evidence_selection_source_search import (
    EvidenceSelectionLiveSourceSearch,
)
from artana_evidence_api.source_plugins.contracts import (
    EvidenceSelectionSourceSearchError,
    SourceSearchExecutionContext,
)
from artana_evidence_api.source_plugins.rare_disease.orphanet import (
    OrphanetSourcePlugin,
)
from artana_evidence_api.source_registry import get_source_definition
from pydantic import ValidationError


def test_orphanet_plugin_metadata_requires_orphacode_credentials() -> None:
    plugin = OrphanetSourcePlugin()
    definition = get_source_definition("orphanet")

    assert definition is not None
    assert plugin.source_definition() == definition
    assert plugin.source_key == "orphanet"
    assert plugin.source_family == "rare_disease"
    assert plugin.metadata.requires_credentials is True
    assert plugin.metadata.credential_names == ("ORPHACODE_API_KEY",)
    assert plugin.request_schema_ref == "OrphanetSourceSearchRequest"
    assert plugin.result_schema_ref == "OrphanetSourceSearchResponse"


def test_orphanet_plugin_builds_query_payload_from_disease_context() -> None:
    plugin = OrphanetSourcePlugin()
    intent = PlannedSourceIntent(
        source_key="orphanet",
        disease=" Marfan   syndrome ",
        phenotype="connective tissue disorder",
        evidence_role="rare disease nomenclature",
        reason="Ground rare disease context.",
    )

    assert plugin.build_query_payload(intent) == {"query": "Marfan syndrome"}


def test_orphanet_plugin_builds_orphacode_payload_from_query() -> None:
    plugin = OrphanetSourcePlugin()
    intent = PlannedSourceIntent(
        source_key="orphanet",
        query="ORPHA:558",
        evidence_role="rare disease nomenclature",
        reason="Fetch exact ORPHAcode.",
    )

    assert plugin.build_query_payload(intent) == {"orphacode": 558}


def test_orphanet_plugin_normalizes_candidate_context() -> None:
    plugin = OrphanetSourcePlugin()

    context = plugin.build_candidate_context(_orphanet_record()).to_json()

    assert context["source_key"] == "orphanet"
    assert context["source_family"] == "rare_disease"
    assert context["provider_external_id"] == "ORPHA:558"
    assert context["variant_aware_recommended"] is False
    assert context["normalized_record"] == {
        "orphanet_id": "ORPHA:558",
        "orpha_code": "558",
        "preferred_term": "Marfan syndrome",
        "synonyms": ["MFS"],
        "definition": "A connective tissue disorder.",
        "typology": "Disease",
        "status": "Active",
        "classification_level": "Disorder",
        "orphanet_url": "https://orpha.example/558",
    }
    assert context["extraction_policy"]["proposal_type"] == (
        "rare_disease_context_candidate"
    )


def test_orphanet_plugin_validates_source_key_mismatch() -> None:
    plugin = OrphanetSourcePlugin()

    with pytest.raises(
        EvidenceSelectionSourceSearchError,
        match="Orphanet plugin requires canonical source_key 'orphanet'",
    ):
        plugin.validate_live_search(
            EvidenceSelectionLiveSourceSearch(
                source_key="clinvar",
                query_payload={"query": "Marfan syndrome"},
            ),
        )


def test_orphanet_plugin_rejects_invalid_live_search_payload() -> None:
    plugin = OrphanetSourcePlugin()

    with pytest.raises(ValidationError, match="Provide one of query or orphacode"):
        plugin.validate_live_search(
            EvidenceSelectionLiveSourceSearch(
                source_key="orphanet",
                query_payload={},
            ),
        )


@pytest.mark.asyncio
async def test_orphanet_plugin_runs_existing_direct_search_path() -> None:
    plugin = OrphanetSourcePlugin(gateway_factory=lambda: _FakeOrphanetGateway())
    store = InMemoryDirectSourceSearchStore()
    context = SourceSearchExecutionContext(
        space_id=uuid4(),
        created_by=uuid4(),
        store=store,
    )

    result = await plugin.run_direct_search(
        context=context,
        search=EvidenceSelectionLiveSourceSearch(
            source_key="orphanet",
            query_payload={"query": "Marfan syndrome"},
            max_records=1,
        ),
    )

    assert result.source_key == "orphanet"
    assert result.query == "Marfan syndrome"
    assert result.max_results == 1
    assert result.record_count == 1
    assert result.records == [_orphanet_record()]
    assert result.source_capture.source_key == "orphanet"
    assert result.source_capture.external_id == "ORPHA:558"
    assert (
        store.get(
            space_id=result.space_id,
            source_key="orphanet",
            search_id=result.id,
        )
        == result
    )


class _FakeOrphanetGateway:
    async def fetch_records_async(
        self,
        *,
        query: str | None = None,
        orphacode: int | None = None,
        language: str = "EN",
        max_results: int = 20,
    ) -> OrphanetGatewayFetchResult:
        assert query == "Marfan syndrome"
        assert orphacode is None
        assert language == "EN"
        assert max_results == 1
        return OrphanetGatewayFetchResult(
            records=[_orphanet_record()], fetched_records=1
        )


def _orphanet_record() -> dict[str, object]:
    return {
        "orpha_code": "558",
        "orphanet_id": "ORPHA:558",
        "preferred_term": "Marfan syndrome",
        "name": "Marfan syndrome",
        "synonyms": ["MFS"],
        "definition": "A connective tissue disorder.",
        "typology": "Disease",
        "status": "Active",
        "classification_level": "Disorder",
        "orphanet_url": "https://orpha.example/558",
        "source": "orphanet",
    }
