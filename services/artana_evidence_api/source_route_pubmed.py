"""PubMed public direct-source route plugin."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from artana_evidence_api.auth import HarnessUser, get_current_harness_user
from artana_evidence_api.dependencies import (
    get_direct_source_search_store,
    get_pubmed_discovery_service,
    require_harness_space_read_access,
    require_harness_space_write_access,
)
from artana_evidence_api.direct_source_search import (
    DirectSourceSearchStore,
    PubMedSourceSearchResponse,
)
from artana_evidence_api.source_result_capture import (
    SourceCaptureStage,
    SourceResultCapture,
    compact_provenance,
    source_result_capture_metadata,
)
from artana_evidence_api.source_route_contracts import (
    DirectSourceRouteDependencies,
    DirectSourceRoutePlugin,
    DirectSourceTypedRoute,
)
from artana_evidence_api.source_route_helpers import parse_source_search_payload
from artana_evidence_api.types.common import (
    JSONObject,
    json_array_or_empty,
    json_object_or_empty,
)
from fastapi import Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder

from .routers import pubmed

_CURRENT_USER_DEPENDENCY = Depends(get_current_harness_user)
_PUBMED_DISCOVERY_SERVICE_DEPENDENCY = Depends(get_pubmed_discovery_service)
_DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY = Depends(get_direct_source_search_store)


def pubmed_typed_route_plugin() -> DirectSourceRoutePlugin:
    """Return the typed public PubMed route plugin."""

    return DirectSourceRoutePlugin(
        source_key="pubmed",
        routes=(
            DirectSourceTypedRoute(
                path="/v2/spaces/{space_id}/sources/pubmed/searches",
                method="POST",
                endpoint=create_pubmed_source_search,
                response_model=PubMedSourceSearchResponse | pubmed.DiscoverySearchJob,
                status_code=status.HTTP_201_CREATED,
                summary="Search PubMed evidence source",
                dependencies=(Depends(require_harness_space_write_access),),
            ),
            DirectSourceTypedRoute(
                path="/v2/spaces/{space_id}/sources/pubmed/searches/{job_id}",
                method="GET",
                endpoint=get_pubmed_source_search,
                response_model=PubMedSourceSearchResponse | pubmed.DiscoverySearchJob,
                summary="Get PubMed evidence source search",
                dependencies=(Depends(require_harness_space_read_access),),
            ),
        ),
        create_payload=create_pubmed_route_payload,
        get_payload=get_pubmed_route_payload,
    )


async def create_pubmed_source_search(
    space_id: UUID,
    request: pubmed.PubMedSearchRequest,
    *,
    current_user: HarnessUser = _CURRENT_USER_DEPENDENCY,
    pubmed_discovery_service: pubmed.PubMedDiscoveryService = (
        _PUBMED_DISCOVERY_SERVICE_DEPENDENCY
    ),
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 compatibility route for PubMed source search."""

    return await create_pubmed_source_search_payload(
        space_id=space_id,
        request=request,
        current_user=current_user,
        pubmed_discovery_service=pubmed_discovery_service,
        direct_source_search_store=direct_source_search_store,
    )


