"""Repository interface for durable scheduler job records."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime  # noqa: TC003
from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TC003

if TYPE_CHECKING:
    from src.domain.entities.ingestion_scheduler_job import IngestionSchedulerJob


class IngestionSchedulerJobRepository(ABC):
    """Abstract persistence contract for ingestion scheduler jobs."""

    @abstractmethod
    def get_by_job_id(self, job_id: str) -> IngestionSchedulerJob | None:
        """Fetch one scheduler job by backend job identifier."""

    @abstractmethod
    def get_by_source(self, source_id: UUID) -> IngestionSchedulerJob | None:
        """Fetch the scheduler job associated with a source."""

    @abstractmethod
    def upsert(self, job: IngestionSchedulerJob) -> IngestionSchedulerJob:
        """Create or update a scheduler job record."""

    @abstractmethod
    def list_due(
        self,
        *,
        as_of: datetime,
        limit: int = 100,
    ) -> list[IngestionSchedulerJob]:
        """List enabled jobs that are due at or before the given timestamp."""

    @abstractmethod
    def delete_by_job_id(self, job_id: str) -> bool:
        """Delete a scheduler job by backend job identifier."""

    @abstractmethod
    def delete_by_source(self, source_id: UUID) -> bool:
        """Delete scheduler state for a source."""
