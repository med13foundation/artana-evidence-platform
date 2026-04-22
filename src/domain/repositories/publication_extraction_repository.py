"""
Publication extraction repository interface.

Defines persistence operations for extracted publication facts.
"""

from __future__ import annotations

from abc import abstractmethod
from uuid import UUID

from src.domain.entities.publication_extraction import PublicationExtraction
from src.domain.repositories.base import QuerySpecification, Repository
from src.type_definitions.common import PublicationExtractionUpdate


class PublicationExtractionRepository(
    Repository[PublicationExtraction, UUID, PublicationExtractionUpdate],
):
    """Domain repository interface for publication extraction outputs."""

    @abstractmethod
    def find_by_publication_id(
        self,
        publication_id: int,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[PublicationExtraction]:
        """List extraction outputs for a publication."""

    @abstractmethod
    def find_by_queue_item_id(
        self,
        queue_item_id: UUID,
    ) -> PublicationExtraction | None:
        """Find extraction output by queue item ID."""

    @abstractmethod
    def count_by_criteria(self, spec: QuerySpecification) -> int:
        """Count extraction outputs matching a specification."""


__all__ = ["PublicationExtractionRepository"]
