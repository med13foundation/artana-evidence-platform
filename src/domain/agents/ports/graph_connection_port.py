"""Port interface for graph-connection agent operations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.agents.contexts.graph_connection_context import (
        GraphConnectionContext,
    )
    from src.domain.agents.contracts.graph_connection import GraphConnectionContract


class GraphConnectionPort(ABC):
    """Port for graph-connection agent execution."""

    @abstractmethod
    async def discover(
        self,
        context: GraphConnectionContext,
        *,
        model_id: str | None = None,
    ) -> GraphConnectionContract:
        """Discover relation candidates from a graph neighborhood."""

    @abstractmethod
    async def close(self) -> None:
        """Release runtime resources used by the adapter."""


__all__ = ["GraphConnectionPort"]
