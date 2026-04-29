"""UniProt typed public direct-source routes."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from artana_evidence_api.auth import HarnessUser, get_current_harness_user
from artana_evidence_api.dependencies import (
    get_direct_source_search_store,
    get_uniprot_source_gateway,
    require_harness_space_read_access,
    require_harness_space_write_access,
)
from artana_evidence_api.direct_source_search import (
    DirectSourceSearchStore,
    UniProtSourceSearchRequest,
    UniProtSourceSearchResponse,
    run_uniprot_direct_search,
)
from artana_evidence_api.source_enrichment_bridges import UniProtGatewayProtocol
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
_UNIPROT_SOURCE_GATEWAY_DEPENDENCY = Depends(get_uniprot_source_gateway)
_DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY = Depends(get_direct_source_search_store)


def uniprot_typed_route_plugin() -> DirectSourceRoutePlugin:
    """Return the typed public UniProt route plugin."""

    return DirectSourceRoutePlugin(
        source_key="uniprot",
        routes=(
            DirectSourceTypedRoute(
                path="/v2/spaces/{space_id}/sources/uniprot/searches",
                method="POST",
                endpoint=create_uniprot_source_search,
                response_model=UniProtSourceSearchResponse,
                status_code=status.HTTP_201_CREATED,
                summary="Search UniProt evidence source",
                dependencies=(Depends(require_harness_space_write_access),),
            ),
            DirectSourceTypedRoute(
                path="/v2/spaces/{space_id}/sources/uniprot/searches/{search_id}",
                method="GET",
                endpoint=get_uniprot_source_search,
                response_model=UniProtSourceSearchResponse,
                summary="Get UniProt evidence source search",
                dependencies=(Depends(require_harness_space_read_access),),
            ),
        ),
        create_payload=create_uniprot_route_payload,
        get_payload=get_uniprot_route_payload,
    )


async def create_uniprot_source_search(
    space_id: UUID,
    request: UniProtSourceSearchRequest,
    *,
    current_user: HarnessUser = _CURRENT_USER_DEPENDENCY,
    uniprot_gateway: UniProtGatewayProtocol | None = (
        _UNIPROT_SOURCE_GATEWAY_DEPENDENCY
    ),
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 route for UniProt source search."""

    return await create_uniprot_source_search_payload(
        space_id=space_id,
        request=request,
        current_user=current_user,
        uniprot_gateway=uniprot_gateway,
        direct_source_search_store=direct_source_search_store,
    )


def get_uniprot_source_search(
    space_id: UUID,
    search_id: UUID,
    *,
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
) -> JSONObject:
    """Typed v2 route for UniProt source-search lookup."""

    return get_uniprot_source_search_payload(
        space_id=space_id,
        search_id=search_id,
        direct_source_search_store=direct_source_search_store,
    )


async def create_uniprot_source_search_payload(
    *,
    space_id: UUID,
    request: UniProtSourceSearchRequest,
    current_user: HarnessUser,
    uniprot_gateway: UniProtGatewayProtocol | None,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    """Create a UniProt direct-source search response."""

    gateway = require_gateway(
        uniprot_gateway,
        unavailable_detail="UniProt gateway is not available.",
    )
    try:
        result = await run_uniprot_direct_search(
            space_id=space_id,
            created_by=current_user.id,
            request=request,
            gateway=gateway,
            store=direct_source_search_store,
        )
    except RuntimeError as exc:
        raise gateway_unavailable(exc) from exc
    return source_result_payload(result)


def get_uniprot_source_search_payload(
    *,
    space_id: UUID,
    search_id: UUID,
    direct_source_search_store: DirectSourceSearchStore,
) -> JSONObject:
    """Return a stored UniProt direct-source search response."""

    return stored_source_search_payload(
        space_id=space_id,
        source_key="uniprot",
        search_id=search_id,
        direct_source_search_store=direct_source_search_store,
    )


async def create_uniprot_route_payload(
    space_id: UUID,
    request_payload: JSONObject,
    dependencies: DirectSourceRouteDependencies,
) -> JSONObject:
    """Create a UniProt search from the generic route payload."""

    uniprot_gateway = cast(
        "UniProtGatewayProtocol | None",
        dependencies.source_dependency("uniprot"),
    )
    return await create_uniprot_source_search_payload(
        space_id=space_id,
        request=parse_source_search_payload(request_payload, UniProtSourceSearchRequest),
        current_user=dependencies.current_user,
        uniprot_gateway=uniprot_gateway,
        direct_source_search_store=dependencies.direct_source_search_store,
    )


def get_uniprot_route_payload(
    space_id: UUID,
    search_id: UUID,
    dependencies: DirectSourceRouteDependencies,
) -> JSONObject:
    """Return a UniProt search from the generic route lookup."""

    return get_uniprot_source_search_payload(
        space_id=space_id,
        search_id=search_id,
        direct_source_search_store=dependencies.direct_source_search_store,
    )


__all__ = [
    "create_uniprot_route_payload",
    "create_uniprot_source_search",
    "create_uniprot_source_search_payload",
    "get_uniprot_route_payload",
    "get_uniprot_source_search",
    "get_uniprot_source_search_payload",
    "uniprot_typed_route_plugin",
]
