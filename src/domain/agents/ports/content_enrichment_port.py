"""Port interface for content-enrichment agent execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.agents.contexts.content_enrichment_context import (
        ContentEnrichmentContext,
    )
    from src.domain.agents.contracts.content_enrichment import (
        ContentEnrichmentContract,
    )


class ContentEnrichmentPort(ABC):
    """Port for Tier-2 content-enrichment workflows."""

    @abstractmethod
    async def enrich(
        self,
        context: ContentEnrichmentContext,
        *,
        model_id: str | None = None,
    ) -> ContentEnrichmentContract:
        """Enrich one source document and return a structured contract."""

    @abstractmethod
    async def close(self) -> None:
        """Release runtime resources used by the adapter."""


__all__ = ["ContentEnrichmentPort"]
