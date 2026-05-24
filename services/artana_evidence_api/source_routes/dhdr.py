"""DHDR typed public direct-source routes."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from artana_evidence_api.auth import HarnessUser, get_current_harness_user
from artana_evidence_api.dependencies import (
    get_dhdr_source_gateway,
    get_direct_source_search_store,
    require_harness_space_read_access,
    require_harness_space_write_access,
)
from artana_evidence_api.direct_source_search import DirectSourceSearchStore
from artana_evidence_api.direct_sources.dhdr import (
    DHDRGatewayProtocol,
    DHDRSourceSearchRequest,
    DHDRSourceSearchResponse,
    run_dhdr_direct_search,
)
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
_DHDR_SOURCE_GATEWAY_DEPENDENCY = Depends(get_dhdr_source_gateway)
_DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY = Depends(get_direct_source_search_store)


def dhdr_typed_route_plugin() -> DirectSourceRoutePlugin:
    """Return the typed public DHDR route plugin."""

    return DirectSourceRoutePlugin(
        source_key="dhdr",
        routes=(
            DirectSourceTypedRoute(
                path="/v2/spaces/{space_id}/sources/dhdr/searches",
                method="POST",
                endpoint=create_dhdr_source_search,
                response_model=DHDRSourceSearchResponse,
                status_code=status.HTTP_201_CREATED,
                summary="Search DHDR evidence source",
                dependencies=(Depends(require_harness_space_write_access),),
            ),
            DirectSourceTypedRoute(
                path="/v2/spaces/{space_id}/sources/dhdr/searches/{search_id}",
                method="GET",
                endpoint=get_dhdr_source_search,
                response_model=DHDRSourceSearchResponse,
                summary="Get DHDR evidence source search",
                dependencies=(Depends(require_harness_space_read_access),),
            ),
        ),
        create_payload=create_dhdr_route_payload,
        get_payload=get_dhdr_route_payload,
    )


async def create_dhdr_source_search(
    space_id: UUID,
    request: DHDRSourceSearchRequest,
    *,
    current_user: HarnessUser = _CURRENT_USER_DEPENDENCY,
    dhdr_gateway: DHDRGatewayProtocol | None = _DHDR_SOURCE_GATEWAY_DEPENDENCY,
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 route for DHDR source search."""

    return await create_dhdr_source_search_payload(
        space_id=space_id,
        request=request,
        current_user=current_user,
        dhdr_gateway=dhdr_gateway,
        direct_source_search_store=direct_source_search_store,
    )


def get_dhdr_source_search(
    space_id: UUID,
    search_id: UUID,
    *,
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 route for DHDR source-search lookup."""

    return get_dhdr_source_search_payload(
        space_id=space_id,
        search_id=search_id,
        direct_source_search_store=direct_source_search_store,
    )


async def create_dhdr_source_search_payload(
    *,
    space_id: UUID,
    request: DHDRSourceSearchRequest,
    current_user: HarnessUser,
    dhdr_gateway: DHDRGatewayProtocol | None,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    """Create a DHDR direct-source search response."""

    gateway = require_gateway(
        dhdr_gateway,
        unavailable_detail="DHDR gateway is not available.",
    )
    try:
        result = await run_dhdr_direct_search(
            space_id=space_id,
            created_by=current_user.id,
            request=request,
            gateway=gateway,
            store=direct_source_search_store,
        )
    except RuntimeError as exc:
        raise gateway_unavailable(exc) from exc
    return source_result_payload(result)


def get_dhdr_source_search_payload(
    *,
    space_id: UUID,
    search_id: UUID,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    """Return a stored DHDR direct-source search response."""

    return stored_source_search_payload(
        space_id=space_id,
        source_key="dhdr",
        search_id=search_id,
        direct_source_search_store=direct_source_search_store,
    )


async def create_dhdr_route_payload(
    space_id: UUID,
    request_payload: JSONObject,
    dependencies: DirectSourceRouteDependencies,
) -> JSONObject:
    """Create a DHDR search from the generic route payload."""

    dhdr_gateway = cast(
        "DHDRGatewayProtocol | None",
        dependencies.source_dependency("dhdr"),
    )
    return await create_dhdr_source_search_payload(
        space_id=space_id,
        request=parse_source_search_payload(request_payload, DHDRSourceSearchRequest),
        current_user=dependencies.current_user,
        dhdr_gateway=dhdr_gateway,
        direct_source_search_store=dependencies.direct_source_search_store,
    )


def get_dhdr_route_payload(
    space_id: UUID,
    search_id: UUID,
    dependencies: DirectSourceRouteDependencies,
) -> JSONObject:
    """Return a DHDR search from the generic route lookup."""

    return get_dhdr_source_search_payload(
        space_id=space_id,
        search_id=search_id,
        direct_source_search_store=dependencies.direct_source_search_store,
    )


__all__ = [
    "create_dhdr_route_payload",
    "create_dhdr_source_search",
    "create_dhdr_source_search_payload",
    "dhdr_typed_route_plugin",
    "get_dhdr_route_payload",
    "get_dhdr_source_search",
    "get_dhdr_source_search_payload",
]
