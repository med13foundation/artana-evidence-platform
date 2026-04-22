"""In-memory scheduler backend for development and testing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from src.application.services.ports.scheduler_port import ScheduledJob, SchedulerPort
from src.domain.entities.user_data_source import IngestionSchedule, ScheduleFrequency


class InMemoryScheduler(SchedulerPort):
    """Simple scheduler backend that computes upcoming runs eagerly."""

    def __init__(self) -> None:
        self._jobs: dict[str, ScheduledJob] = {}

    def register_job(
        self,
        source_id: UUID,
        schedule: IngestionSchedule,
    ) -> ScheduledJob:
        if not schedule.requires_scheduler:
            msg = "Schedule must be enabled and non-manual to register with scheduler"
            raise ValueError(msg)

        job_id = schedule.backend_job_id or str(uuid4())
        next_run = self._compute_next_run(schedule, datetime.now(UTC))
        job = ScheduledJob(
            job_id=job_id,
            source_id=source_id,
            schedule=schedule,
            next_run_at=next_run,
        )
        self._jobs[job.job_id] = job
        return job

    def remove_job(self, job_id: str) -> None:
        self._jobs.pop(job_id, None)

    def get_due_jobs(self, *, as_of: datetime | None = None) -> list[ScheduledJob]:
        reference = as_of or datetime.now(UTC)
        due_jobs = [job for job in self._jobs.values() if job.is_due(as_of=reference)]
        for job in due_jobs:
            updated_job = ScheduledJob(
                job_id=job.job_id,
                source_id=job.source_id,
                schedule=job.schedule,
                next_run_at=self._compute_next_run(job.schedule, reference),
            )
            self._jobs[job.job_id] = updated_job
        return due_jobs

    def get_job(self, job_id: str) -> ScheduledJob | None:
        return self._jobs.get(job_id)

    def _compute_next_run(
        self,
        schedule: IngestionSchedule,
        reference: datetime,
    ) -> datetime:
        if schedule.frequency == ScheduleFrequency.HOURLY:
            delta = timedelta(hours=1)
        elif schedule.frequency == ScheduleFrequency.DAILY:
            delta = timedelta(days=1)
        elif schedule.frequency == ScheduleFrequency.WEEKLY:
            delta = timedelta(weeks=1)
        elif schedule.frequency == ScheduleFrequency.MONTHLY:
            delta = timedelta(days=30)
        elif schedule.frequency == ScheduleFrequency.CRON:
            msg = "Cron expressions require a dedicated scheduler backend"
            raise NotImplementedError(msg)
        else:
            delta = timedelta(days=365)

        start = schedule.start_time or reference
        if start > reference:
            return start
        return reference + delta
