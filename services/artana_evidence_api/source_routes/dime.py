"""DiMe typed public direct-source routes."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from artana_evidence_api.auth import HarnessUser, get_current_harness_user
from artana_evidence_api.dependencies import (
    get_dime_source_gateway,
    get_direct_source_search_store,
    require_harness_space_read_access,
    require_harness_space_write_access,
)
from artana_evidence_api.direct_source_search import DirectSourceSearchStore
from artana_evidence_api.direct_sources.dime import (
    DiMeGatewayProtocol,
    DiMeSourceSearchRequest,
    DiMeSourceSearchResponse,
    run_dime_direct_search,
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
_DIME_SOURCE_GATEWAY_DEPENDENCY = Depends(get_dime_source_gateway)
_DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY = Depends(get_direct_source_search_store)


def dime_typed_route_plugin() -> DirectSourceRoutePlugin:
    """Return the typed public DiMe route plugin."""

    return DirectSourceRoutePlugin(
        source_key="dime",
        routes=(
            DirectSourceTypedRoute(
                path="/v2/spaces/{space_id}/sources/dime/searches",
                method="POST",
                endpoint=create_dime_source_search,
                response_model=DiMeSourceSearchResponse,
                status_code=status.HTTP_201_CREATED,
                summary="Search DiMe evidence source",
                dependencies=(Depends(require_harness_space_write_access),),
            ),
            DirectSourceTypedRoute(
                path="/v2/spaces/{space_id}/sources/dime/searches/{search_id}",
                method="GET",
                endpoint=get_dime_source_search,
                response_model=DiMeSourceSearchResponse,
                summary="Get DiMe evidence source search",
                dependencies=(Depends(require_harness_space_read_access),),
            ),
        ),
        create_payload=create_dime_route_payload,
        get_payload=get_dime_route_payload,
    )


async def create_dime_source_search(
    space_id: UUID,
    request: DiMeSourceSearchRequest,
    *,
    current_user: HarnessUser = _CURRENT_USER_DEPENDENCY,
    dime_gateway: DiMeGatewayProtocol | None = _DIME_SOURCE_GATEWAY_DEPENDENCY,
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 route for DiMe source search."""

    return await create_dime_source_search_payload(
        space_id=space_id,
        request=request,
        current_user=current_user,
        dime_gateway=dime_gateway,
        direct_source_search_store=direct_source_search_store,
    )


def get_dime_source_search(
    space_id: UUID,
    search_id: UUID,
    *,
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 route for DiMe source-search lookup."""

    return get_dime_source_search_payload(
        space_id=space_id,
        search_id=search_id,
        direct_source_search_store=direct_source_search_store,
    )


async def create_dime_source_search_payload(
    *,
    space_id: UUID,
    request: DiMeSourceSearchRequest,
    current_user: HarnessUser,
    dime_gateway: DiMeGatewayProtocol | None,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    """Create a DiMe direct-source search response."""

    gateway = require_gateway(
        dime_gateway,
        unavailable_detail="DiMe gateway is not available.",
    )
    try:
        result = await run_dime_direct_search(
            space_id=space_id,
            created_by=current_user.id,
            request=request,
            gateway=gateway,
            store=direct_source_search_store,
        )
    except RuntimeError as exc:
        raise gateway_unavailable(exc) from exc
    return source_result_payload(result)


def get_dime_source_search_payload(
    *,
    space_id: UUID,
    search_id: UUID,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    """Return a stored DiMe direct-source search response."""

    return stored_source_search_payload(
        space_id=space_id,
        source_key="dime",
        search_id=search_id,
        direct_source_search_store=direct_source_search_store,
    )


async def create_dime_route_payload(
    space_id: UUID,
    request_payload: JSONObject,
    dependencies: DirectSourceRouteDependencies,
) -> JSONObject:
    """Create a DiMe search from the generic route payload."""

    dime_gateway = cast(
        "DiMeGatewayProtocol | None",
        dependencies.source_dependency("dime"),
    )
    return await create_dime_source_search_payload(
        space_id=space_id,
        request=parse_source_search_payload(request_payload, DiMeSourceSearchRequest),
        current_user=dependencies.current_user,
        dime_gateway=dime_gateway,
        direct_source_search_store=dependencies.direct_source_search_store,
    )


def get_dime_route_payload(
    space_id: UUID,
    search_id: UUID,
    dependencies: DirectSourceRouteDependencies,
) -> JSONObject:
    """Return a DiMe search from the generic route lookup."""

    return get_dime_source_search_payload(
        space_id=space_id,
        search_id=search_id,
        direct_source_search_store=dependencies.direct_source_search_store,
    )


__all__ = [
    "create_dime_route_payload",
    "create_dime_source_search",
    "create_dime_source_search_payload",
    "dime_typed_route_plugin",
    "get_dime_route_payload",
    "get_dime_source_search",
    "get_dime_source_search_payload",
]
