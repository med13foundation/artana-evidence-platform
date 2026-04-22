"""Repository interface for source document lifecycle persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from src.domain.entities.source_document import SourceDocument  # noqa: TC001

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID


class SourceDocumentRepository(ABC):
    """Abstract persistence contract for Document Store records."""

    @abstractmethod
    def get_by_id(self, document_id: UUID) -> SourceDocument | None:
        """Fetch a source document by its primary id."""

    @abstractmethod
    def get_by_source_external_record(
        self,
        *,
        source_id: UUID,
        external_record_id: str,
    ) -> SourceDocument | None:
        """Fetch a source document by source + upstream record identifier."""

    @abstractmethod
    def upsert(self, document: SourceDocument) -> SourceDocument:
        """Create or update a source document using source/external id identity."""

    @abstractmethod
    def upsert_many(
        self,
        documents: list[SourceDocument],
    ) -> list[SourceDocument]:
        """Create or update one or more source documents."""

    @abstractmethod
    def list_pending_enrichment(
        self,
        *,
        limit: int = 100,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
        ingestion_job_id: UUID | None = None,
        source_type: str | None = None,
    ) -> list[SourceDocument]:
        """List documents waiting for enrichment."""

    @abstractmethod
    def list_pending_extraction(
        self,
        *,
        limit: int = 100,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
        ingestion_job_id: UUID | None = None,
        source_type: str | None = None,
    ) -> list[SourceDocument]:
        """List documents waiting for extraction."""

    def recover_stale_in_progress_extraction(
        self,
        *,
        stale_before: datetime,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
        ingestion_job_id: UUID | None = None,
        limit: int = 500,
    ) -> int:
        """
        Recover stale extraction documents stuck in IN_PROGRESS.

        Default implementation is a no-op so lightweight stubs do not need to
        implement it unless recovery behavior is under test.
        """
        _ = stale_before
        _ = source_id
        _ = research_space_id
        _ = ingestion_job_id
        _ = limit
        return 0

    @abstractmethod
    def delete_by_source(self, source_id: UUID) -> int:
        """Delete all document rows for the given source and return affected rows."""

    @abstractmethod
    def count_for_source(self, source_id: UUID) -> int:
        """Count source documents for a given source."""
