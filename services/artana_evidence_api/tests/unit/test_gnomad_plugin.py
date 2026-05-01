"""gnomAD source plugin tests."""

from __future__ import annotations

from uuid import UUID

import pytest
from artana_evidence_api.direct_source_search import (
    GnomADSourceSearchRequest,
    InMemoryDirectSourceSearchStore,
)
from artana_evidence_api.direct_sources.gnomad_gateway import GnomADGatewayFetchResult
from artana_evidence_api.evidence_selection_source_search import (
    EvidenceSelectionLiveSourceSearch,
)
from artana_evidence_api.source_plugins.contracts import SourceSearchExecutionContext
from artana_evidence_api.source_plugins.gnomad import GnomADSourcePlugin
from artana_evidence_api.source_registry import get_source_definition

_SPACE_ID = UUID("22222222-2222-2222-2222-222222222222")
_USER_ID = UUID("11111111-1111-1111-1111-111111111111")


class _Intent:
    source_key = "gnomad"
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


class _VariantIntent(_Intent):
    query = "17-5982158-C-T"
    gene_symbol = None


class _UnsupportedVariantIntent(_Intent):
    gene_symbol = None
    variant_hgvs = "NM_005121.3:c.977C>T"


class _StubGnomADGateway:
    def fetch_records(
        self,
        *,
        gene_symbol: str | None = None,
        variant_id: str | None = None,
        reference_genome: str = "GRCh38",
        dataset: str = "gnomad_r4",
        max_results: int = 20,
    ) -> GnomADGatewayFetchResult:
        return GnomADGatewayFetchResult(
            records=[
                {
                    "source": "gnomad",
                    "record_type": "gene_constraint",
                    "gene_symbol": gene_symbol or "MED13",
                    "gene_id": "ENSG00000108510",
                    "reference_genome": reference_genome,
                    "dataset": dataset,
                    "constraint": {"pLI": 1},
                    "pLI": 1.0,
                    "variant_id": variant_id,
                },
            ],
            fetched_records=1,
        )


def test_gnomad_plugin_metadata_matches_source_definition() -> None:
    plugin = GnomADSourcePlugin(gateway_factory=lambda: _StubGnomADGateway())
    definition = get_source_definition("gnomad")

    assert definition is not None
    assert plugin.source_definition() == definition
    assert plugin.metadata.source_key == "gnomad"
    assert plugin.metadata.request_schema_ref == "GnomADSourceSearchRequest"
    assert plugin.metadata.result_schema_ref == "GnomADSourceSearchResponse"


def test_gnomad_plugin_builds_gene_and_variant_query_payloads() -> None:
    plugin = GnomADSourcePlugin()

    assert plugin.build_query_payload(_Intent()) == {"gene_symbol": "MED13"}
    assert plugin.build_query_payload(_VariantIntent()) == {
        "variant_id": "17-5982158-C-T",
    }


def test_gnomad_plugin_rejects_hgvs_without_gnomad_variant_id() -> None:
    plugin = GnomADSourcePlugin()

    with pytest.raises(ValueError, match="gnomAD variant_id"):
        plugin.build_query_payload(_UnsupportedVariantIntent())


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        ({}, "Provide one of gene_symbol or variant_id"),
        (
            {"gene_symbol": "MED13", "variant_id": "17-5982158-C-T"},
            "Provide either gene_symbol or variant_id",
        ),
        (
            {"variant_id": "NM_005121.3:c.977C>T"},
            "variant_id must use gnomAD format",
        ),
    ],
)
def test_gnomad_search_request_rejects_invalid_query_shapes(
    payload: dict[str, object],
    error: str,
) -> None:
    with pytest.raises(ValueError, match=error):
        GnomADSourceSearchRequest.model_validate(payload)


@pytest.mark.asyncio
async def test_gnomad_plugin_runs_direct_search() -> None:
    plugin = GnomADSourcePlugin(gateway_factory=lambda: _StubGnomADGateway())
    store = InMemoryDirectSourceSearchStore()

    result = await plugin.run_direct_search(
        context=SourceSearchExecutionContext(
            space_id=_SPACE_ID,
            created_by=_USER_ID,
            store=store,
        ),
        search=EvidenceSelectionLiveSourceSearch(
            source_key="gnomad",
            query_payload={"gene_symbol": "MED13"},
            max_records=1,
        ),
    )

    assert result.source_key == "gnomad"
    assert result.query == "MED13"
    assert result.records[0]["gene_symbol"] == "MED13"
    assert (
        store.get(space_id=_SPACE_ID, source_key="gnomad", search_id=result.id)
        == result
    )


def test_gnomad_plugin_normalizes_variant_records_as_variant_aware() -> None:
    plugin = GnomADSourcePlugin()
    record = {
        "record_type": "variant_frequency",
        "variant_id": "17-5982158-C-T",
        "gene_symbol": "MED13",
        "dataset": "gnomad_r4",
        "reference_genome": "GRCh38",
        "genome": {"af": 0.00000656},
    }

    assert plugin.provider_external_id(record) == "17-5982158-C-T"
    assert plugin.recommends_variant_aware(record) is True
    assert plugin.normalize_record(record)["variant_id"] == "17-5982158-C-T"
    assert plugin.build_candidate_context(record).to_json()["source_key"] == "gnomad"