def get_pubmed_source_search(
    space_id: UUID,
    job_id: UUID,
    *,
    current_user: HarnessUser = _CURRENT_USER_DEPENDENCY,
    pubmed_discovery_service: pubmed.PubMedDiscoveryService = (
        _PUBMED_DISCOVERY_SERVICE_DEPENDENCY
    ),
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 compatibility route for PubMed source-search lookup."""

    return get_pubmed_source_search_payload(
        space_id=space_id,
        search_id=job_id,
        current_user=current_user,
        pubmed_discovery_service=pubmed_discovery_service,
        direct_source_search_store=direct_source_search_store,
    )


def _pubmed_source_capture(result: pubmed.DiscoverySearchJob) -> JSONObject:
    return source_result_capture_metadata(
        source_key="pubmed",
        capture_stage=SourceCaptureStage.SEARCH_RESULT,
        capture_method="direct_source_search",
        locator=f"pubmed:search:{result.id}",
        external_id=str(result.id),
        retrieved_at=result.completed_at or result.updated_at or result.created_at,
        search_id=str(result.id),
        query=result.query_preview,
        query_payload=result.parameters.model_dump(mode="json"),
        result_count=result.total_results,
        provenance=compact_provenance(
            provider=result.provider.value,
            status=result.status.value,
            storage_key=result.storage_key,
        ),
    )


def _pubmed_preview_records(result: pubmed.DiscoverySearchJob) -> list[JSONObject]:
    records = json_array_or_empty(result.result_metadata.get("preview_records"))
    return [json_object_or_empty(record) for record in records]


def _require_completed_pubmed_result(result: pubmed.DiscoverySearchJob) -> None:
    if result.status.value == "completed":
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "PubMed search job is not completed; durable direct-source handoff "
            "requires a completed PubMed result."
        ),
    )


def _pubmed_direct_source_record(
    *,
    space_id: UUID,
    result: pubmed.DiscoverySearchJob,
) -> PubMedSourceSearchResponse:
    _require_completed_pubmed_result(result)
    records = _pubmed_preview_records(result)
    completed_at = result.completed_at or result.updated_at or result.created_at
    source_capture = SourceResultCapture.model_validate(_pubmed_source_capture(result))
    return PubMedSourceSearchResponse(
        id=result.id,
        space_id=space_id,
        owner_id=result.owner_id,
        session_id=result.session_id,
        query=result.query_preview,
        query_preview=result.query_preview,
        parameters=result.parameters,
        total_results=result.total_results,
        result_metadata=result.result_metadata,
        record_count=len(records),
        records=records,
        error_message=result.error_message,
        storage_key=result.storage_key,
        created_at=result.created_at,
        updated_at=result.updated_at,
        completed_at=completed_at,
        source_capture=source_capture,
    )


async def create_pubmed_source_search_payload(
    *,
    space_id: UUID,
    request: pubmed.PubMedSearchRequest,
    current_user: HarnessUser,
    pubmed_discovery_service: pubmed.PubMedDiscoveryService,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    pubmed_result = await pubmed.create_pubmed_search(
        space_id=space_id,
        request=request,
        current_user=current_user,
        pubmed_discovery_service=pubmed_discovery_service,
    )
    if pubmed_result.status.value != "completed":
        return json_object_or_empty(jsonable_encoder(pubmed_result))
    durable_result = _pubmed_direct_source_record(
        space_id=space_id,
        result=pubmed_result,
    )
    return json_object_or_empty(
        jsonable_encoder(
            direct_source_search_store.save(
                durable_result,
                created_by=current_user.id,
            ),
        ),
    )


def get_pubmed_source_search_payload(
    *,
    space_id: UUID,
    search_id: UUID,
    current_user: HarnessUser,
    pubmed_discovery_service: pubmed.PubMedDiscoveryService | None,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    stored_result = direct_source_search_store.get(
        space_id=space_id,
        source_key="pubmed",
        search_id=search_id,
    )
    if isinstance(stored_result, PubMedSourceSearchResponse):
        return json_object_or_empty(jsonable_encoder(stored_result))
    if pubmed_discovery_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PubMed discovery service is not available.",
        )
    pubmed_result = pubmed.get_pubmed_search(
        space_id=space_id,
        job_id=search_id,
        current_user=current_user,
        pubmed_discovery_service=pubmed_discovery_service,
    )
    if pubmed_result.status.value != "completed":
        return json_object_or_empty(jsonable_encoder(pubmed_result))
    durable_result = _pubmed_direct_source_record(
        space_id=space_id,
        result=pubmed_result,
    )
    saved_result = direct_source_search_store.save(
        durable_result,
        created_by=current_user.id,
    )
    return json_object_or_empty(jsonable_encoder(saved_result))


async def create_pubmed_route_payload(
    space_id: UUID,
    request_payload: JSONObject,
    dependencies: DirectSourceRouteDependencies,
) -> JSONObject:
    """Create a PubMed search from the generic route payload."""

    request = parse_source_search_payload(request_payload, pubmed.PubMedSearchRequest)
    pubmed_discovery_service = cast(
        "pubmed.PubMedDiscoveryService | None",
        dependencies.source_dependency("pubmed"),
    )
    if pubmed_discovery_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PubMed discovery service is not available.",
        )
    return await create_pubmed_source_search_payload(
        space_id=space_id,
        request=request,
        current_user=dependencies.current_user,
        pubmed_discovery_service=pubmed_discovery_service,
        direct_source_search_store=dependencies.direct_source_search_store,
    )


def get_pubmed_route_payload(
    space_id: UUID,
    search_id: UUID,
    dependencies: DirectSourceRouteDependencies,
) -> JSONObject:
    """Return a PubMed search from the generic route lookup."""

    pubmed_discovery_service = cast(
        "pubmed.PubMedDiscoveryService | None",
        dependencies.source_dependency("pubmed"),
    )
    return get_pubmed_source_search_payload(
        space_id=space_id,
        search_id=search_id,
        current_user=dependencies.current_user,
        pubmed_discovery_service=pubmed_discovery_service,
        direct_source_search_store=dependencies.direct_source_search_store,
    )


__all__ = [
    "create_pubmed_source_search",
    "create_pubmed_route_payload",
    "create_pubmed_source_search_payload",
    "get_pubmed_source_search",
    "get_pubmed_route_payload",
    "get_pubmed_source_search_payload",
    "pubmed_typed_route_plugin",
]
