"""Unit tests for the Monarch KG direct-source gateway and plugin."""

from __future__ import annotations

from uuid import UUID

import pytest
from artana_evidence_api.direct_source_search import (
    InMemoryDirectSourceSearchStore,
    MonarchSourceSearchRequest,
    MonarchSourceSearchResponse,
    run_monarch_direct_search,
)
from artana_evidence_api.direct_sources.monarch import MonarchGatewayFetchResult
from artana_evidence_api.source_plugins.registry import source_plugin

_SPACE_ID = UUID("22222222-2222-4222-8222-222222222222")
_USER_ID = UUID("11111111-1111-4111-8111-111111111111")


@pytest.mark.asyncio
async def test_monarch_direct_search_preserves_biolink_and_primary_source_provenance() -> (
    None
):
    gateway = _FakeMonarchGateway(
        records=[
            {
                "id": "uuid:association-1",
                "category": "biolink:GeneToPhenotypicFeatureAssociation",
                "subject": "HGNC:7670",
                "subject_label": "MED13",
                "predicate": "biolink:has_phenotype",
                "object": "HP:0001263",
                "object_label": "Global developmental delay",
                "primary_knowledge_source": "infores:hpo-annotations",
                "aggregator_knowledge_source": ["infores:monarchinitiative"],
                "provided_by": "hpoa_gene_to_phenotype_edges",
                "publications": ["PMID:41663567"],
            },
        ],
    )

    result = await run_monarch_direct_search(
        space_id=_SPACE_ID,
        created_by=_USER_ID,
        request=MonarchSourceSearchRequest(
            association_kind="gene_phenotype",
            gene_symbols=["MED13"],
            max_results=10,
        ),
        gateway=gateway,
        store=InMemoryDirectSourceSearchStore(),
    )

    assert isinstance(result, MonarchSourceSearchResponse)
    assert result.source_key == "monarch"
    assert result.association_kind == "gene_phenotype"
    assert result.records == [
        {
            "id": "uuid:association-1",
            "category": "biolink:GeneToPhenotypicFeatureAssociation",
            "subject": "HGNC:7670",
            "subject_label": "MED13",
            "predicate": "biolink:has_phenotype",
            "object": "HP:0001263",
            "object_label": "Global developmental delay",
            "primary_knowledge_source": "infores:hpo-annotations",
            "aggregator_knowledge_source": ["infores:monarchinitiative"],
            "provided_by": "hpoa_gene_to_phenotype_edges",
            "publications": ["PMID:41663567"],
        },
    ]
    assert result.source_capture.provenance["provider"] == "Monarch KG API"
    assert result.source_capture.provenance["categories"] == [
        "biolink:GeneToPhenotypicFeatureAssociation",
    ]
    assert gateway.requests[0].category == "biolink:GeneToPhenotypicFeatureAssociation"


@pytest.mark.asyncio
async def test_monarch_direct_search_surfaces_mediator_hpo_coverage_gaps() -> None:
    result = await run_monarch_direct_search(
        space_id=_SPACE_ID,
        created_by=_USER_ID,
        request=MonarchSourceSearchRequest(
            association_kind="gene_phenotype",
            gene_symbols=["MED8", "MED13"],
            include_mediator_coverage_gaps=True,
            max_results=10,
        ),
        gateway=_FakeMonarchGateway(records=[]),
        store=InMemoryDirectSourceSearchStore(),
    )

    gap_records = [
        record
        for record in result.records
        if record.get("record_type") == "monarch_hpo_coverage_gap"
    ]
    assert gap_records == [
        {
            "record_type": "monarch_hpo_coverage_gap",
            "gene_symbol": "MED8",
            "mediator_module": "head",
            "association_category": "biolink:GeneToPhenotypicFeatureAssociation",
            "observed_hpo_phenotype_count": 0,
            "interpretation": "curation_gap_not_biological_null",
            "action": "review_upstream_monarch_hpo_coverage",
            "source": "monarch",
        },
    ]


def test_monarch_plugin_is_discoverable_and_builds_gene_phenotype_payload() -> None:
    plugin = source_plugin("monarch")

    assert plugin is not None
    payload = plugin.build_query_payload(_Intent())
    assert payload == {
        "association_kind": "gene_phenotype",
        "gene_symbols": ["MED13"],
    }


class _Intent:
    source_key = "monarch"
    query = None
    gene_symbol = "MED13"
    variant_hgvs = None
    protein_variant = None
    uniprot_id = None
    drug_name = None
    drugbank_id = None
    disease = None
    phenotype = None
    organism = None
    taxon_id = None
    panels = None


class _FakeMonarchGateway:
    def __init__(self, records: list[dict[str, object]]) -> None:
        self._records = records
        self.requests: list[MonarchSourceSearchRequest] = []

    async def fetch_records_async(
        self,
        request: MonarchSourceSearchRequest,
    ) -> MonarchGatewayFetchResult:
        self.requests.append(request)
        return MonarchGatewayFetchResult(
            records=self._records,
            fetched_records=len(self._records),
            total=len(self._records),
        )
