"""Mapper utilities for ingestion scheduler job entities."""

from __future__ import annotations

from uuid import UUID

from src.domain.entities.ingestion_scheduler_job import IngestionSchedulerJob
from src.domain.entities.user_data_source import ScheduleFrequency
from src.models.database.ingestion_scheduler_job import IngestionSchedulerJobModel


class IngestionSchedulerJobMapper:
    """Bidirectional mapper for durable scheduler job rows."""

    @staticmethod
    def to_domain(model: IngestionSchedulerJobModel) -> IngestionSchedulerJob:
        return IngestionSchedulerJob(
            job_id=model.job_id,
            source_id=UUID(model.source_id),
            frequency=ScheduleFrequency(model.frequency),
            cron_expression=model.cron_expression,
            timezone=model.timezone,
            start_time=model.start_time,
            next_run_at=model.next_run_at,
            last_run_at=model.last_run_at,
            is_enabled=model.is_enabled,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def to_model(entity: IngestionSchedulerJob) -> IngestionSchedulerJobModel:
        return IngestionSchedulerJobModel(
            job_id=entity.job_id,
            source_id=str(entity.source_id),
            frequency=entity.frequency.value,
            cron_expression=entity.cron_expression,
            timezone=entity.timezone,
            start_time=entity.start_time,
            next_run_at=entity.next_run_at,
            last_run_at=entity.last_run_at,
            is_enabled=entity.is_enabled,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
