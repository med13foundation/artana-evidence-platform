"""Postgres-backed durable scheduler backend."""

from __future__ import annotations

from calendar import monthrange
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

from src.application.services.ports.scheduler_port import ScheduledJob, SchedulerPort
from src.domain.entities.user_data_source import IngestionSchedule, ScheduleFrequency
from src.models.database.ingestion_scheduler_job import IngestionSchedulerJobModel

from ._postgres_scheduler_cron import next_cron_occurrence

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

DEFAULT_DUE_JOB_BATCH_SIZE = 500


class PostgresScheduler(SchedulerPort):
    """Durable scheduler implementation backed by Postgres tables."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        due_job_batch_size: int = DEFAULT_DUE_JOB_BATCH_SIZE,
    ) -> None:
        self._session_factory = session_factory
        self._due_job_batch_size = max(due_job_batch_size, 1)

    def register_job(
        self,
        source_id: UUID,
        schedule: IngestionSchedule,
    ) -> ScheduledJob:
        if not schedule.requires_scheduler:
            msg = "Schedule must be enabled and non-manual to register with scheduler"
            raise ValueError(msg)

        reference = datetime.now(UTC)
        next_run_at = self._compute_next_run(schedule=schedule, reference=reference)
        source_id_text = str(source_id)
        timezone_name = schedule.timezone or "UTC"
        normalized_start = self._normalize_datetime(schedule.start_time)

        with self._session_factory() as session:
            existing = session.execute(
                select(IngestionSchedulerJobModel)
                .where(IngestionSchedulerJobModel.source_id == source_id_text)
                .limit(1),
            ).scalar_one_or_none()

            model: IngestionSchedulerJobModel
            if existing is None:
                resolved_job_id = schedule.backend_job_id or str(uuid4())
                model = IngestionSchedulerJobModel(
                    job_id=resolved_job_id,
                    source_id=source_id_text,
                    frequency=schedule.frequency.value,
                    cron_expression=schedule.cron_expression,
                    timezone=timezone_name,
                    start_time=normalized_start,
                    next_run_at=next_run_at,
                    last_run_at=None,
                    is_enabled=True,
                )
                session.add(model)
            else:
                model = existing
                model.frequency = schedule.frequency.value
                model.cron_expression = schedule.cron_expression
                model.timezone = timezone_name
                model.start_time = normalized_start
                model.next_run_at = next_run_at
                model.is_enabled = True

            session.commit()
            session.refresh(model)
            return self._to_scheduled_job(model)

    def remove_job(self, job_id: str) -> None:
        with self._session_factory() as session:
            model = session.get(IngestionSchedulerJobModel, job_id)
            if model is None:
                return
            session.delete(model)
            session.commit()

    def get_due_jobs(self, *, as_of: datetime | None = None) -> list[ScheduledJob]:
        reference = self._normalize_datetime(as_of) or datetime.now(UTC)

        with self._session_factory() as session:
            with session.begin():
                stmt = (
                    select(IngestionSchedulerJobModel)
                    .where(IngestionSchedulerJobModel.is_enabled.is_(True))
                    .where(IngestionSchedulerJobModel.next_run_at <= reference)
                    .order_by(IngestionSchedulerJobModel.next_run_at.asc())
                    .limit(self._due_job_batch_size)
                    .with_for_update(skip_locked=True)
                )
                models = session.execute(stmt).scalars().all()
                due_jobs = [self._to_scheduled_job(model) for model in models]

                for model in models:
                    schedule = self._to_schedule(model)
                    model.last_run_at = reference
                    model.next_run_at = self._compute_next_run(
                        schedule=schedule,
                        reference=reference,
                    )

            return due_jobs

    def get_job(self, job_id: str) -> ScheduledJob | None:
        with self._session_factory() as session:
            model = session.get(IngestionSchedulerJobModel, job_id)
            if model is None:
                return None
            return self._to_scheduled_job(model)

    @staticmethod
    def _normalize_datetime(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _resolve_timezone(timezone_name: str) -> ZoneInfo:
        normalized = timezone_name.strip() or "UTC"
        try:
            return ZoneInfo(normalized)
        except ZoneInfoNotFoundError as exc:
            msg = f"Unknown timezone '{timezone_name}'"
            raise ValueError(msg) from exc

    @classmethod
    def _resolve_start_local(
        cls,
        *,
        start_time: datetime | None,
        reference_local: datetime,
        timezone: ZoneInfo,
    ) -> datetime:
        normalized_start = cls._normalize_datetime(start_time)
        if normalized_start is None:
            return reference_local
        return normalized_start.astimezone(timezone)

    def _compute_next_run(
        self,
        *,
        schedule: IngestionSchedule,
        reference: datetime,
    ) -> datetime:
        normalized_reference = self._normalize_datetime(reference) or datetime.now(UTC)
        timezone = self._resolve_timezone(schedule.timezone)
        reference_local = normalized_reference.astimezone(timezone)
        start_local = self._resolve_start_local(
            start_time=schedule.start_time,
            reference_local=reference_local,
            timezone=timezone,
        )

        next_run_local: datetime
        if schedule.frequency == ScheduleFrequency.HOURLY:
            next_run_local = self._next_fixed_interval(
                start=start_local,
                reference=reference_local,
                delta=timedelta(hours=1),
            )
        elif schedule.frequency == ScheduleFrequency.DAILY:
            next_run_local = self._next_fixed_interval(
                start=start_local,
                reference=reference_local,
                delta=timedelta(days=1),
            )
        elif schedule.frequency == ScheduleFrequency.WEEKLY:
            next_run_local = self._next_fixed_interval(
                start=start_local,
                reference=reference_local,
                delta=timedelta(weeks=1),
            )
        elif schedule.frequency == ScheduleFrequency.MONTHLY:
            next_run_local = self._next_monthly_interval(
                start=start_local,
                reference=reference_local,
            )
        elif schedule.frequency == ScheduleFrequency.CRON:
            if not schedule.cron_expression:
                msg = "Cron expressions require a non-empty cron_expression value"
                raise ValueError(msg)
            next_run_local = next_cron_occurrence(
                expression=schedule.cron_expression,
                reference=reference_local,
            )
        else:
            msg = f"Unsupported scheduler frequency: {schedule.frequency.value}"
            raise ValueError(msg)

        return next_run_local.astimezone(UTC)

    @staticmethod
    def _next_fixed_interval(
        *,
        start: datetime,
        reference: datetime,
        delta: timedelta,
    ) -> datetime:
        if start > reference:
            return start

        elapsed = reference - start
        steps = int(elapsed // delta) + 1
        return start + (delta * steps)

    @staticmethod
    def _next_monthly_interval(*, start: datetime, reference: datetime) -> datetime:
        if start > reference:
            return start

        month_delta = (reference.year - start.year) * 12 + (
            reference.month - start.month
        )
        candidate = PostgresScheduler._add_months(start, month_delta)
        if candidate <= reference:
            candidate = PostgresScheduler._add_months(start, month_delta + 1)
        return candidate

    @staticmethod
    def _add_months(value: datetime, months: int) -> datetime:
        month_index = (value.month - 1) + months
        year = value.year + (month_index // 12)
        month = (month_index % 12) + 1
        day = min(value.day, monthrange(year, month)[1])
        return value.replace(year=year, month=month, day=day)

    def _to_schedule(self, model: IngestionSchedulerJobModel) -> IngestionSchedule:
        try:
            frequency = ScheduleFrequency(model.frequency)
        except ValueError as exc:
            msg = f"Unsupported persisted scheduler frequency: {model.frequency}"
            raise ValueError(msg) from exc
        return IngestionSchedule(
            enabled=bool(model.is_enabled),
            frequency=frequency,
            start_time=self._normalize_datetime(model.start_time),
            timezone=model.timezone or "UTC",
            cron_expression=model.cron_expression,
            backend_job_id=model.job_id,
            next_run_at=self._normalize_datetime(model.next_run_at),
            last_run_at=self._normalize_datetime(model.last_run_at),
        )

    def _to_scheduled_job(self, model: IngestionSchedulerJobModel) -> ScheduledJob:
        schedule = self._to_schedule(model)
        next_run_at = self._normalize_datetime(model.next_run_at)
        if next_run_at is None:
            msg = f"Persisted scheduler job {model.job_id} is missing next_run_at"
            raise ValueError(msg)
        return ScheduledJob(
            job_id=model.job_id,
            source_id=UUID(model.source_id),
            schedule=schedule,
            next_run_at=next_run_at,
        )
