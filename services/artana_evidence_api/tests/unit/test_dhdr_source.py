"""Tests for the DBDP DHDR digital-health dataset source connector."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import httpx
import pytest
from artana_evidence_api.direct_source_search import InMemoryDirectSourceSearchStore
from artana_evidence_api.direct_sources.dhdr import (
    DHDRCatalogGateway,
    DHDRGatewayFetchResult,
    DHDRSourceSearchRequest,
    run_dhdr_direct_search,
)
from artana_evidence_api.source_plugins.contracts import (
    EvidenceSelectionSourceSearchError,
    SourceSearchExecutionContext,
)
from artana_evidence_api.source_plugins.digital_health.dhdr import DHDRSourcePlugin
from artana_evidence_api.types.common import JSONObject
from pydantic import ValidationError


class _StubDHDRGateway:
    async def fetch_records_async(
        self,
        *,
        query: str | None = None,
        condition: str | None = None,
        modality: str | None = None,
        device: str | None = None,
        max_results: int = 20,
    ) -> DHDRGatewayFetchResult:
        del query, max_results
        return DHDRGatewayFetchResult(
            records=[
                {
                    "dataset_name": "WearGait-PD",
                    "condition": condition or "Parkinson's disease",
                    "modalities": [modality or "IMU"],
                    "devices": [device or "sensorized insole"],
                    "cohort_size": "100 individuals with Parkinson's disease",
                    "host_platform": "Synapse",
                    "dataset_url": "https://www.synapse.org/Synapse:syn52540892/wiki/623751",
                    "license": "host-specific; review dataset terms before reuse",
                    "terms_url": "https://www.synapse.org/Synapse:syn52540892/wiki/623751",
                    "description": "Wearables gait dataset for Parkinson's disease.",
                    "source": "dhdr",
                },
            ],
            fetched_records=1,
            snapshot_date="2026-05-04",
            catalog_url="https://www.dbdp.org/dhdr",
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


def _dhdr_page_html() -> str:
    return """
    <!DOCTYPE html><!-- Last Published: Mon May 04 2026 14:01:24 GMT+0000 (Coordinated Universal Time) -->
    <div role="listitem" class="w-dyn-item">
      <h6 fs-cmsfilter-field="project_title">Wearables for gait in Parkinson's Disease and age-matched controls (WearGait-PD)</h6>
      <div fs-cmsfilter-field="modules" class="job-category">IMU</div>
      <div class="text-block-8">This open-access wearables dataset contains synchronized raw IMU and sensorized insole data from 100 individuals with Parkinson's disease and 85 age-matched controls.</div>
      <a href="https://www.synapse.org/Synapse:syn52540892/wiki/623751" class="link-block w-inline-block">Learn More</a>
    </div>
    <div role="listitem" class="w-dyn-item">
      <h6 fs-cmsfilter-field="project_title">AdolescentsSchizophrenia</h6>
      <div fs-cmsfilter-field="modules" class="job-category">EEG</div>
      <div class="text-block-8">The subjects were adolescents divided into healthy (n = 39) and symptoms of schizophrenia (n = 45) groups.</div>
      <a href="http://brain.bio.msu.ru/eeg_schizophrenia.htm" class="link-block w-inline-block">Learn More</a>
    </div>
    """


def test_dhdr_request_requires_bounded_query_shape() -> None:
    request = DHDRSourceSearchRequest.model_validate(
        {"condition": " Parkinson ", "modality": " IMU "},
    )

    assert request.condition == "Parkinson"
    assert request.modality == "IMU"
    assert request.query_text() == "condition:Parkinson modality:IMU"

    with pytest.raises(ValidationError, match="Provide at least one"):
        DHDRSourceSearchRequest.model_validate({})


@pytest.mark.asyncio
async def test_dhdr_gateway_parses_public_catalog_cards_and_caches_results() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(200, text=_dhdr_page_html(), request=request)

    gateway = DHDRCatalogGateway(transport=httpx.MockTransport(handler))

    result = await gateway.fetch_records_async(
        condition="Parkinson",
        modality="IMU",
        max_results=1,
    )
    cached_result = await gateway.fetch_records_async(condition="schizophrenia")

    assert requests == ["https://www.dbdp.org/dhdr"]
    assert result.fetched_records == 1
    assert result.snapshot_date == "2026-05-04"
    assert result.records[0]["dataset_name"] == "WearGait-PD"
    assert result.records[0]["condition"] == "Parkinson's disease"
    assert result.records[0]["modalities"] == ["IMU"]
    assert result.records[0]["devices"] == ["sensorized insole"]
    assert result.records[0]["host_platform"] == "Synapse"
    assert result.records[0]["terms_url"] == (
        "https://www.synapse.org/Synapse:syn52540892/wiki/623751"
    )
    assert cached_result.records[0]["dataset_name"] == "AdolescentsSchizophrenia"


@pytest.mark.asyncio
async def test_dhdr_direct_search_captures_dataset_terms_and_metadata_scope() -> None:
    space_id = uuid4()
    owner_id = uuid4()

    result = await run_dhdr_direct_search(
        space_id=space_id,
        created_by=owner_id,
        request=DHDRSourceSearchRequest(
            condition="Parkinson",
            modality="IMU",
            max_results=2,
        ),
        gateway=_StubDHDRGateway(),
        store=InMemoryDirectSourceSearchStore(),
    )

    assert result.space_id == space_id
    assert result.source_key == "dhdr"
    assert result.query == "condition:Parkinson modality:IMU"
    assert result.snapshot_date == "2026-05-04"
    assert result.record_count == 1
    assert result.records[0]["dataset_name"] == "WearGait-PD"
    assert result.source_capture.source_key == "dhdr"
    assert result.source_capture.external_id == "WearGait-PD"
    assert result.source_capture.provenance["content_scope"] == (
        "metadata_only_no_raw_sensor_data"
    )
    assert result.source_capture.provenance["license_policy"] == (
        "per_dataset_terms_required"
    )


@pytest.mark.asyncio
async def test_dhdr_plugin_plans_runs_and_normalizes_records() -> None:
    plugin = DHDRSourcePlugin(gateway_factory=lambda: _StubDHDRGateway())

    payload = plugin.build_query_payload(
        _Intent(source_key="dhdr", disease="Parkinson disease"),
    )

    assert payload == {"condition": "Parkinson disease"}

    result = await plugin.run_direct_search(
        context=SourceSearchExecutionContext(
            space_id=UUID("22222222-2222-2222-2222-222222222222"),
            created_by=UUID("11111111-1111-1111-1111-111111111111"),
            store=InMemoryDirectSourceSearchStore(),
        ),
        search=_SearchInput(
            source_key="dhdr",
            query_payload={"condition": "Parkinson", "modality": "IMU"},
        ),
    )

    context = plugin.build_candidate_context(result.records[0]).to_json()
    assert context["source_key"] == "dhdr"
    assert context["source_family"] == "digital_biomarker_dataset"
    assert context["provider_external_id"] == "WearGait-PD"
    assert context["normalized_record"]["dataset_name"] == "WearGait-PD"
    assert context["normalized_record"]["host_platform"] == "Synapse"


@pytest.mark.asyncio
async def test_dhdr_plugin_requires_available_gateway() -> None:
    plugin = DHDRSourcePlugin(gateway_factory=lambda: None)

    with pytest.raises(EvidenceSelectionSourceSearchError, match="DHDR gateway"):
        await plugin.run_direct_search(
            context=SourceSearchExecutionContext(
                space_id=uuid4(),
                created_by=uuid4(),
                store=InMemoryDirectSourceSearchStore(),
            ),
            search=_SearchInput(source_key="dhdr", query_payload={"query": "sleep"}),
        )
