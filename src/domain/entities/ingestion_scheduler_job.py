"""Domain entity for durable scheduler job records."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field

from src.domain.entities.user_data_source import IngestionSchedule, ScheduleFrequency


class IngestionSchedulerJob(BaseModel):
    """Persistent scheduler metadata for one source ingestion job."""

    model_config = ConfigDict(frozen=True)

    job_id: str = Field(..., min_length=1, max_length=64)
    source_id: UUID
    frequency: ScheduleFrequency
    cron_expression: str | None = None
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    start_time: datetime | None = None
    next_run_at: datetime
    last_run_at: datetime | None = None
    is_enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def schedule(self) -> IngestionSchedule:
        """Return the domain schedule represented by this persisted job."""
        return IngestionSchedule(
            enabled=self.is_enabled,
            frequency=self.frequency,
            start_time=self.start_time,
            timezone=self.timezone,
            cron_expression=self.cron_expression,
            backend_job_id=self.job_id,
            next_run_at=self.next_run_at,
            last_run_at=self.last_run_at,
        )


__all__ = ["IngestionSchedulerJob"]
