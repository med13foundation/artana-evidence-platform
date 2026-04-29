"""MGI typed public direct-source routes."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from artana_evidence_api.auth import HarnessUser, get_current_harness_user
from artana_evidence_api.dependencies import (
    get_direct_source_search_store,
    get_mgi_source_gateway,
    require_harness_space_read_access,
    require_harness_space_write_access,
)
from artana_evidence_api.direct_source_search import (
    DirectSourceSearchStore,
    MGISourceSearchRequest,
    MGISourceSearchResponse,
    run_mgi_direct_search,
)
from artana_evidence_api.source_enrichment_bridges import AllianceGeneGatewayProtocol
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
_MGI_SOURCE_GATEWAY_DEPENDENCY = Depends(get_mgi_source_gateway)
_DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY = Depends(get_direct_source_search_store)


def mgi_typed_route_plugin() -> DirectSourceRoutePlugin:
    """Return the typed public MGI route plugin."""

    return DirectSourceRoutePlugin(
        source_key="mgi",
        routes=(
            DirectSourceTypedRoute(
                path="/v2/spaces/{space_id}/sources/mgi/searches",
                method="POST",
                endpoint=create_mgi_source_search,
                response_model=MGISourceSearchResponse,
                status_code=status.HTTP_201_CREATED,
                summary="Search MGI evidence source",
                dependencies=(Depends(require_harness_space_write_access),),
            ),
            DirectSourceTypedRoute(
                path="/v2/spaces/{space_id}/sources/mgi/searches/{search_id}",
                method="GET",
                endpoint=get_mgi_source_search,
                response_model=MGISourceSearchResponse,
                summary="Get MGI evidence source search",
                dependencies=(Depends(require_harness_space_read_access),),
            ),
        ),
        create_payload=create_mgi_route_payload,
        get_payload=get_mgi_route_payload,
    )


async def create_mgi_source_search(
    space_id: UUID,
    request: MGISourceSearchRequest,
    *,
    current_user: HarnessUser = _CURRENT_USER_DEPENDENCY,
    mgi_gateway: AllianceGeneGatewayProtocol | None = _MGI_SOURCE_GATEWAY_DEPENDENCY,
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 route for MGI source search."""

    return await create_mgi_source_search_payload(
        space_id=space_id,
        request=request,
        current_user=current_user,
        mgi_gateway=mgi_gateway,
        direct_source_search_store=direct_source_search_store,
    )


def get_mgi_source_search(
    space_id: UUID,
    search_id: UUID,
    *,
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 route for MGI source-search lookup."""

    return get_mgi_source_search_payload(
        space_id=space_id,
        search_id=search_id,
        direct_source_search_store=direct_source_search_store,
    )


async def create_mgi_source_search_payload(
    *,
    space_id: UUID,
    request: MGISourceSearchRequest,
    current_user: HarnessUser,
    mgi_gateway: AllianceGeneGatewayProtocol | None,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    """Create an MGI direct-source search response."""

    gateway = require_gateway(
        mgi_gateway,
        unavailable_detail="MGI gateway is not available.",
    )
    try:
        result = await run_mgi_direct_search(
            space_id=space_id,
            created_by=current_user.id,
            request=request,
            gateway=gateway,
            store=direct_source_search_store,
        )
    except RuntimeError as exc:
        raise gateway_unavailable(exc) from exc
    return source_result_payload(result)


def get_mgi_source_search_payload(
    *,
    space_id: UUID,
    search_id: UUID,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    """Return a stored MGI direct-source search response."""

    return stored_source_search_payload(
        space_id=space_id,
        source_key="mgi",
        search_id=search_id,
        direct_source_search_store=direct_source_search_store,
    )


async def create_mgi_route_payload(
    space_id: UUID,
    request_payload: JSONObject,
    dependencies: DirectSourceRouteDependencies,
) -> JSONObject:
    """Create an MGI search from the generic route payload."""

    mgi_gateway = cast(
        "AllianceGeneGatewayProtocol | None",
        dependencies.source_dependency("mgi"),
    )
    return await create_mgi_source_search_payload(
        space_id=space_id,
        request=parse_source_search_payload(request_payload, MGISourceSearchRequest),
        current_user=dependencies.current_user,
        mgi_gateway=mgi_gateway,
        direct_source_search_store=dependencies.direct_source_search_store,
    )


def get_mgi_route_payload(
    space_id: UUID,
    search_id: UUID,
    dependencies: DirectSourceRouteDependencies,
) -> JSONObject:
    """Return an MGI search from the generic route lookup."""

    return get_mgi_source_search_payload(
        space_id=space_id,
        search_id=search_id,
        direct_source_search_store=dependencies.direct_source_search_store,
    )


__all__ = [
    "create_mgi_route_payload",
    "create_mgi_source_search",
    "create_mgi_source_search_payload",
    "get_mgi_route_payload",
    "get_mgi_source_search",
    "get_mgi_source_search_payload",
    "mgi_typed_route_plugin",
]
