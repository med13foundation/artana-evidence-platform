"""Monarch KG typed public direct-source routes."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from artana_evidence_api.auth import HarnessUser, get_current_harness_user
from artana_evidence_api.dependencies import (
    get_direct_source_search_store,
    get_monarch_source_gateway,
    require_harness_space_read_access,
    require_harness_space_write_access,
)
from artana_evidence_api.direct_source_search import (
    DirectSourceSearchStore,
    MonarchSourceSearchRequest,
    MonarchSourceSearchResponse,
    run_monarch_direct_search,
)
from artana_evidence_api.direct_sources.monarch import MonarchGatewayProtocol
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
_MONARCH_SOURCE_GATEWAY_DEPENDENCY = Depends(get_monarch_source_gateway)
_DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY = Depends(get_direct_source_search_store)


def monarch_typed_route_plugin() -> DirectSourceRoutePlugin:
    """Return the typed public Monarch KG route plugin."""

    return DirectSourceRoutePlugin(
        source_key="monarch",
        routes=(
            DirectSourceTypedRoute(
                path="/v2/spaces/{space_id}/sources/monarch/searches",
                method="POST",
                endpoint=create_monarch_source_search,
                response_model=MonarchSourceSearchResponse,
                status_code=status.HTTP_201_CREATED,
                summary="Search Monarch KG evidence source",
                dependencies=(Depends(require_harness_space_write_access),),
            ),
            DirectSourceTypedRoute(
                path="/v2/spaces/{space_id}/sources/monarch/searches/{search_id}",
                method="GET",
                endpoint=get_monarch_source_search,
                response_model=MonarchSourceSearchResponse,
                summary="Get Monarch KG evidence source search",
                dependencies=(Depends(require_harness_space_read_access),),
            ),
        ),
        create_payload=create_monarch_route_payload,
        get_payload=get_monarch_route_payload,
    )


async def create_monarch_source_search(
    space_id: UUID,
    request: MonarchSourceSearchRequest,
    *,
    current_user: HarnessUser = _CURRENT_USER_DEPENDENCY,
    monarch_gateway: MonarchGatewayProtocol | None = _MONARCH_SOURCE_GATEWAY_DEPENDENCY,
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 route for Monarch source search."""

    return await create_monarch_source_search_payload(
        space_id=space_id,
        request=request,
        current_user=current_user,
        monarch_gateway=monarch_gateway,
        direct_source_search_store=direct_source_search_store,
    )


def get_monarch_source_search(
    space_id: UUID,
    search_id: UUID,
    *,
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 route for Monarch source-search lookup."""

    return get_monarch_source_search_payload(
        space_id=space_id,
        search_id=search_id,
        direct_source_search_store=direct_source_search_store,
    )


async def create_monarch_source_search_payload(
    *,
    space_id: UUID,
    request: MonarchSourceSearchRequest,
    current_user: HarnessUser,
    monarch_gateway: MonarchGatewayProtocol | None,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    """Create a Monarch direct-source search response."""

    gateway = require_gateway(
        monarch_gateway,
        unavailable_detail="Monarch KG gateway is not available.",
    )
    try:
        result = await run_monarch_direct_search(
            space_id=space_id,
            created_by=current_user.id,
            request=request,
            gateway=gateway,
            store=direct_source_search_store,
        )
    except RuntimeError as exc:
        raise gateway_unavailable(exc) from exc
    return source_result_payload(result)


def get_monarch_source_search_payload(
    *,
    space_id: UUID,
    search_id: UUID,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    """Return a stored Monarch direct-source search response."""

    return stored_source_search_payload(
        space_id=space_id,
        source_key="monarch",
        search_id=search_id,
        direct_source_search_store=direct_source_search_store,
    )


async def create_monarch_route_payload(
    space_id: UUID,
    request_payload: JSONObject,
    dependencies: DirectSourceRouteDependencies,
) -> JSONObject:
    """Create a Monarch search from the generic route payload."""

    monarch_gateway = cast(
        "MonarchGatewayProtocol | None",
        dependencies.source_dependency("monarch"),
    )
    return await create_monarch_source_search_payload(
        space_id=space_id,
        request=parse_source_search_payload(
            request_payload, MonarchSourceSearchRequest
        ),
        current_user=dependencies.current_user,
        monarch_gateway=monarch_gateway,
        direct_source_search_store=dependencies.direct_source_search_store,
    )


def get_monarch_route_payload(
    space_id: UUID,
    search_id: UUID,
    dependencies: DirectSourceRouteDependencies,
) -> JSONObject:
    """Return a Monarch search from the generic route lookup."""

    return get_monarch_source_search_payload(
        space_id=space_id,
        search_id=search_id,
        direct_source_search_store=dependencies.direct_source_search_store,
    )


__all__ = [
    "create_monarch_route_payload",
    "create_monarch_source_search",
    "create_monarch_source_search_payload",
    "get_monarch_route_payload",
    "get_monarch_source_search",
    "get_monarch_source_search_payload",
    "monarch_typed_route_plugin",
]
