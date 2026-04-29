"""Unit tests for the public direct-source route plugin layer."""

from __future__ import annotations

from collections.abc import MutableMapping
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from artana_evidence_api.auth import (
    HarnessUser,
    HarnessUserRole,
    HarnessUserStatus,
)
from artana_evidence_api.direct_source_search import (
    InMemoryDirectSourceSearchStore,
    MarrvelSourceSearchResponse,
    PubMedSourceSearchResponse,
)
from artana_evidence_api.marrvel_discovery import MarrvelDiscoveryResult
from artana_evidence_api.pubmed_discovery import AdvancedQueryParameters
from artana_evidence_api.source_result_capture import (
    SourceCaptureStage,
    SourceResultCapture,
    source_result_capture_metadata,
)
from artana_evidence_api.source_route_contracts import (
    DirectSourceRouteDependencies,
)
from artana_evidence_api.source_route_dependencies import (
    direct_source_route_dependencies,
)
from artana_evidence_api.source_route_plugins import (
    DirectSourceRoutePluginRegistryError,
    create_direct_source_search_payload,
    direct_source_route_plugin_keys,
    direct_source_typed_route_endpoint_map,
    get_direct_source_search_payload,
    require_direct_source_route_plugin,
)
from fastapi import HTTPException, status

_USER_ID = UUID("11111111-1111-1111-1111-111111111111")
_SPACE_ID = UUID("22222222-2222-2222-2222-222222222222")


def _user() -> HarnessUser:
    return HarnessUser(
        id=_USER_ID,
        email="route-adapters@example.com",
        username="route-adapters",
        full_name="Route Adapters",
        role=HarnessUserRole.RESEARCHER,
        status=HarnessUserStatus.ACTIVE,
    )


def _capture(source_key: str, search_id: UUID, query: str) -> SourceResultCapture:
    now = datetime.now(UTC)
    return SourceResultCapture.model_validate(
        source_result_capture_metadata(
            source_key=source_key,
            capture_stage=SourceCaptureStage.SEARCH_RESULT,
            capture_method="direct_source_search",
            locator=f"{source_key}:search:{search_id}",
            retrieved_at=now,
            search_id=str(search_id),
            query=query,
            result_count=1,
        ),
    )


class _MarrvelResultLookup:
    def __init__(self, result: MarrvelDiscoveryResult) -> None:
        self._result = result

    def get_result(
        self,
        *,
        owner_id: UUID,
        result_id: UUID,
    ) -> MarrvelDiscoveryResult | None:
        if self._result.owner_id == owner_id and self._result.id == result_id:
            return self._result
        return None


def test_unknown_direct_source_route_plugin_raises_registry_error() -> None:
    with pytest.raises(DirectSourceRoutePluginRegistryError):
        require_direct_source_route_plugin("not_a_source")


def test_generic_route_dependency_keys_match_route_plugin_keys() -> None:
    dependencies = direct_source_route_dependencies(
        current_user=_user(),
        direct_source_search_store=InMemoryDirectSourceSearchStore(),
        pubmed_discovery_service=None,
        marrvel_discovery_service=None,
        clinvar_gateway=None,
        clinicaltrials_gateway=None,
        uniprot_gateway=None,
        alphafold_gateway=None,
        drugbank_gateway=None,
        mgi_gateway=None,
        zfin_gateway=None,
    )

    assert set(dependencies.source_dependencies) == set(direct_source_route_plugin_keys())


def test_typed_route_endpoint_map_is_read_only() -> None:
    endpoint_map = direct_source_typed_route_endpoint_map()
    route_key = next(iter(endpoint_map))
    mutable_endpoint_map = cast(
        "MutableMapping[tuple[str, str], object]",
        endpoint_map,
    )

    with pytest.raises(TypeError):
        mutable_endpoint_map[route_key] = endpoint_map[route_key]


def test_stored_pubmed_get_does_not_require_discovery_service() -> None:
    search_id = uuid4()
    now = datetime.now(UTC)
    store = InMemoryDirectSourceSearchStore()
    store.save(
        PubMedSourceSearchResponse(
            id=search_id,
            space_id=_SPACE_ID,
            owner_id=_USER_ID,
            query="MED13",
            query_preview="MED13",
            parameters=AdvancedQueryParameters(search_term="MED13"),
            total_results=1,
            result_metadata={"preview_records": [{"pmid": "12345678"}]},
            record_count=1,
            records=[{"pmid": "12345678"}],
            created_at=now,
            updated_at=now,
            completed_at=now,
            source_capture=_capture("pubmed", search_id, "MED13"),
        ),
        created_by=_USER_ID,
    )

    payload = get_direct_source_search_payload(
        source_key="pubmed",
        space_id=_SPACE_ID,
        search_id=search_id,
        dependencies=DirectSourceRouteDependencies(
            current_user=_user(),
            direct_source_search_store=store,
            source_dependencies={"pubmed": None},
        ),
    )

    assert payload["id"] == str(search_id)
    assert payload["source_key"] == "pubmed"


