"""Tests for the DrugMechDB curated mechanism-path source connector."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import httpx
import pytest
from artana_evidence_api.direct_source_search import InMemoryDirectSourceSearchStore
from artana_evidence_api.direct_sources.drugmechdb import (
    DRUGMECHDB_INDICATION_PATHS_URL,
    DrugMechDBGatewayFetchResult,
    DrugMechDBSourceGateway,
    DrugMechDBSourceSearchRequest,
    run_drugmechdb_direct_search,
)
from artana_evidence_api.source_plugins.contracts import (
    EvidenceSelectionSourceSearchError,
    SourceSearchExecutionContext,
)
from artana_evidence_api.source_plugins.drug_mechanisms.drugmechdb import (
    DrugMechDBSourcePlugin,
)
from artana_evidence_api.types.common import JSONObject
from pydantic import ValidationError


class _StubDrugMechDBGateway:
    async def fetch_records_async(
        self,
        *,
        query: str | None = None,
        drug_name: str | None = None,
        drugbank_id: str | None = None,
        disease: str | None = None,
        disease_mesh: str | None = None,
        node_id: str | None = None,
        path_id: str | None = None,
        max_results: int = 20,
    ) -> DrugMechDBGatewayFetchResult:
        del query, node_id, path_id, max_results
        return DrugMechDBGatewayFetchResult(
            records=[
                {
                    "source": "drugmechdb",
                    "path_id": "DB00619_MESH_D015464_1",
                    "drug_name": drug_name or "imatinib",
                    "drugbank_id": drugbank_id or "DB00619",
                    "drugbank_curie": "DB:DB00619",
                    "disease_name": disease or "CML (ph+)",
                    "disease_mesh": disease_mesh or "MESH:D015464",
                    "node_ids": [
                        "MESH:D000068877",
                        "UniProt:P00519",
                        "MESH:D015464",
                    ],
                    "edge_count": 2,
                    "node_count": 3,
                    "references": ["https://go.drugbank.com/drugs/DB00619"],
                    "license": "CC0-1.0",
                    "narrative": (
                        "DrugMechDB path DB00619_MESH_D015464_1: imatinib "
                        "(Drug; MESH:D000068877) decreases activity of BCR/ABL "
                        "(Protein; UniProt:P00519). BCR/ABL causes CML (ph+)."
                    ),
                },
            ],
            fetched_records=1,
            corpus_size=4846,
            commit_sha="41fea1332cdc56abab1c12761edd2e63a01ef9ca",
        )


@dataclass(frozen=True, slots=True)
class _Intent:
    source_key: str
    query: str | None = None
    gene_symbol: str | None = None
    variant_hgvs: str | None = None
    protein_variant: str | None = None
    uniprot_id: str | None = None
    drug_name: str | None = None
    drugbank_id: str | None = None
    disease: str | None = None
    phenotype: str | None = None
    organism: str | None = None
    taxon_id: int | None = None
    panels: list[str] | None = None


@dataclass(frozen=True, slots=True)
class _SearchInput:
    source_key: str
    query_payload: JSONObject
    max_records: int | None = None
    timeout_seconds: float | None = None


def _drugmechdb_yaml() -> str:
    return """
    - directed: true
      graph:
        _id: DB00619_MESH_D015464_1
        disease: CML (ph+)
        disease_mesh: MESH:D015464
        drug: imatinib
        drug_mesh: MESH:D000068877
        drugbank: DB:DB00619
      links:
      - key: decreases activity of
        source: MESH:D000068877
        target: UniProt:P00519
      - key: causes
        source: UniProt:P00519
        target: MESH:D015464
      nodes:
      - id: MESH:D000068877
        label: Drug
        name: imatinib
      - id: UniProt:P00519
        label: Protein
        name: BCR/ABL
      - id: MESH:D015464
        label: Disease
        name: CML (ph+)
      reference:
      - https://go.drugbank.com/drugs/DB00619
    - directed: true
      graph:
        _id: DB01257_MESH_D006457_1
        disease: Hemolytic anemia
        disease_mesh: MESH:D006457
        drug: eculizumab
        drug_mesh: MESH:D000077264
        drugbank: DB:DB01257
      links:
      - key: decreases activity of
        source: MESH:D000077264
        target: UniProt:P01031
      - key: causes
        source: UniProt:P01031
        target: MESH:D006457
      nodes:
      - id: MESH:D000077264
        label: Drug
        name: eculizumab
      - id: UniProt:P01031
        label: Protein
        name: Complement C5
      - id: MESH:D006457
        label: Disease
        name: Hemolytic anemia
    """


def test_drugmechdb_request_requires_bounded_filter_shape() -> None:
    request = DrugMechDBSourceSearchRequest.model_validate(
        {
            "drug_name": " imatinib ",
            "disease_mesh": " MESH:D015464 ",
            "max_results": 2,
        },
    )

    assert request.drug_name == "imatinib"
    assert request.disease_mesh == "MESH:D015464"
    assert request.query_text() == "drug_name:imatinib disease_mesh:MESH:D015464"

    with pytest.raises(ValidationError, match="Provide at least one"):
        DrugMechDBSourceSearchRequest.model_validate({})


@pytest.mark.asyncio
async def test_drugmechdb_gateway_parses_pinned_yaml_and_renders_paths() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(200, text=_drugmechdb_yaml(), request=request)

    gateway = DrugMechDBSourceGateway(transport=httpx.MockTransport(handler))

    result = await gateway.fetch_records_async(
        drugbank_id="DB00619",
        disease="CML",
        max_results=1,
    )
    cached_result = await gateway.fetch_records_async(node_id="UniProt:P01031")

    assert requests == [DRUGMECHDB_INDICATION_PATHS_URL]
    assert result.fetched_records == 1
    assert result.corpus_size == 2
    assert result.commit_sha == "41fea1332cdc56abab1c12761edd2e63a01ef9ca"
    assert result.records[0]["path_id"] == "DB00619_MESH_D015464_1"
    assert result.records[0]["drugbank_id"] == "DB00619"
    assert result.records[0]["drugbank_curie"] == "DB:DB00619"
    assert result.records[0]["disease_mesh"] == "MESH:D015464"
    assert result.records[0]["node_ids"] == [
        "MESH:D000068877",
        "UniProt:P00519",
        "MESH:D015464",
    ]
    assert result.records[0]["edge_count"] == 2
    assert result.records[0]["license"] == "CC0-1.0"
    assert "imatinib (Drug; MESH:D000068877) decreases activity of BCR/ABL" in str(
        result.records[0]["narrative"],
    )
    assert cached_result.records[0]["path_id"] == "DB01257_MESH_D006457_1"


@pytest.mark.asyncio
async def test_drugmechdb_direct_search_captures_license_and_batching_policy() -> None:
    space_id = uuid4()
    owner_id = uuid4()

    result = await run_drugmechdb_direct_search(
        space_id=space_id,
        created_by=owner_id,
        request=DrugMechDBSourceSearchRequest(
            drug_name="imatinib",
            disease="CML",
            max_results=2,
        ),
        gateway=_StubDrugMechDBGateway(),
        store=InMemoryDirectSourceSearchStore(),
    )

    assert result.space_id == space_id
    assert result.source_key == "drugmechdb"
    assert result.query == "drug_name:imatinib disease:CML"
    assert result.record_count == 1
    assert result.corpus_size == 4846
    assert result.records[0]["path_id"] == "DB00619_MESH_D015464_1"
    assert result.source_capture.source_key == "drugmechdb"
    assert result.source_capture.external_id == "DB00619_MESH_D015464_1"
    assert result.source_capture.provenance["license"] == "CC0-1.0"
    assert result.source_capture.provenance["extraction_policy"] == (
        "selective_batched_no_auto_bulk_extraction"
    )


@pytest.mark.asyncio
async def test_drugmechdb_plugin_plans_runs_and_normalizes_records() -> None:
    plugin = DrugMechDBSourcePlugin(gateway_factory=lambda: _StubDrugMechDBGateway())

    payload = plugin.build_query_payload(
        _Intent(
            source_key="drugmechdb",
            drug_name="imatinib",
            disease="CML",
        ),
    )

    assert payload == {"drug_name": "imatinib", "disease": "CML"}

    result = await plugin.run_direct_search(
        context=SourceSearchExecutionContext(
            space_id=UUID("22222222-2222-2222-2222-222222222222"),
            created_by=UUID("11111111-1111-1111-1111-111111111111"),
            store=InMemoryDirectSourceSearchStore(),
        ),
        search=_SearchInput(
            source_key="drugmechdb",
            query_payload={"drugbank_id": "DB00619", "disease_mesh": "MESH:D015464"},
        ),
    )

    context = plugin.build_candidate_context(result.records[0]).to_json()
    assert context["source_key"] == "drugmechdb"
    assert context["source_family"] == "drug_mechanism_path"
    assert context["provider_external_id"] == "DB00619_MESH_D015464_1"
    assert context["normalized_record"]["path_id"] == "DB00619_MESH_D015464_1"
    assert context["normalized_record"]["drugbank_id"] == "DB00619"
    assert context["normalized_record"]["disease_mesh"] == "MESH:D015464"
    assert context["normalized_record"]["license"] == "CC0-1.0"


@pytest.mark.asyncio
async def test_drugmechdb_plugin_requires_available_gateway() -> None:
    plugin = DrugMechDBSourcePlugin(gateway_factory=lambda: None)

    with pytest.raises(EvidenceSelectionSourceSearchError, match="DrugMechDB gateway"):
        await plugin.run_direct_search(
            context=SourceSearchExecutionContext(
                space_id=uuid4(),
                created_by=uuid4(),
                store=InMemoryDirectSourceSearchStore(),
            ),
            search=_SearchInput(
                source_key="drugmechdb",
                query_payload={"drug_name": "imatinib"},
            ),
        )
