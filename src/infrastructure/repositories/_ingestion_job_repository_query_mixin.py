"""Query-heavy mixin for the ingestion job repository."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import desc, select
from sqlalchemy.exc import OperationalError, ProgrammingError

from src.domain.entities.ingestion_job import (
    IngestionJob,
    IngestionJobKind,
    IngestionStatus,
    IngestionTrigger,
)
from src.infrastructure.mappers.ingestion_job_mapper import IngestionJobMapper
from src.models.database.ingestion_job import (
    IngestionJobKindEnum,
    IngestionJobModel,
    IngestionStatusEnum,
    IngestionTriggerEnum,
)

from ._ingestion_job_repository_common import (
    _coerce_json_object,
    _normalize_optional_string,
    _parse_timestamp,
    is_missing_optional_column_error,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy import Select

    from src.type_definitions.common import JSONObject

    from ._ingestion_job_repository_common import IngestionJobRepositoryContext


class SqlAlchemyIngestionJobRepositoryQueryMixin:
    """Read/query methods for ingestion jobs and queued pipeline metadata."""

    @staticmethod
    def _pipeline_payload_from_job_metadata(job_metadata: object) -> JSONObject:
        metadata = _coerce_json_object(job_metadata)
        return _coerce_json_object(metadata.get("pipeline_run"))

    @classmethod
    def _resolve_pipeline_run_id(cls, job_metadata: object) -> str | None:
        pipeline_payload = cls._pipeline_payload_from_job_metadata(job_metadata)
        return _normalize_optional_string(pipeline_payload.get("run_id"))

    @classmethod
    def _resolve_pipeline_queue_status(cls, job_metadata: object) -> str | None:
        pipeline_payload = cls._pipeline_payload_from_job_metadata(job_metadata)
        queue_status = _normalize_optional_string(pipeline_payload.get("queue_status"))
        if queue_status is not None:
            return queue_status
        return _normalize_optional_string(pipeline_payload.get("status"))

    @classmethod
    def _resolve_pipeline_next_attempt_at(cls, job_metadata: object) -> datetime | None:
        pipeline_payload = cls._pipeline_payload_from_job_metadata(job_metadata)
        return _parse_timestamp(pipeline_payload.get("next_attempt_at"))

    def find_by_id(
        self: IngestionJobRepositoryContext,
        job_id: UUID,
    ) -> IngestionJob | None:
        stmt = select(IngestionJobModel).where(IngestionJobModel.id == str(job_id))
        model = self.session.execute(stmt).scalar_one_or_none()
        return IngestionJobMapper.to_domain(model) if model else None

    def _fetch(
        self: IngestionJobRepositoryContext,
        stmt: Select[tuple[IngestionJobModel]],
    ) -> list[IngestionJob]:
        logger = logging.getLogger(__name__)
        try:
            models = self.session.execute(stmt).scalars().all()
        except (OperationalError, ProgrammingError) as exc:
            if not is_missing_optional_column_error(exc):
                raise
            logger.warning(
                "Ingestion job optional columns are unavailable; returning empty history list",
                exc_info=exc,
            )
            self.session.rollback()
            return []
        return [IngestionJobMapper.to_domain(model) for model in models]

    def find_by_source(
        self: IngestionJobRepositoryContext,
        source_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[IngestionJob]:
        stmt = (
            select(IngestionJobModel)
            .where(IngestionJobModel.source_id == str(source_id))
            .order_by(desc(IngestionJobModel.triggered_at))
            .offset(skip)
            .limit(limit)
        )
        return self._fetch(stmt)

    def find_latest_by_source_and_kind(
        self: IngestionJobRepositoryContext,
        *,
        source_id: UUID,
        job_kind: IngestionJobKind,
        limit: int = 50,
    ) -> list[IngestionJob]:
        stmt = (
            select(IngestionJobModel)
            .where(IngestionJobModel.source_id == str(source_id))
            .where(
                IngestionJobModel.job_kind == IngestionJobKindEnum(job_kind.value),
            )
            .order_by(desc(IngestionJobModel.triggered_at))
            .limit(limit)
        )
        return self._fetch(stmt)

    def find_by_trigger(
        self: IngestionJobRepositoryContext,
        trigger: IngestionTrigger,
        skip: int = 0,
        limit: int = 50,
    ) -> list[IngestionJob]:
        stmt = (
            select(IngestionJobModel)
            .where(IngestionJobModel.trigger == IngestionTriggerEnum(trigger.value))
            .order_by(desc(IngestionJobModel.triggered_at))
            .offset(skip)
            .limit(limit)
        )
        return self._fetch(stmt)

    def find_by_status(
        self: IngestionJobRepositoryContext,
        status: IngestionStatus,
        skip: int = 0,
        limit: int = 50,
    ) -> list[IngestionJob]:
        stmt = (
            select(IngestionJobModel)
            .where(IngestionJobModel.status == IngestionStatusEnum(status.value))
            .order_by(desc(IngestionJobModel.triggered_at))
            .offset(skip)
            .limit(limit)
        )
        return self._fetch(stmt)

    def find_running_jobs(
        self: IngestionJobRepositoryContext,
        skip: int = 0,
        limit: int = 50,
    ) -> list[IngestionJob]:
        return self.find_by_status(IngestionStatus.RUNNING, skip, limit)

    def find_failed_jobs(
        self: IngestionJobRepositoryContext,
        since: datetime | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[IngestionJob]:
        stmt = select(IngestionJobModel).where(
            IngestionJobModel.status == IngestionStatusEnum.FAILED,
        )
        if since:
            stmt = stmt.where(
                IngestionJobModel.triggered_at
                >= IngestionJobMapper.serialize_timestamp(since),
            )
        stmt = (
            stmt.order_by(desc(IngestionJobModel.triggered_at))
            .offset(skip)
            .limit(limit)
        )
        return self._fetch(stmt)

    def find_recent_jobs(
        self: IngestionJobRepositoryContext,
        hours: int = 24,
        skip: int = 0,
        limit: int = 50,
    ) -> list[IngestionJob]:
        threshold = datetime.now(UTC) - timedelta(hours=hours)
        stmt = (
            select(IngestionJobModel)
            .where(
                IngestionJobModel.triggered_at
                >= IngestionJobMapper.serialize_timestamp(threshold),
            )
            .order_by(desc(IngestionJobModel.triggered_at))
            .offset(skip)
            .limit(limit)
        )
        return self._fetch(stmt)

    def find_by_triggered_by(
        self: IngestionJobRepositoryContext,
        user_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[IngestionJob]:
        stmt = (
            select(IngestionJobModel)
            .where(IngestionJobModel.triggered_by == str(user_id))
            .order_by(desc(IngestionJobModel.triggered_at))
            .offset(skip)
            .limit(limit)
        )
        return self._fetch(stmt)
