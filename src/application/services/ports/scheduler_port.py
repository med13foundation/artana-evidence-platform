"""Port abstraction for pluggable ingestion schedulers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from uuid import UUID

    from src.domain.entities.user_data_source import IngestionSchedule


@dataclass
class ScheduledJob:
    """Representation of a scheduled ingestion job."""

    job_id: str
    source_id: UUID
    schedule: IngestionSchedule
    next_run_at: datetime

    def is_due(self, *, as_of: datetime | None = None) -> bool:
        reference = as_of or datetime.now(UTC)
        return self.next_run_at <= reference


class SchedulerPort(Protocol):
    """Protocol that scheduler implementations must satisfy."""

    def register_job(
        self,
        source_id: UUID,
        schedule: IngestionSchedule,
    ) -> ScheduledJob:
        """Register or update a recurring job for the given source."""

    def get_job(self, job_id: str) -> ScheduledJob | None:
        """Return the current scheduler metadata for a job if available."""

    def remove_job(self, job_id: str) -> None:
        """Remove a scheduled job."""

    def get_due_jobs(self, *, as_of: datetime | None = None) -> list[ScheduledJob]:
        """Return jobs that should run at or before the given timestamp."""
