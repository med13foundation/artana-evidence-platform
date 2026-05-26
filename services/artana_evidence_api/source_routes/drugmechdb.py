"""DrugMechDB typed public direct-source routes."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from artana_evidence_api.auth import HarnessUser, get_current_harness_user
from artana_evidence_api.dependencies import (
    get_direct_source_search_store,
    get_drugmechdb_source_gateway,
    require_harness_space_read_access,
    require_harness_space_write_access,
)
from artana_evidence_api.direct_source_search import DirectSourceSearchStore
from artana_evidence_api.direct_sources.drugmechdb import (
    DrugMechDBGatewayProtocol,
    DrugMechDBSourceSearchRequest,
    DrugMechDBSourceSearchResponse,
    run_drugmechdb_direct_search,
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
_DRUGMECHDB_SOURCE_GATEWAY_DEPENDENCY = Depends(get_drugmechdb_source_gateway)
_DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY = Depends(get_direct_source_search_store)


def drugmechdb_typed_route_plugin() -> DirectSourceRoutePlugin:
    """Return the typed public DrugMechDB route plugin."""

    return DirectSourceRoutePlugin(
        source_key="drugmechdb",
        routes=(
            DirectSourceTypedRoute(
                path="/v2/spaces/{space_id}/sources/drugmechdb/searches",
                method="POST",
                endpoint=create_drugmechdb_source_search,
                response_model=DrugMechDBSourceSearchResponse,
                status_code=status.HTTP_201_CREATED,
                summary="Search DrugMechDB evidence source",
                dependencies=(Depends(require_harness_space_write_access),),
            ),
            DirectSourceTypedRoute(
                path="/v2/spaces/{space_id}/sources/drugmechdb/searches/{search_id}",
                method="GET",
                endpoint=get_drugmechdb_source_search,
                response_model=DrugMechDBSourceSearchResponse,
                summary="Get DrugMechDB evidence source search",
                dependencies=(Depends(require_harness_space_read_access),),
            ),
        ),
        create_payload=create_drugmechdb_route_payload,
        get_payload=get_drugmechdb_route_payload,
    )


async def create_drugmechdb_source_search(
    space_id: UUID,
    request: DrugMechDBSourceSearchRequest,
    *,
    current_user: HarnessUser = _CURRENT_USER_DEPENDENCY,
    drugmechdb_gateway: DrugMechDBGatewayProtocol | None = (
        _DRUGMECHDB_SOURCE_GATEWAY_DEPENDENCY
    ),
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 route for DrugMechDB source search."""

    return await create_drugmechdb_source_search_payload(
        space_id=space_id,
        request=request,
        current_user=current_user,
        drugmechdb_gateway=drugmechdb_gateway,
        direct_source_search_store=direct_source_search_store,
    )


def get_drugmechdb_source_search(
    space_id: UUID,
    search_id: UUID,
    *,
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 route for DrugMechDB source-search lookup."""

    return get_drugmechdb_source_search_payload(
        space_id=space_id,
        search_id=search_id,
        direct_source_search_store=direct_source_search_store,
    )


async def create_drugmechdb_source_search_payload(
    *,
    space_id: UUID,
    request: DrugMechDBSourceSearchRequest,
    current_user: HarnessUser,
    drugmechdb_gateway: DrugMechDBGatewayProtocol | None,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    """Create a DrugMechDB direct-source search response."""

    gateway = require_gateway(
        drugmechdb_gateway,
        unavailable_detail="DrugMechDB gateway is not available.",
    )
    try:
        result = await run_drugmechdb_direct_search(
            space_id=space_id,
            created_by=current_user.id,
            request=request,
            gateway=gateway,
            store=direct_source_search_store,
        )
    except RuntimeError as exc:
        raise gateway_unavailable(exc) from exc
    return source_result_payload(result)


def get_drugmechdb_source_search_payload(
    *,
    space_id: UUID,
    search_id: UUID,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    """Return a stored DrugMechDB direct-source search response."""

    return stored_source_search_payload(
        space_id=space_id,
        source_key="drugmechdb",
        search_id=search_id,
        direct_source_search_store=direct_source_search_store,
    )


async def create_drugmechdb_route_payload(
    space_id: UUID,
    request_payload: JSONObject,
    dependencies: DirectSourceRouteDependencies,
) -> JSONObject:
    """Create a DrugMechDB search from the generic route payload."""

    drugmechdb_gateway = cast(
        "DrugMechDBGatewayProtocol | None",
        dependencies.source_dependency("drugmechdb"),
    )
    return await create_drugmechdb_source_search_payload(
        space_id=space_id,
        request=parse_source_search_payload(
            request_payload,
            DrugMechDBSourceSearchRequest,
        ),
        current_user=dependencies.current_user,
        drugmechdb_gateway=drugmechdb_gateway,
        direct_source_search_store=dependencies.direct_source_search_store,
    )


def get_drugmechdb_route_payload(
    space_id: UUID,
    search_id: UUID,
    dependencies: DirectSourceRouteDependencies,
) -> JSONObject:
    """Return a DrugMechDB search from the generic route lookup."""

    return get_drugmechdb_source_search_payload(
        space_id=space_id,
        search_id=search_id,
        direct_source_search_store=dependencies.direct_source_search_store,
    )


__all__ = [
    "create_drugmechdb_route_payload",
    "create_drugmechdb_source_search",
    "create_drugmechdb_source_search_payload",
    "drugmechdb_typed_route_plugin",
    "get_drugmechdb_route_payload",
    "get_drugmechdb_source_search",
    "get_drugmechdb_source_search_payload",
]
