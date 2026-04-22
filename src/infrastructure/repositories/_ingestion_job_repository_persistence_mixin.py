"""Persistence and mutation methods for the ingestion job repository."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select

from src.domain.entities.ingestion_job import (
    IngestionError,
    IngestionJob,
    IngestionStatus,
    IngestionTrigger,
    JobMetrics,
)
from src.infrastructure.llm.config import load_runtime_policy
from src.infrastructure.mappers.ingestion_job_mapper import IngestionJobMapper
from src.models.database.ingestion_job import (
    IngestionJobModel,
    IngestionStatusEnum,
    IngestionTriggerEnum,
)

from ._ingestion_job_repository_common import resolve_dictionary_version_used

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.sql.elements import ColumnElement

    from src.type_definitions.common import JSONObject

    from ._ingestion_job_repository_common import IngestionJobRepositoryContext


class SqlAlchemyIngestionJobRepositoryPersistenceMixin:
    """Save, mutate, and aggregate ingestion job rows."""

    def _resolve_dictionary_version_used(
        self: IngestionJobRepositoryContext,
    ) -> int:
        return resolve_dictionary_version_used(self.session)

    def save(
        self: IngestionJobRepositoryContext,
        job: IngestionJob,
    ) -> IngestionJob:
        payload = IngestionJobMapper.to_model_dict(job)
        raw_dictionary_version = payload.get("dictionary_version_used")
        if not isinstance(raw_dictionary_version, int) or raw_dictionary_version < 0:
            payload["dictionary_version_used"] = self._resolve_dictionary_version_used()
        raw_replay_policy = payload.get("replay_policy")
        if not isinstance(raw_replay_policy, str) or not raw_replay_policy.strip():
            payload["replay_policy"] = load_runtime_policy().replay_policy
        model = self.session.get(IngestionJobModel, payload["id"])
        if model is None:
            model = IngestionJobModel(**payload)
            self.session.add(model)
        else:
            for field, value in payload.items():
                setattr(model, field, value)
        self.session.commit()
        self.session.refresh(model)
        return IngestionJobMapper.to_domain(model)

    def update_status(
        self: IngestionJobRepositoryContext,
        job_id: UUID,
        status: IngestionStatus,
    ) -> IngestionJob | None:
        job = self.find_by_id(job_id)
        if job is None:
            return None
        updated_job = job.model_copy(update={"status": status})
        return self.save(updated_job)

    def update_metrics(
        self: IngestionJobRepositoryContext,
        job_id: UUID,
        metrics: JobMetrics,
    ) -> IngestionJob | None:
        job = self.find_by_id(job_id)
        if job is None:
            return None
        updated_job = job.model_copy(update={"metrics": metrics})
        return self.save(updated_job)

    def add_error(
        self: IngestionJobRepositoryContext,
        job_id: UUID,
        error: IngestionError,
    ) -> IngestionJob | None:
        job = self.find_by_id(job_id)
        if job is None:
            return None
        updated_job = job.model_copy(
            update={"errors": [*job.errors, error]},
        )
        return self.save(updated_job)

    def delete(self: IngestionJobRepositoryContext, job_id: UUID) -> bool:
        model = self.session.get(IngestionJobModel, str(job_id))
        if model is None:
            return False
        self.session.delete(model)
        self.session.commit()
        return True

    def start_job(
        self: IngestionJobRepositoryContext,
        job_id: UUID,
    ) -> IngestionJob | None:
        job = self.find_by_id(job_id)
        if job is None:
            return None
        return self.save(job.start_execution())

    def complete_job(
        self: IngestionJobRepositoryContext,
        job_id: UUID,
        metrics: JobMetrics,
    ) -> IngestionJob | None:
        job = self.find_by_id(job_id)
        if job is None:
            return None
        return self.save(job.complete_successfully(metrics))

    def fail_job(
        self: IngestionJobRepositoryContext,
        job_id: UUID,
        error: IngestionError,
    ) -> IngestionJob | None:
        job = self.find_by_id(job_id)
        if job is None:
            return None
        return self.save(job.fail(error))

    def cancel_job(
        self: IngestionJobRepositoryContext,
        job_id: UUID,
    ) -> IngestionJob | None:
        job = self.find_by_id(job_id)
        if job is None:
            return None
        return self.save(job.cancel())

    def delete_old_jobs(
        self: IngestionJobRepositoryContext,
        days: int = 90,
    ) -> int:
        threshold = datetime.now(UTC) - timedelta(days=days)
        stmt = delete(IngestionJobModel).where(
            IngestionJobModel.triggered_at
            < IngestionJobMapper.serialize_timestamp(threshold),
        )
        result = self.session.execute(stmt)
        self.session.commit()
        rowcount = getattr(result, "rowcount", None)
        return int(rowcount or 0)

    def count_by_source(
        self: IngestionJobRepositoryContext,
        source_id: UUID,
    ) -> int:
        stmt = select(func.count()).where(IngestionJobModel.source_id == str(source_id))
        return int(self.session.execute(stmt).scalar_one())

    def count_by_status(
        self: IngestionJobRepositoryContext,
        status: IngestionStatus,
    ) -> int:
        stmt = select(func.count()).where(
            IngestionJobModel.status == IngestionStatusEnum(status.value),
        )
        return int(self.session.execute(stmt).scalar_one())

    def count_by_trigger(
        self: IngestionJobRepositoryContext,
        trigger: IngestionTrigger,
    ) -> int:
        stmt = select(func.count()).where(
            IngestionJobModel.trigger == IngestionTriggerEnum(trigger.value),
        )
        return int(self.session.execute(stmt).scalar_one())

    def exists(self: IngestionJobRepositoryContext, job_id: UUID) -> bool:
        stmt = select(func.count()).where(IngestionJobModel.id == str(job_id))
        return bool(self.session.execute(stmt).scalar_one())

    def get_job_statistics(
        self: IngestionJobRepositoryContext,
        source_id: UUID | None = None,
    ) -> JSONObject:
        filters: list[ColumnElement[bool]] = []
        if source_id:
            filters.append(IngestionJobModel.source_id == str(source_id))

        def _count(additional_clause: ColumnElement[bool] | None = None) -> int:
            stmt = select(func.count()).select_from(IngestionJobModel)
            for clause in filters:
                stmt = stmt.where(clause)
            if additional_clause is not None:
                stmt = stmt.where(additional_clause)
            return int(self.session.execute(stmt).scalar_one())

        total_jobs = _count()
        status_counts = {
            status.value: _count(
                IngestionJobModel.status == IngestionStatusEnum(status.value),
            )
            for status in IngestionStatus
        }
        trigger_counts = {
            trigger.value: _count(
                IngestionJobModel.trigger == IngestionTriggerEnum(trigger.value),
            )
            for trigger in IngestionTrigger
        }

        return {
            "total_jobs": total_jobs,
            "status_counts": status_counts,
            "trigger_counts": trigger_counts,
        }

    def get_recent_failures(
        self: IngestionJobRepositoryContext,
        limit: int = 10,
    ) -> list[tuple[IngestionJob, IngestionError]]:
        stmt = (
            select(IngestionJobModel)
            .where(IngestionJobModel.status == IngestionStatusEnum.FAILED)
            .order_by(IngestionJobModel.triggered_at.desc())
            .limit(limit)
        )
        jobs = self._fetch(stmt)
        failures: list[tuple[IngestionJob, IngestionError]] = []
        for job in jobs:
            error = (
                job.errors[-1]
                if job.errors
                else IngestionError(
                    error_type="unknown",
                    error_message="No error recorded",
                    record_id=None,
                )
            )
            failures.append((job, error))
        return failures