def test_stored_marrvel_get_does_not_require_discovery_service() -> None:
    search_id = uuid4()
    now = datetime.now(UTC)
    store = InMemoryDirectSourceSearchStore()
    store.save(
        MarrvelSourceSearchResponse(
            id=search_id,
            space_id=_SPACE_ID,
            query="BRCA1",
            query_mode="gene",
            query_value="BRCA1",
            gene_symbol="BRCA1",
            resolved_gene_symbol="BRCA1",
            taxon_id=9606,
            gene_found=True,
            omim_count=0,
            variant_count=1,
            panel_counts={"clinvar": 1},
            panels={"clinvar": [{"accession": "VCV000012345"}]},
            available_panels=["clinvar"],
            record_count=1,
            records=[{"marrvel_record_id": f"{search_id}:clinvar:0"}],
            created_at=now,
            completed_at=now,
            source_capture=_capture("marrvel", search_id, "BRCA1"),
        ),
        created_by=_USER_ID,
    )

    payload = get_direct_source_search_payload(
        source_key="marrvel",
        space_id=_SPACE_ID,
        search_id=search_id,
        dependencies=DirectSourceRouteDependencies(
            current_user=_user(),
            direct_source_search_store=store,
            source_dependencies={"marrvel": None},
        ),
    )

    assert payload["id"] == str(search_id)
    assert payload["source_key"] == "marrvel"


def test_marrvel_get_fallback_persists_rebuilt_durable_result() -> None:
    search_id = uuid4()
    store = InMemoryDirectSourceSearchStore()
    discovery_result = MarrvelDiscoveryResult(
        id=search_id,
        space_id=_SPACE_ID,
        owner_id=_USER_ID,
        query_mode="gene",
        query_value="BRCA1",
        gene_symbol="BRCA1",
        resolved_gene_symbol="BRCA1",
        resolved_variant=None,
        taxon_id=9606,
        status="completed",
        gene_found=True,
        gene_info={"symbol": "BRCA1", "entrezGeneId": 672},
        omim_count=1,
        variant_count=1,
        panel_counts={"omim": 1},
        panels={"omim": [{"phenotype": "Breast cancer"}]},
        available_panels=["omim"],
        created_at=datetime.now(UTC),
    )

    payload = get_direct_source_search_payload(
        source_key="marrvel",
        space_id=_SPACE_ID,
        search_id=search_id,
        dependencies=DirectSourceRouteDependencies(
            current_user=_user(),
            direct_source_search_store=store,
            source_dependencies={"marrvel": _MarrvelResultLookup(discovery_result)},
        ),
    )

    assert payload["id"] == str(search_id)
    stored_result = store.get(
        space_id=_SPACE_ID,
        source_key="marrvel",
        search_id=search_id,
    )
    assert isinstance(stored_result, MarrvelSourceSearchResponse)
    assert stored_result.id == search_id
    assert stored_result.space_id == _SPACE_ID
    assert stored_result.source_key == "marrvel"
    assert stored_result.query == "BRCA1"

    payload_from_store = get_direct_source_search_payload(
        source_key="marrvel",
        space_id=_SPACE_ID,
        search_id=search_id,
        dependencies=DirectSourceRouteDependencies(
            current_user=_user(),
            direct_source_search_store=store,
            source_dependencies={"marrvel": None},
        ),
    )

    assert payload_from_store == payload


def test_gateway_source_get_returns_404_for_missing_stored_result() -> None:
    with pytest.raises(HTTPException) as exc_info:
        get_direct_source_search_payload(
            source_key="clinvar",
            space_id=_SPACE_ID,
            search_id=uuid4(),
            dependencies=DirectSourceRouteDependencies(
                current_user=_user(),
                direct_source_search_store=InMemoryDirectSourceSearchStore(),
            ),
        )

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc_info.value.detail == "Source search was not found for this space and source."


@pytest.mark.asyncio
async def test_generic_create_validates_request_before_gateway_availability() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await create_direct_source_search_payload(
            source_key="clinvar",
            space_id=_SPACE_ID,
            request_payload={"gene_symbol": "   "},
            dependencies=DirectSourceRouteDependencies(
                current_user=_user(),
                direct_source_search_store=InMemoryDirectSourceSearchStore(),
                source_dependencies={"clinvar": None},
            ),
        )

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert "gene_symbol must not be empty" in str(exc_info.value.detail)
