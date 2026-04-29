"""AlphaFold typed public direct-source routes."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from artana_evidence_api.auth import HarnessUser, get_current_harness_user
from artana_evidence_api.dependencies import (
    get_alphafold_source_gateway,
    get_direct_source_search_store,
    require_harness_space_read_access,
    require_harness_space_write_access,
)
from artana_evidence_api.direct_source_search import (
    AlphaFoldSourceSearchRequest,
    AlphaFoldSourceSearchResponse,
    DirectSourceSearchStore,
    run_alphafold_direct_search,
)
from artana_evidence_api.source_enrichment_bridges import AlphaFoldGatewayProtocol
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
_ALPHAFOLD_SOURCE_GATEWAY_DEPENDENCY = Depends(get_alphafold_source_gateway)
_DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY = Depends(get_direct_source_search_store)


def alphafold_typed_route_plugin() -> DirectSourceRoutePlugin:
    """Return the typed public AlphaFold route plugin."""

    return DirectSourceRoutePlugin(
        source_key="alphafold",
        routes=(
            DirectSourceTypedRoute(
                path="/v2/spaces/{space_id}/sources/alphafold/searches",
                method="POST",
                endpoint=create_alphafold_source_search,
                response_model=AlphaFoldSourceSearchResponse,
                status_code=status.HTTP_201_CREATED,
                summary="Search AlphaFold evidence source",
                dependencies=(Depends(require_harness_space_write_access),),
            ),
            DirectSourceTypedRoute(
                path="/v2/spaces/{space_id}/sources/alphafold/searches/{search_id}",
                method="GET",
                endpoint=get_alphafold_source_search,
                response_model=AlphaFoldSourceSearchResponse,
                summary="Get AlphaFold evidence source search",
                dependencies=(Depends(require_harness_space_read_access),),
            ),
        ),
        create_payload=create_alphafold_route_payload,
        get_payload=get_alphafold_route_payload,
    )


async def create_alphafold_source_search(
    space_id: UUID,
    request: AlphaFoldSourceSearchRequest,
    *,
    current_user: HarnessUser = _CURRENT_USER_DEPENDENCY,
    alphafold_gateway: AlphaFoldGatewayProtocol | None = (
        _ALPHAFOLD_SOURCE_GATEWAY_DEPENDENCY
    ),
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 route for AlphaFold source search."""

    return await create_alphafold_source_search_payload(
        space_id=space_id,
        request=request,
        current_user=current_user,
        alphafold_gateway=alphafold_gateway,
        direct_source_search_store=direct_source_search_store,
    )


def get_alphafold_source_search(
    space_id: UUID,
    search_id: UUID,
    *,
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 route for AlphaFold source-search lookup."""

    return get_alphafold_source_search_payload(
        space_id=space_id,
        search_id=search_id,
        direct_source_search_store=direct_source_search_store,
    )


async def create_alphafold_source_search_payload(
    *,
    space_id: UUID,
    request: AlphaFoldSourceSearchRequest,
    current_user: HarnessUser,
    alphafold_gateway: AlphaFoldGatewayProtocol | None,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    """Create an AlphaFold direct-source search response."""

    gateway = require_gateway(
        alphafold_gateway,
        unavailable_detail="AlphaFold gateway is not available.",
    )
    try:
        result = await run_alphafold_direct_search(
            space_id=space_id,
            created_by=current_user.id,
            request=request,
            gateway=gateway,
            store=direct_source_search_store,
        )
    except RuntimeError as exc:
        raise gateway_unavailable(exc) from exc
    return source_result_payload(result)


def get_alphafold_source_search_payload(
    *,
    space_id: UUID,
    search_id: UUID,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    """Return a stored AlphaFold direct-source search response."""

    return stored_source_search_payload(
        space_id=space_id,
        source_key="alphafold",
        search_id=search_id,
        direct_source_search_store=direct_source_search_store,
    )


async def create_alphafold_route_payload(
    space_id: UUID,
    request_payload: JSONObject,
    dependencies: DirectSourceRouteDependencies,
) -> JSONObject:
    """Create an AlphaFold search from the generic route payload."""

    alphafold_gateway = cast(
        "AlphaFoldGatewayProtocol | None",
        dependencies.source_dependency("alphafold"),
    )
    return await create_alphafold_source_search_payload(
        space_id=space_id,
        request=parse_source_search_payload(
            request_payload,
            AlphaFoldSourceSearchRequest,
        ),
        current_user=dependencies.current_user,
        alphafold_gateway=alphafold_gateway,
        direct_source_search_store=dependencies.direct_source_search_store,
    )


def get_alphafold_route_payload(
    space_id: UUID,
    search_id: UUID,
    dependencies: DirectSourceRouteDependencies,
) -> JSONObject:
    """Return an AlphaFold search from the generic route lookup."""

    return get_alphafold_source_search_payload(
        space_id=space_id,
        search_id=search_id,
        direct_source_search_store=dependencies.direct_source_search_store,
    )


__all__ = [
    "alphafold_typed_route_plugin",
    "create_alphafold_route_payload",
    "create_alphafold_source_search",
    "create_alphafold_source_search_payload",
    "get_alphafold_route_payload",
    "get_alphafold_source_search",
    "get_alphafold_source_search_payload",
]
