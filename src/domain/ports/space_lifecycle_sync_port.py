"""Port for syncing tenant lifecycle changes into the graph control plane."""

from __future__ import annotations

from typing import Protocol

from src.domain.entities.research_space import ResearchSpace


class SpaceLifecycleSyncPort(Protocol):
    """Push the latest tenant snapshot into the graph service."""

    def sync_space(self, space: ResearchSpace) -> None:
        """Synchronize one space and its effective membership snapshot."""
