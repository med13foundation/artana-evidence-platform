"""Queueing and retry helpers for ingestion scheduling."""

# mypy: disable-error-code="misc"

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from src.application.services.pubmed_discovery_service import (
    PUBMED_STORAGE_METADATA_ARTICLE_ID_KEY,
    PUBMED_STORAGE_METADATA_JOB_ID_KEY,
    PUBMED_STORAGE_METADATA_OWNER_ID_KEY,
    PUBMED_STORAGE_METADATA_RETRYABLE_KEY,
    PUBMED_STORAGE_METADATA_USE_CASE_KEY,
    PubmedDownloadRequest,
)
from src.domain.entities import ingestion_job, user_data_source
from src.domain.services.ingestion import IngestionExtractionTarget
from src.domain.services.storage_providers import StorageOperationError
from src.domain.value_objects.provenance import DataSource as ProvenanceSource
from src.domain.value_objects.provenance import Provenance
from src.type_definitions import data_sources as data_source_types
from src.type_definitions.storage import StorageOperationRecord, StorageUseCase

if TYPE_CHECKING:
    from collections.abc import Mapping

    from src.application.services.ingestion_scheduling_service import (
        IngestionSchedulingService,
    )
    from src.domain.services.ingestion import IngestionRunSummary

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _PdfRetryContext:
    operation_id: UUID
    job_id: UUID
    owner_id: UUID
    article_id: str


