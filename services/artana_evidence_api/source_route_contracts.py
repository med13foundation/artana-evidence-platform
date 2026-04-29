"""Shared contracts for public direct-source route plugins."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType, UnionType
from uuid import UUID

from artana_evidence_api.auth import HarnessUser
from artana_evidence_api.direct_source_search import DirectSourceSearchStore
from artana_evidence_api.types.common import JSONObject
from fastapi import APIRouter
from fastapi.params import Depends as DependsParameter
from pydantic import BaseModel


@dataclass(frozen=True, slots=True)
class DirectSourceRouteDependencies:
    """Dependencies supplied by the public route layer."""

    current_user: HarnessUser
    direct_source_search_store: DirectSourceSearchStore
    source_dependencies: Mapping[str, object | None] = MappingProxyType({})

    def source_dependency(self, source_key: str) -> object | None:
        """Return the route-edge dependency supplied for one source, if any."""

        return self.source_dependencies.get(source_key)


DirectSourceCreatePayload = Callable[
    [UUID, JSONObject, DirectSourceRouteDependencies],
    Awaitable[JSONObject],
]
DirectSourceGetPayload = Callable[
    [UUID, UUID, DirectSourceRouteDependencies],
    JSONObject,
]
RouteResponseModel = type[BaseModel] | UnionType | None
RouteEndpointResult = JSONObject | BaseModel
RouteEndpoint = Callable[..., RouteEndpointResult | Awaitable[RouteEndpointResult]]


@dataclass(frozen=True, slots=True)
class DirectSourceTypedRoute:
    """One typed public source-search route owned by a route plugin."""

    path: str
    method: str
    endpoint: RouteEndpoint
    response_model: RouteResponseModel
    summary: str
    dependencies: tuple[DependsParameter, ...]
    tags: tuple[str, ...] = ("sources",)
    status_code: int | None = None

    def register(self, router: APIRouter) -> None:
        """Register this typed route on the public v2 router."""

        router.add_api_route(
            self.path,
            self.endpoint,
            methods=[self.method],
            response_model=self.response_model,
            status_code=self.status_code,
            summary=self.summary,
            dependencies=list(self.dependencies),
            tags=list(self.tags),
        )


@dataclass(frozen=True, slots=True)
class DirectSourceRoutePlugin:
    """Route plugin for one direct-search source's public endpoint set.

    Payload callables may raise ``HTTPException`` because this is the HTTP
    compatibility edge, not a transport-neutral domain service.
    """

    source_key: str
    routes: tuple[DirectSourceTypedRoute, ...]
    create_payload: DirectSourceCreatePayload
    get_payload: DirectSourceGetPayload

    def register(self, router: APIRouter) -> None:
        """Register all typed routes owned by this source."""

        for route in self.routes:
            route.register(router)

    async def create(
        self,
        *,
        space_id: UUID,
        request_payload: JSONObject,
        dependencies: DirectSourceRouteDependencies,
    ) -> JSONObject:
        """Create one source search from a generic route payload."""

        return await self.create_payload(space_id, request_payload, dependencies)

    def get(
        self,
        *,
        space_id: UUID,
        search_id: UUID,
        dependencies: DirectSourceRouteDependencies,
    ) -> JSONObject:
        """Return one source search from a generic route lookup."""

        return self.get_payload(space_id, search_id, dependencies)


__all__ = [
    "DirectSourceCreatePayload",
    "DirectSourceGetPayload",
    "DirectSourceRouteDependencies",
    "DirectSourceRoutePlugin",
    "DirectSourceTypedRoute",
    "RouteEndpoint",
    "RouteEndpointResult",
    "RouteResponseModel",
]
