"""DrugBank typed public direct-source routes."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from artana_evidence_api.auth import HarnessUser, get_current_harness_user
from artana_evidence_api.dependencies import (
    get_direct_source_search_store,
    get_drugbank_source_gateway,
    require_harness_space_read_access,
    require_harness_space_write_access,
)
from artana_evidence_api.direct_source_search import (
    DirectSourceSearchStore,
    DrugBankSourceSearchRequest,
    DrugBankSourceSearchResponse,
    run_drugbank_direct_search,
)
from artana_evidence_api.source_enrichment_bridges import DrugBankGatewayProtocol
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
_DRUGBANK_SOURCE_GATEWAY_DEPENDENCY = Depends(get_drugbank_source_gateway)
_DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY = Depends(get_direct_source_search_store)


def drugbank_typed_route_plugin() -> DirectSourceRoutePlugin:
    """Return the typed public DrugBank route plugin."""

    return DirectSourceRoutePlugin(
        source_key="drugbank",
        routes=(
            DirectSourceTypedRoute(
                path="/v2/spaces/{space_id}/sources/drugbank/searches",
                method="POST",
                endpoint=create_drugbank_source_search,
                response_model=DrugBankSourceSearchResponse,
                status_code=status.HTTP_201_CREATED,
                summary="Search DrugBank evidence source",
                dependencies=(Depends(require_harness_space_write_access),),
            ),
            DirectSourceTypedRoute(
                path="/v2/spaces/{space_id}/sources/drugbank/searches/{search_id}",
                method="GET",
                endpoint=get_drugbank_source_search,
                response_model=DrugBankSourceSearchResponse,
                summary="Get DrugBank evidence source search",
                dependencies=(Depends(require_harness_space_read_access),),
            ),
        ),
        create_payload=create_drugbank_route_payload,
        get_payload=get_drugbank_route_payload,
    )


async def create_drugbank_source_search(
    space_id: UUID,
    request: DrugBankSourceSearchRequest,
    *,
    current_user: HarnessUser = _CURRENT_USER_DEPENDENCY,
    drugbank_gateway: DrugBankGatewayProtocol | None = (
        _DRUGBANK_SOURCE_GATEWAY_DEPENDENCY
    ),
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 route for DrugBank source search."""

    return await create_drugbank_source_search_payload(
        space_id=space_id,
        request=request,
        current_user=current_user,
        drugbank_gateway=drugbank_gateway,
        direct_source_search_store=direct_source_search_store,
    )


def get_drugbank_source_search(
    space_id: UUID,
    search_id: UUID,
    *,
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 route for DrugBank source-search lookup."""

    return get_drugbank_source_search_payload(
        space_id=space_id,
        search_id=search_id,
        direct_source_search_store=direct_source_search_store,
    )


async def create_drugbank_source_search_payload(
    *,
    space_id: UUID,
    request: DrugBankSourceSearchRequest,
    current_user: HarnessUser,
    drugbank_gateway: DrugBankGatewayProtocol | None,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    """Create a DrugBank direct-source search response."""

    gateway = require_gateway(
        drugbank_gateway,
        unavailable_detail="DrugBank credentials are not configured.",
    )
    try:
        result = await run_drugbank_direct_search(
            space_id=space_id,
            created_by=current_user.id,
            request=request,
            gateway=gateway,
            store=direct_source_search_store,
        )
    except RuntimeError as exc:
        raise gateway_unavailable(exc) from exc
    return source_result_payload(result)


def get_drugbank_source_search_payload(
    *,
    space_id: UUID,
    search_id: UUID,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    """Return a stored DrugBank direct-source search response."""

    return stored_source_search_payload(
        space_id=space_id,
        source_key="drugbank",
        search_id=search_id,
        direct_source_search_store=direct_source_search_store,
    )


async def create_drugbank_route_payload(
    space_id: UUID,
    request_payload: JSONObject,
    dependencies: DirectSourceRouteDependencies,
) -> JSONObject:
    """Create a DrugBank search from the generic route payload."""

    drugbank_gateway = cast(
        "DrugBankGatewayProtocol | None",
        dependencies.source_dependency("drugbank"),
    )
    return await create_drugbank_source_search_payload(
        space_id=space_id,
        request=parse_source_search_payload(request_payload, DrugBankSourceSearchRequest),
        current_user=dependencies.current_user,
        drugbank_gateway=drugbank_gateway,
        direct_source_search_store=dependencies.direct_source_search_store,
    )


def get_drugbank_route_payload(
    space_id: UUID,
    search_id: UUID,
    dependencies: DirectSourceRouteDependencies,
) -> JSONObject:
    """Return a DrugBank search from the generic route lookup."""

    return get_drugbank_source_search_payload(
        space_id=space_id,
        search_id=search_id,
        direct_source_search_store=dependencies.direct_source_search_store,
    )


__all__ = [
    "create_drugbank_route_payload",
    "create_drugbank_source_search",
    "create_drugbank_source_search_payload",
    "drugbank_typed_route_plugin",
    "get_drugbank_route_payload",
    "get_drugbank_source_search",
    "get_drugbank_source_search_payload",
]
