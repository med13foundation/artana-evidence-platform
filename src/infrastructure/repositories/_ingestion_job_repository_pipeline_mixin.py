"""Pipeline-queue methods for the ingestion job repository."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import desc, select

from src.domain.entities.ingestion_job import JobMetrics
from src.infrastructure.mappers.ingestion_job_mapper import IngestionJobMapper
from src.models.database.ingestion_job import (
    IngestionJobKindEnum,
    IngestionJobModel,
    IngestionStatusEnum,
)

from ._ingestion_job_repository_common import (
    _PIPELINE_ACTIVE_QUEUE_STATUSES,
    _PIPELINE_CLAIM_SCAN_LIMIT,
    _PIPELINE_CLAIMABLE_QUEUE_STATUSES,
    _coerce_json_object,
    _normalize_optional_string,
)

if TYPE_CHECKING:
    from uuid import UUID

    from src.domain.entities.ingestion_job import IngestionJob
    from src.type_definitions.common import JSONObject

    from ._ingestion_job_repository_common import IngestionJobRepositoryContext


class SqlAlchemyIngestionJobRepositoryPipelineMixin:
    """Pipeline queue and worker coordination methods."""

    @staticmethod
    def _build_pipeline_job_metadata_update(  # noqa: PLR0913
        *,
        existing_job_metadata: object,
        status: str,
        queue_status: str,
        updated_at: datetime,
        worker_id: str | None = None,
        next_attempt_at: datetime | None = None,
        last_error: str | None = None,
        error_category: str | None = None,
        attempt_count: int | None = None,
        heartbeat_at: datetime | None = None,
    ) -> JSONObject:
        metadata = _coerce_json_object(existing_job_metadata)
        pipeline_payload = _coerce_json_object(metadata.get("pipeline_run"))
        pipeline_payload["status"] = status
        pipeline_payload["queue_status"] = queue_status
        pipeline_payload["updated_at"] = IngestionJobMapper.serialize_timestamp(
            updated_at,
        )
        pipeline_payload["next_attempt_at"] = (
            IngestionJobMapper.serialize_timestamp(next_attempt_at)
            if next_attempt_at is not None
            else None
        )
        if worker_id is not None:
            pipeline_payload["worker_id"] = worker_id
        if last_error is not None:
            pipeline_payload["last_error"] = last_error
        if error_category is not None:
            pipeline_payload["error_category"] = error_category
        if attempt_count is not None:
            pipeline_payload["attempt_count"] = max(attempt_count, 0)
        if heartbeat_at is not None:
            pipeline_payload["heartbeat_at"] = IngestionJobMapper.serialize_timestamp(
                heartbeat_at,
            )
        metadata["pipeline_run"] = pipeline_payload
        return metadata

    def find_active_pipeline_job_for_source(
        self: IngestionJobRepositoryContext,
        *,
        source_id: UUID,
        exclude_run_id: str | None = None,
    ) -> IngestionJob | None:
        normalized_exclude_run_id = _normalize_optional_string(exclude_run_id)
        statement = (
            select(IngestionJobModel)
            .where(IngestionJobModel.source_id == str(source_id))
            .where(
                IngestionJobModel.job_kind
                == IngestionJobKindEnum.PIPELINE_ORCHESTRATION,
            )
            .where(
                IngestionJobModel.status.in_(
                    (
                        IngestionStatusEnum.PENDING,
                        IngestionStatusEnum.RUNNING,
                    ),
                ),
            )
            .order_by(desc(IngestionJobModel.triggered_at))
            .limit(_PIPELINE_CLAIM_SCAN_LIMIT)
        )
        candidates = self.session.execute(statement).scalars().all()
        for candidate in candidates:
            queue_status = self._resolve_pipeline_queue_status(candidate.job_metadata)
            if queue_status not in _PIPELINE_ACTIVE_QUEUE_STATUSES:
                continue
            candidate_run_id = self._resolve_pipeline_run_id(candidate.job_metadata)
            if (
                normalized_exclude_run_id is not None
                and candidate_run_id == normalized_exclude_run_id
            ):
                continue
            return IngestionJobMapper.to_domain(candidate)
        return None

    def count_active_pipeline_queue_jobs(
        self: IngestionJobRepositoryContext,
    ) -> int:
        statement = (
            select(IngestionJobModel)
            .where(
                IngestionJobModel.job_kind
                == IngestionJobKindEnum.PIPELINE_ORCHESTRATION,
            )
            .where(IngestionJobModel.status == IngestionStatusEnum.PENDING)
        )
        candidates = self.session.execute(statement).scalars().all()
        return sum(
            1
            for candidate in candidates
            if self._resolve_pipeline_queue_status(candidate.job_metadata)
            in {"queued", "retrying"}
        )

    def claim_next_pipeline_job(
        self: IngestionJobRepositoryContext,
        *,
        worker_id: str,
        as_of: datetime,
    ) -> IngestionJob | None:
        statement = (
            select(IngestionJobModel)
            .where(
                IngestionJobModel.job_kind
                == IngestionJobKindEnum.PIPELINE_ORCHESTRATION,
            )
            .where(IngestionJobModel.status == IngestionStatusEnum.PENDING)
            .order_by(IngestionJobModel.triggered_at.asc())
            .limit(_PIPELINE_CLAIM_SCAN_LIMIT)
            .with_for_update(skip_locked=True)
        )
        try:
            candidates = self.session.execute(statement).scalars().all()
            for candidate in candidates:
                queue_status = self._resolve_pipeline_queue_status(
                    candidate.job_metadata,
                )
                if queue_status not in _PIPELINE_CLAIMABLE_QUEUE_STATUSES:
                    continue
                next_attempt_at = self._resolve_pipeline_next_attempt_at(
                    candidate.job_metadata,
                )
                if next_attempt_at is not None and next_attempt_at > as_of:
                    continue
                candidate.status = IngestionStatusEnum.RUNNING
                candidate.started_at = IngestionJobMapper.serialize_timestamp(as_of)
                candidate.completed_at = None
                candidate.job_metadata = self._build_pipeline_job_metadata_update(
                    existing_job_metadata=candidate.job_metadata,
                    status="running",
                    queue_status="running",
                    updated_at=as_of,
                    worker_id=worker_id,
                    heartbeat_at=as_of,
                )
                self.session.commit()
                self.session.refresh(candidate)
                return IngestionJobMapper.to_domain(candidate)
            self.session.rollback()
        except Exception:
            self.session.rollback()
            raise
        return None

    def heartbeat_pipeline_job(
        self: IngestionJobRepositoryContext,
        *,
        job_id: UUID,
        worker_id: str,
        heartbeat_at: datetime,
    ) -> IngestionJob | None:
        model = self.session.get(IngestionJobModel, str(job_id))
        if model is None:
            return None
        if model.job_kind != IngestionJobKindEnum.PIPELINE_ORCHESTRATION:
            return None
        if model.status != IngestionStatusEnum.RUNNING:
            return None
        current_worker_id = _normalize_optional_string(
            self._pipeline_payload_from_job_metadata(model.job_metadata).get(
                "worker_id",
            ),
        )
        if current_worker_id is not None and current_worker_id != worker_id:
            return None
        model.job_metadata = self._build_pipeline_job_metadata_update(
            existing_job_metadata=model.job_metadata,
            status="running",
            queue_status="running",
            updated_at=heartbeat_at,
            worker_id=worker_id,
            heartbeat_at=heartbeat_at,
        )
        self.session.commit()
        self.session.refresh(model)
        return IngestionJobMapper.to_domain(model)

    def mark_pipeline_job_retryable(
        self: IngestionJobRepositoryContext,
        *,
        job_id: UUID,
        worker_id: str,
        next_attempt_at: datetime,
        last_error: str,
        error_category: str | None,
    ) -> IngestionJob | None:
        model = self.session.get(IngestionJobModel, str(job_id))
        if model is None:
            return None
        if model.job_kind != IngestionJobKindEnum.PIPELINE_ORCHESTRATION:
            return None
        pipeline_payload = self._pipeline_payload_from_job_metadata(model.job_metadata)
        current_worker_id = _normalize_optional_string(
            pipeline_payload.get("worker_id"),
        )
        if current_worker_id is not None and current_worker_id != worker_id:
            return None
        attempt_count_raw = pipeline_payload.get("attempt_count")
        attempt_count = attempt_count_raw if isinstance(attempt_count_raw, int) else 0
        model.status = IngestionStatusEnum.PENDING
        model.started_at = None
        model.completed_at = None
        model.metrics = JobMetrics(
            records_processed=0,
            records_failed=0,
            records_skipped=0,
            bytes_processed=0,
            api_calls_made=0,
            duration_seconds=None,
            records_per_second=None,
        ).model_dump(mode="json")
        model.errors = []
        model.job_metadata = self._build_pipeline_job_metadata_update(
            existing_job_metadata=model.job_metadata,
            status="retrying",
            queue_status="retrying",
            updated_at=datetime.now(UTC),
            worker_id=worker_id,
            next_attempt_at=next_attempt_at,
            last_error=last_error,
            error_category=error_category,
            attempt_count=attempt_count + 1,
        )
        self.session.commit()
        self.session.refresh(model)
        return IngestionJobMapper.to_domain(model)
