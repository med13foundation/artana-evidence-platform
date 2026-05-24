"""Tests for the DiMe digital-measures direct source connector."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import httpx
import pytest
from artana_evidence_api.direct_source_search import InMemoryDirectSourceSearchStore
from artana_evidence_api.direct_sources.dime import (
    DiMeGatewayFetchResult,
    DiMePublicCatalogGateway,
    DiMeSourceSearchRequest,
    dime_methodological_reference,
    run_dime_direct_search,
)
from artana_evidence_api.source_plugins.contracts import (
    EvidenceSelectionSourceSearchError,
    SourceSearchExecutionContext,
)
from artana_evidence_api.source_plugins.digital_measurement.dime import (
    DiMeSourcePlugin,
)
from artana_evidence_api.types.common import JSONObject
from pydantic import ValidationError


class _StubDiMeGateway:
    async def fetch_records_async(
        self,
        *,
        query: str | None = None,
        disease: str | None = None,
        therapeutic_area: str | None = None,
        sensor: str | None = None,
        max_results: int = 20,
    ) -> DiMeGatewayFetchResult:
        del query, therapeutic_area, max_results
        return DiMeGatewayFetchResult(
            records=[
                {
                    "endpoint_identifier": "3",
                    "trial_registry_id": "NCT05027997",
                    "disease": disease or "Blepharospasm, Dystonia",
                    "therapeutic_area": ["Neurological or sensory"],
                    "digital_endpoint": "Skintronics wearable blinking activity",
                    "concept_of_interest": ["Neurological or sensory"],
                    "sensor_or_dht": sensor or "Wearable",
                    "sponsor": "Example sponsor",
                    "endpoint_positioning": "Primary",
                    "validation_status": "not_reported_in_public_view",
                    "source": "dime",
                    "source_url": (
                        "https://dimesociety.org/library-of-digital-endpoints/"
                    ),
                    "terms_of_use_url": "https://dimesociety.org/terms-of-use/",
                },
            ],
            fetched_records=1,
            snapshot_date="2026-04",
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


def _airtable_payload() -> JSONObject:
    return {
        "data": {
            "table": {
                "columns": [
                    {"id": "endpoint", "name": "Endpoint identifier"},
                    {"id": "trial", "name": "Trial identifier"},
                    {
                        "id": "description",
                        "name": "Endpoint description (per trial registration record)",
                    },
                    {
                        "id": "concept",
                        "name": "Health concept/s",
                        "typeOptions": {
                            "choices": {
                                "neuro": {"name": "Neurological or sensory"},
                            },
                        },
                    },
                    {
                        "id": "technology",
                        "name": "Technology type",
                        "typeOptions": {
                            "choices": {"wearable": {"name": "Wearable"}},
                        },
                    },
                    {"id": "condition", "name": "Condition/s"},
                    {
                        "id": "category",
                        "name": "Condition/s category",
                        "typeOptions": {
                            "choices": {
                                "neuro": {"name": "Neurological or sensory"},
                            },
                        },
                    },
                    {"id": "sponsor", "name": "Industry sponsor or collaborator"},
                    {"id": "position", "name": "Endpoint positioning"},
                    {"id": "phase", "name": "Trial phase"},
                    {"id": "registration", "name": "Date of Trial Registration"},
                    {"id": "record", "name": "Trial Registration Record"},
                ],
            },
            "rowsById": {
                "rec1": {
                    "cellValuesByColumnId": {
                        "endpoint": "3",
                        "trial": "NCT05027997",
                        "description": "Skintronics wearable blinking activity",
                        "concept": ["neuro"],
                        "technology": "wearable",
                        "condition": "Blepharospasm, Dystonia",
                        "category": ["neuro"],
                        "sponsor": "Example sponsor",
                        "position": "Primary",
                        "phase": ["Phase 2"],
                        "registration": "2021-08-01",
                        "record": "https://clinicaltrials.gov/study/NCT05027997",
                    },
                },
            },
        },
    }


def test_dime_request_requires_bounded_query_shape() -> None:
    request = DiMeSourceSearchRequest.model_validate(
        {"disease": " Dystonia ", "sensor": " wearable "},
    )

    assert request.disease == "Dystonia"
    assert request.sensor == "wearable"
    assert request.query_text() == "disease:Dystonia sensor:wearable"

    with pytest.raises(ValidationError, match="Provide at least one"):
        DiMeSourceSearchRequest.model_validate({})


def test_dime_methodological_reference_is_patient_meaningfulness_framework() -> None:
    reference = dime_methodological_reference()

    assert reference["pmid"] == "33083687"
    assert reference["pmcid"] == "PMC7548919"
    assert reference["doi"] == "10.1159/000509725"
    assert reference["framework_levels"] == [
        "Meaningful Aspect of Health (MAH)",
        "Concept of Interest (COI)",
        "Outcome to be measured",
        "Endpoint",
    ]


@pytest.mark.asyncio
async def test_dime_public_gateway_maps_public_airtable_catalog_metadata() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/embed/"):
            return httpx.Response(
                200,
                text='window.bootstrap = {urlWithParams: "/v0.3/view/search"};',
                request=request,
            )
        if request.url.path == "/v0.3/view/search":
            assert request.headers["x-time-zone"] == "UTC"
            return httpx.Response(
                200,
                json=_airtable_payload(),
                request=request,
            )
        return httpx.Response(404, request=request)

    gateway = DiMePublicCatalogGateway(transport=httpx.MockTransport(handler))

    result = await gateway.fetch_records_async(
        disease="dystonia",
        sensor="wearable",
        max_results=1,
    )

    assert result.fetched_records == 1
    assert result.snapshot_date == "2026-04"
    assert result.records[0]["trial_registry_id"] == "NCT05027997"
    assert result.records[0]["therapeutic_area"] == ["Neurological or sensory"]
    assert result.records[0]["sensor_or_dht"] == "Wearable"
    assert result.records[0]["validation_status"] == "not_reported_in_public_view"


@pytest.mark.asyncio
async def test_dime_direct_search_captures_terms_and_method_reference() -> None:
    space_id = uuid4()
    owner_id = uuid4()

    result = await run_dime_direct_search(
        space_id=space_id,
        created_by=owner_id,
        request=DiMeSourceSearchRequest(
            disease="dystonia",
            sensor="wearable",
            max_results=2,
        ),
        gateway=_StubDiMeGateway(),
        store=InMemoryDirectSourceSearchStore(),
    )

    assert result.space_id == space_id
    assert result.source_key == "dime"
    assert result.query == "disease:dystonia sensor:wearable"
    assert result.snapshot_date == "2026-04"
    assert result.record_count == 1
    assert result.records[0]["trial_registry_id"] == "NCT05027997"
    assert result.methodological_reference["pmid"] == "33083687"
    assert result.source_capture.source_key == "dime"
    assert result.source_capture.external_id == "NCT05027997"
    assert result.source_capture.provenance["terms_of_use_url"] == (
        "https://dimesociety.org/terms-of-use/"
    )


@pytest.mark.asyncio
async def test_dime_plugin_plans_runs_and_normalizes_records() -> None:
    plugin = DiMeSourcePlugin(gateway_factory=lambda: _StubDiMeGateway())

    payload = plugin.build_query_payload(
        _Intent(source_key="dime", disease="MED13 syndrome"),
    )

    assert payload == {"disease": "MED13 syndrome"}

    result = await plugin.run_direct_search(
        context=SourceSearchExecutionContext(
            space_id=UUID("22222222-2222-2222-2222-222222222222"),
            created_by=UUID("11111111-1111-1111-1111-111111111111"),
            store=InMemoryDirectSourceSearchStore(),
        ),
        search=_SearchInput(
            source_key="dime",
            query_payload={"disease": "dystonia", "sensor": "wearable"},
        ),
    )

    context = plugin.build_candidate_context(result.records[0]).to_json()
    assert context["source_key"] == "dime"
    assert context["source_family"] == "digital_measurement"
    assert context["provider_external_id"] == "NCT05027997"
    assert context["normalized_record"]["trial_registry_id"] == "NCT05027997"
    assert context["normalized_record"]["sensor_or_dht"] == "wearable"


@pytest.mark.asyncio
async def test_dime_plugin_requires_available_gateway() -> None:
    plugin = DiMeSourcePlugin(gateway_factory=lambda: None)

    with pytest.raises(EvidenceSelectionSourceSearchError, match="DiMe gateway"):
        await plugin.run_direct_search(
            context=SourceSearchExecutionContext(
                space_id=uuid4(),
                created_by=uuid4(),
                store=InMemoryDirectSourceSearchStore(),
            ),
            search=_SearchInput(source_key="dime", query_payload={"query": "sleep"}),
        )
