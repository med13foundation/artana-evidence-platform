"""Port interface for PubMed semantic relevance classification."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.agents.contexts.pubmed_relevance_context import (
        PubMedRelevanceContext,
    )
    from src.domain.agents.contracts.pubmed_relevance import PubMedRelevanceContract


class PubMedRelevancePort(ABC):
    """Port for classifying PubMed title/abstract semantic relevance."""

    @abstractmethod
    async def classify(
        self,
        context: PubMedRelevanceContext,
        *,
        model_id: str | None = None,
    ) -> PubMedRelevanceContract:
        """Return a relevance label (`relevant` or `non_relevant`)."""

    @abstractmethod
    async def close(self) -> None:
        """Release runtime resources used by the adapter."""


__all__ = ["PubMedRelevancePort"]
