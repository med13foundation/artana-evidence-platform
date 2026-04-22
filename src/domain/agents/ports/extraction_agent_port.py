"""Port interface for extraction agent operations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.agents.contexts.extraction_context import ExtractionContext
    from src.domain.agents.contracts.extraction import ExtractionContract


class ExtractionAgentPort(ABC):
    """Port for tool-assisted extraction agent execution."""

    @abstractmethod
    async def extract(
        self,
        context: ExtractionContext,
        *,
        model_id: str | None = None,
    ) -> ExtractionContract:
        """Extract structured observations and relations from context."""

    @abstractmethod
    async def close(self) -> None:
        """Release runtime resources used by the adapter."""


__all__ = ["ExtractionAgentPort"]
