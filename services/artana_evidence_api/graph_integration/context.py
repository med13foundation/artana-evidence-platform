"""Explicit caller context for graph transport and governed submissions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from artana_evidence_api.evidence_db_auth import (
    build_graph_service_bearer_token_for_service,
)

if TYPE_CHECKING:
    from artana_evidence_api.graph_client import (
        GraphRawMutationTransport,
        GraphTransportBundle,
    )

GraphCallRole = Literal["admin", "curator", "researcher", "viewer"]
GraphServiceCapability = Literal["space_sync"]


@dataclass(frozen=True)
class GraphCallContext:
    """One explicit caller envelope for graph-service requests."""

    user_id: str | None = None
    role: GraphCallRole = "researcher"
    graph_admin: bool = False
    graph_ai_principal: str | None = None
    graph_service_capabilities: tuple[GraphServiceCapability, ...] = ()
    request_id: str | None = None

    def authorization_header(self) -> str:
        """Return a bearer token for this graph caller."""
        return (
            "Bearer "
            + build_graph_service_bearer_token_for_service(
                user_id=self.user_id,
                role=self.role,
                graph_admin=self.graph_admin,
                graph_ai_principal=self.graph_ai_principal,
                graph_service_capabilities=list(self.graph_service_capabilities),
            )
        )

    def default_headers(self) -> dict[str, str]:
        """Return default request headers for one graph call context."""
        headers = {"Authorization": self.authorization_header()}
        if self.request_id is not None and self.request_id.strip():
            headers["X-Request-ID"] = self.request_id.strip()
        return headers

    @classmethod
    def service(
        cls,
        *,
        role: GraphCallRole = "researcher",
        graph_admin: bool = False,
        graph_ai_principal: str | None = None,
        graph_service_capabilities: tuple[GraphServiceCapability, ...] = (),
        request_id: str | None = None,
    ) -> GraphCallContext:
        """Build one service-owned graph call context."""
        return cls(
            role=role,
            graph_admin=graph_admin,
            graph_ai_principal=graph_ai_principal,
            graph_service_capabilities=graph_service_capabilities,
            request_id=request_id,
        )


def make_graph_transport_bundle_factory(
    *,
    call_context: GraphCallContext,
) -> Callable[[], GraphTransportBundle]:
    """Return a stable graph-transport-bundle factory bound to one call context."""
    from artana_evidence_api.graph_client import GraphTransportBundle

    def _factory() -> GraphTransportBundle:
        return GraphTransportBundle(call_context=call_context)

    return _factory


def make_graph_raw_mutation_transport_factory(
    *,
    call_context: GraphCallContext,
) -> Callable[[], GraphRawMutationTransport]:
    """Return a raw-mutation transport factory bound to one call context."""
    from artana_evidence_api.config import get_settings
    from artana_evidence_api.graph_client import GraphRawMutationTransport
    from artana_evidence_api.graph_transport import GraphTransportConfig

    def _factory() -> GraphRawMutationTransport:
        settings = get_settings()
        bundle = GraphTransportBundle(
            config=GraphTransportConfig(
                base_url=settings.graph_api_url,
                timeout_seconds=settings.graph_api_timeout_seconds,
                default_headers=call_context.default_headers(),
            ),
            call_context=call_context,
        )
        runtime = bundle._runtime  # noqa: SLF001 - intentional shared transport runtime
        return GraphRawMutationTransport(runtime)

    from artana_evidence_api.graph_client import GraphTransportBundle

    return _factory


__all__ = [
    "GraphCallContext",
    "GraphCallRole",
    "GraphServiceCapability",
    "make_graph_raw_mutation_transport_factory",
    "make_graph_transport_bundle_factory",
]
