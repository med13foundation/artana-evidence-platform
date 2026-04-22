"""Application service for publication extraction outputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.domain.repositories.base import QuerySpecification

if TYPE_CHECKING:
    from uuid import UUID

    from src.domain.entities.publication_extraction import PublicationExtraction
    from src.domain.repositories.publication_extraction_repository import (
        PublicationExtractionRepository,
    )


@dataclass(frozen=True)
class PublicationExtractionListResult:
    items: list[PublicationExtraction]
    total: int


class PublicationExtractionService:
    """Coordinates read access to publication extraction outputs."""

    def __init__(
        self,
        repository: PublicationExtractionRepository,
    ) -> None:
        self._repository = repository

    def get_by_id(self, extraction_id: UUID) -> PublicationExtraction | None:
        return self._repository.get_by_id(extraction_id)

    def list_extractions(
        self,
        spec: QuerySpecification,
    ) -> PublicationExtractionListResult:
        items = self._repository.find_by_criteria(spec)
        total = self._repository.count_by_criteria(
            QuerySpecification(filters=spec.filters),
        )
        return PublicationExtractionListResult(items=items, total=total)


__all__ = ["PublicationExtractionListResult", "PublicationExtractionService"]
