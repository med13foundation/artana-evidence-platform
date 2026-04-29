"""ClinicalTrials.gov typed public direct-source routes."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from artana_evidence_api.auth import HarnessUser, get_current_harness_user
from artana_evidence_api.dependencies import (
    get_clinicaltrials_source_gateway,
    get_direct_source_search_store,
    require_harness_space_read_access,
    require_harness_space_write_access,
)
from artana_evidence_api.direct_source_search import (
    ClinicalTrialsSourceSearchRequest,
    ClinicalTrialsSourceSearchResponse,
    DirectSourceSearchStore,
    run_clinicaltrials_direct_search,
)
from artana_evidence_api.source_enrichment_bridges import ClinicalTrialsGatewayProtocol
from artana_evidence_api.source_route_contracts import (
    DirectSourceRouteDependencies,
    DirectSourceRoutePlugin,
    DirectSourceTypedRoute,
)
from artana_evidence_api.source_route_helpers import (
    gateway_unavailable,
    parse_source_search_payload,
    require_gateway,
    source_result_payload,
    stored_source_search_payload,
)
from artana_evidence_api.types.common import JSONObject
from fastapi import Depends, status

_CURRENT_USER_DEPENDENCY = Depends(get_current_harness_user)
_CLINICALTRIALS_SOURCE_GATEWAY_DEPENDENCY = Depends(
    get_clinicaltrials_source_gateway,
)
_DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY = Depends(get_direct_source_search_store)


def clinical_trials_typed_route_plugin() -> DirectSourceRoutePlugin:
    """Return the typed public ClinicalTrials.gov route plugin."""

    return DirectSourceRoutePlugin(
        source_key="clinical_trials",
        routes=(
            DirectSourceTypedRoute(
                path="/v2/spaces/{space_id}/sources/clinical_trials/searches",
                method="POST",
                endpoint=create_clinicaltrials_source_search,
                response_model=ClinicalTrialsSourceSearchResponse,
                status_code=status.HTTP_201_CREATED,
                summary="Search ClinicalTrials.gov evidence source",
                dependencies=(Depends(require_harness_space_write_access),),
            ),
            DirectSourceTypedRoute(
                path="/v2/spaces/{space_id}/sources/clinical_trials/searches/{search_id}",
                method="GET",
                endpoint=get_clinicaltrials_source_search,
                response_model=ClinicalTrialsSourceSearchResponse,
                summary="Get ClinicalTrials.gov evidence source search",
                dependencies=(Depends(require_harness_space_read_access),),
            ),
        ),
        create_payload=create_clinicaltrials_route_payload,
        get_payload=get_clinicaltrials_route_payload,
    )


async def create_clinicaltrials_source_search(
    space_id: UUID,
    request: ClinicalTrialsSourceSearchRequest,
    *,
    current_user: HarnessUser = _CURRENT_USER_DEPENDENCY,
    clinicaltrials_gateway: ClinicalTrialsGatewayProtocol | None = (
        _CLINICALTRIALS_SOURCE_GATEWAY_DEPENDENCY
    ),
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 route for ClinicalTrials.gov source search."""

    return await create_clinicaltrials_source_search_payload(
        space_id=space_id,
        request=request,
        current_user=current_user,
        clinicaltrials_gateway=clinicaltrials_gateway,
        direct_source_search_store=direct_source_search_store,
    )


def get_clinicaltrials_source_search(
    space_id: UUID,
    search_id: UUID,
    *,
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 route for ClinicalTrials.gov source-search lookup."""

    return get_clinicaltrials_source_search_payload(
        space_id=space_id,
        search_id=search_id,
        direct_source_search_store=direct_source_search_store,
    )


async def create_clinicaltrials_source_search_payload(
    *,
    space_id: UUID,
    request: ClinicalTrialsSourceSearchRequest,
    current_user: HarnessUser,
    clinicaltrials_gateway: ClinicalTrialsGatewayProtocol | None,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    """Create a ClinicalTrials.gov direct-source search response."""

    gateway = require_gateway(
        clinicaltrials_gateway,
        unavailable_detail="ClinicalTrials.gov gateway is not available.",
    )
    try:
        result = await run_clinicaltrials_direct_search(
            space_id=space_id,
            created_by=current_user.id,
            request=request,
            gateway=gateway,
            store=direct_source_search_store,
        )
    except RuntimeError as exc:
        raise gateway_unavailable(exc) from exc
    return source_result_payload(result)


def get_clinicaltrials_source_search_payload(
    *,
    space_id: UUID,
    search_id: UUID,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    """Return a stored ClinicalTrials.gov direct-source search response."""

    return stored_source_search_payload(
        space_id=space_id,
        source_key="clinical_trials",
        search_id=search_id,
        direct_source_search_store=direct_source_search_store,
    )


async def create_clinicaltrials_route_payload(
    space_id: UUID,
    request_payload: JSONObject,
    dependencies: DirectSourceRouteDependencies,
) -> JSONObject:
    """Create a ClinicalTrials.gov search from the generic route payload."""

    clinicaltrials_gateway = cast(
        "ClinicalTrialsGatewayProtocol | None",
        dependencies.source_dependency("clinical_trials"),
    )
    return await create_clinicaltrials_source_search_payload(
        space_id=space_id,
        request=parse_source_search_payload(
            request_payload,
            ClinicalTrialsSourceSearchRequest,
        ),
        current_user=dependencies.current_user,
        clinicaltrials_gateway=clinicaltrials_gateway,
        direct_source_search_store=dependencies.direct_source_search_store,
    )


def get_clinicaltrials_route_payload(
    space_id: UUID,
    search_id: UUID,
    dependencies: DirectSourceRouteDependencies,
) -> JSONObject:
    """Return a ClinicalTrials.gov search from the generic route lookup."""

    return get_clinicaltrials_source_search_payload(
        space_id=space_id,
        search_id=search_id,
        direct_source_search_store=dependencies.direct_source_search_store,
    )


__all__ = [
    "clinical_trials_typed_route_plugin",
    "create_clinicaltrials_route_payload",
    "create_clinicaltrials_source_search",
    "create_clinicaltrials_source_search_payload",
    "get_clinicaltrials_route_payload",
    "get_clinicaltrials_source_search",
    "get_clinicaltrials_source_search_payload",
]