class _IngestionSchedulingQueueHelpers:
    """Helpers for queue metadata, scheduling updates, and retries."""

    def _enqueue_extraction(
        self: IngestionSchedulingService,
        *,
        source: user_data_source.UserDataSource,
        ingestion_job_id: UUID,
        summary: IngestionRunSummary,
    ) -> data_source_types.IngestionExtractionQueueMetadata | None:
        if self._extraction_queue_service is None:
            return None

        summary_targets = self._collect_extraction_targets(summary)
        if not summary_targets:
            return None

        enqueue_summary = self._extraction_queue_service.enqueue_for_ingestion(
            source_id=source.id,
            ingestion_job_id=ingestion_job_id,
            targets=summary_targets,
        )
        return data_source_types.IngestionExtractionQueueMetadata(
            requested=enqueue_summary.requested,
            queued=enqueue_summary.queued,
            skipped=enqueue_summary.skipped,
            version=enqueue_summary.extraction_version,
        )

    @staticmethod
    def _collect_extraction_targets(
        summary: IngestionRunSummary,
    ) -> list[IngestionExtractionTarget]:
        raw_targets = getattr(summary, "extraction_targets", ())
        if not isinstance(raw_targets, list | tuple):
            return []
        deduped: dict[str, IngestionExtractionTarget] = {}
        for target in raw_targets:
            if not isinstance(target, IngestionExtractionTarget):
                continue
            source_record_id = target.source_record_id.strip()
            if not source_record_id:
                continue
            deduped[source_record_id] = target
        return list(deduped.values())

    async def _run_extraction(
        self: IngestionSchedulingService,
        *,
        source: user_data_source.UserDataSource,
        ingestion_job_id: UUID,
        queued_count: int,
    ) -> data_source_types.IngestionExtractionRunMetadata | None:
        if self._extraction_runner_service is None:
            return None
        if queued_count <= 0:
            return None
        summary = await self._extraction_runner_service.run_for_ingestion_job(
            source_id=source.id,
            ingestion_job_id=ingestion_job_id,
            expected_items=queued_count,
        )
        return data_source_types.IngestionExtractionRunMetadata(
            source_id=str(summary.source_id) if summary.source_id is not None else None,
            ingestion_job_id=(
                str(summary.ingestion_job_id)
                if summary.ingestion_job_id is not None
                else None
            ),
            requested=summary.requested,
            processed=summary.processed,
            completed=summary.completed,
            skipped=summary.skipped,
            failed=summary.failed,
            started_at=summary.started_at,
            completed_at=summary.completed_at,
        )

    def _create_ingestion_job(
        self: IngestionSchedulingService,
        source: user_data_source.UserDataSource,
        *,
        trigger: ingestion_job.IngestionTrigger = ingestion_job.IngestionTrigger.SCHEDULED,
    ) -> ingestion_job.IngestionJob:
        acquired_by = "ingestion-scheduler"
        processing_steps: tuple[str, ...] = ("scheduled_ingestion",)
        if trigger == ingestion_job.IngestionTrigger.API:
            acquired_by = "ingestion-api"
            processing_steps = ("api_triggered_ingestion",)
        return ingestion_job.IngestionJob(
            id=uuid4(),
            source_id=source.id,
            trigger=trigger,
            triggered_by=None,
            started_at=None,
            completed_at=None,
            provenance=Provenance(
                source=ProvenanceSource.COMPUTED,
                source_version=None,
                source_url=None,
                acquired_by=acquired_by,
                processing_steps=processing_steps,
                quality_score=None,
            ),
            metadata={},
            source_config_snapshot=source.configuration.model_dump(),
        )

    def _get_source(
        self: IngestionSchedulingService,
        source_id: UUID,
    ) -> user_data_source.UserDataSource:
        source = self._source_repository.find_by_id(source_id)
        if source is None:
            msg = f"Data source {source_id} not found"
            raise ValueError(msg)
        return source

    def _update_schedule_after_run(
        self: IngestionSchedulingService,
        source: user_data_source.UserDataSource,
    ) -> None:
        schedule = source.ingestion_schedule
        updates: dict[str, datetime | None] = {"last_run_at": datetime.now(UTC)}
        job_id = schedule.backend_job_id
        if job_id:
            job = self._scheduler.get_job(job_id)
            if job:
                updates["next_run_at"] = job.next_run_at
        updated_schedule = schedule.model_copy(update=updates)
        self._source_repository.update_ingestion_schedule(source.id, updated_schedule)

    def _compact_source_record_ledger(
        self: IngestionSchedulingService,
    ) -> None:
        repository = self._source_record_ledger_repository
        retention_days = self._source_ledger_retention_days
        if repository is None or retention_days is None:
            return
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        deleted_rows = repository.delete_entries_older_than(
            cutoff=cutoff,
            limit=self._source_ledger_cleanup_batch_size,
        )
        if deleted_rows <= 0:
            return
        logger.info(
            "Compacted stale source record ledger entries",
            extra={
                "deleted_rows": deleted_rows,
                "retention_days": retention_days,
                "cutoff": cutoff.isoformat(timespec="seconds"),
            },
        )

    async def _retry_failed_pdf_downloads(
        self: IngestionSchedulingService,
    ) -> None:
        """Retry failed PDF storage operations for PubMed discovery jobs."""
        if (
            self._storage_operation_repository is None
            or self._pubmed_discovery_service is None
        ):
            return

        operations = self._storage_operation_repository.list_failed_store_operations(
            limit=self._retry_batch_size,
        )
        for operation in operations:
            context = self._build_pdf_retry_context(operation)
            if context is None:
                continue
            job = self._pubmed_discovery_service.get_search_job(
                context.owner_id,
                context.job_id,
            )
            if job is None:
                self._mark_operation_retry_disabled(operation)
                continue

            if self._article_already_stored(job.result_metadata, context.article_id):
                self._mark_operation_retry_disabled(operation)
                continue

            try:
                await self._pubmed_discovery_service.download_article_pdf(
                    context.owner_id,
                    PubmedDownloadRequest(
                        job_id=context.job_id,
                        article_id=context.article_id,
                    ),
                )
            except (
                RuntimeError,
                ValueError,
                StorageOperationError,
            ):
                logger.warning(
                    "PubMed PDF retry failed",
                    extra={
                        "job_id": str(context.job_id),
                        "article_id": context.article_id,
                    },
                )
                continue
            else:
                self._mark_operation_retry_disabled(operation)

    @staticmethod
    def _article_already_stored(
        metadata: Mapping[str, object],
        article_id: str,
    ) -> bool:
        stored_assets = metadata.get("stored_assets")
        if not isinstance(stored_assets, dict):
            return False
        normalized_id = str(article_id)
        stored_keys = {str(key) for key in stored_assets}
        return normalized_id in stored_keys

    def _build_pdf_retry_context(
        self: IngestionSchedulingService,
        operation: StorageOperationRecord,
    ) -> _PdfRetryContext | None:
        metadata = operation.metadata or {}
        use_case = metadata.get(PUBMED_STORAGE_METADATA_USE_CASE_KEY)
        retryable = metadata.get(PUBMED_STORAGE_METADATA_RETRYABLE_KEY, True)
        if use_case != StorageUseCase.PDF.value or not bool(retryable):
            return None
        job_id_raw = metadata.get(PUBMED_STORAGE_METADATA_JOB_ID_KEY)
        owner_id_raw = metadata.get(PUBMED_STORAGE_METADATA_OWNER_ID_KEY)
        article_id_raw = metadata.get(PUBMED_STORAGE_METADATA_ARTICLE_ID_KEY)
        if not job_id_raw or not owner_id_raw or not article_id_raw:
            return None
        try:
            return _PdfRetryContext(
                operation_id=operation.id,
                job_id=UUID(str(job_id_raw)),
                owner_id=UUID(str(owner_id_raw)),
                article_id=str(article_id_raw),
            )
        except ValueError:
            return None

    def _mark_operation_retry_disabled(
        self: IngestionSchedulingService,
        operation: StorageOperationRecord,
    ) -> None:
        if self._storage_operation_repository is None:
            return
        metadata = (
            dict(operation.metadata) if isinstance(operation.metadata, dict) else {}
        )
        metadata[PUBMED_STORAGE_METADATA_RETRYABLE_KEY] = False
        metadata["retry_completed_at"] = datetime.now(UTC).isoformat()
        self._storage_operation_repository.update_operation_metadata(
            operation.id,
            metadata,
        )
