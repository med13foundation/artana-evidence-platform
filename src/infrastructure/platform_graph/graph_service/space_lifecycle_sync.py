"""Graph-service-backed tenant lifecycle sync adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domain.entities.research_space import ResearchSpace

from .space_sync import sync_platform_space_to_graph

if TYPE_CHECKING:
    from src.domain.repositories.research_space_repository import (
        ResearchSpaceMembershipRepository,
    )

    from .client import GraphServiceClient


class GraphServiceSpaceLifecycleSync:
    """Synchronize platform tenant changes into the standalone graph service."""

    def __init__(
        self,
        *,
        membership_repository: ResearchSpaceMembershipRepository,
        client: GraphServiceClient | None = None,
    ) -> None:
        self._membership_repository = membership_repository
        self._client = client

    def sync_space(self, space: ResearchSpace) -> None:
        """Push one authoritative tenant snapshot to the graph service."""
        sync_platform_space_to_graph(
            space=space,
            memberships=self._membership_repository.find_by_space(
                space.id,
                skip=0,
                limit=1000,
            ),
            client=self._client,
        )


__all__ = ["GraphServiceSpaceLifecycleSync"]
