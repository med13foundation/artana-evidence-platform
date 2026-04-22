"""Port interface for graph-search agent operations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.agents.contexts.graph_search_context import GraphSearchContext
    from src.domain.agents.contracts.graph_search import GraphSearchContract


class GraphSearchPort(ABC):
    """Port for graph-search agent execution."""

    @abstractmethod
    async def search(
        self,
        context: GraphSearchContext,
        *,
        model_id: str | None = None,
    ) -> GraphSearchContract:
        """Run graph search for one natural-language research question."""

    @abstractmethod
    async def close(self) -> None:
        """Release runtime resources used by the adapter."""


__all__ = ["GraphSearchPort"]
