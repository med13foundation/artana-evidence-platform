"""Application service for running publication extraction jobs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.application.services._extraction_runner_helpers import (
    ExtractionBatchSummary,
    ExtractionRunnerBatchProcessor,
)

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.services.ports.extraction_processor_port import (
        ExtractionProcessorPort,
    )
    from src.application.services.storage_operation_coordinator import (
        StorageOperationCoordinator,
    )
    from src.domain.repositories import (
        ExtractionQueueRepository,
        PublicationExtractionRepository,
        PublicationRepository,
    )


@dataclass(frozen=True)
class ExtractionRunSummary:
    source_id: UUID | None
    ingestion_job_id: UUID | None
    requested: int
    processed: int
    completed: int
    skipped: int
    failed: int
    started_at: datetime
    completed_at: datetime

    def to_metadata(self) -> dict[str, object]:
        return {
            "source_id": str(self.source_id) if self.source_id else None,
            "ingestion_job_id": (
                str(self.ingestion_job_id) if self.ingestion_job_id else None
            ),
            "requested": self.requested,
            "processed": self.processed,
            "completed": self.completed,
            "skipped": self.skipped,
            "failed": self.failed,
            "started_at": self.started_at.isoformat(timespec="seconds"),
            "completed_at": self.completed_at.isoformat(timespec="seconds"),
        }


class ExtractionRunnerService:
    """Claims pending extraction queue items and processes them."""

    def __init__(  # noqa: PLR0913 - explicit dependencies keep orchestration clear
        self,
        *,
        queue_repository: ExtractionQueueRepository,
        publication_repository: PublicationRepository,
        extraction_repository: PublicationExtractionRepository,
        processor_registry: dict[str, ExtractionProcessorPort] | None = None,
        storage_coordinator: StorageOperationCoordinator | None = None,
        batch_size: int = 25,
    ) -> None:
        self._queue_repository = queue_repository
        self._publication_repository = publication_repository
        self._extraction_repository = extraction_repository
        self._processor_registry = {
            key.strip().lower(): value
            for key, value in (processor_registry or {}).items()
            if key.strip()
        }
        if not self._processor_registry:
            msg = (
                "ExtractionRunnerService requires explicit processor registration "
                "for each source_type"
            )
            raise ValueError(msg)
        self._storage_coordinator = storage_coordinator
        self._batch_size = max(batch_size, 1)

    def has_processor_for_source_type(self, source_type: str) -> bool:
        """Return whether a processor contract exists for the provided source type."""
        normalized_source_type = source_type.strip().lower()
        return bool(
            normalized_source_type
            and normalized_source_type in self._processor_registry,
        )

    async def run_for_ingestion_job(
        self,
        *,
        source_id: UUID,
        ingestion_job_id: UUID,
        expected_items: int,
        batch_size: int | None = None,
    ) -> ExtractionRunSummary:
        started_at = datetime.now(UTC)
        processed = 0
        completed = 0
        skipped = 0
        failed = 0
        batch_limit = batch_size or self._batch_size

        while True:
            batch = await self._run_batch(
                limit=batch_limit,
                source_id=source_id,
                ingestion_job_id=ingestion_job_id,
            )
            processed += batch.processed
            completed += batch.completed
            skipped += batch.skipped
            failed += batch.failed

            if batch.processed == 0:
                break
            if processed >= expected_items:
                break

        completed_at = datetime.now(UTC)
        return ExtractionRunSummary(
            source_id=source_id,
            ingestion_job_id=ingestion_job_id,
            requested=expected_items,
            processed=processed,
            completed=completed,
            skipped=skipped,
            failed=failed,
            started_at=started_at,
            completed_at=completed_at,
        )

    async def run_pending(
        self,
        *,
        limit: int | None = None,
        source_id: UUID | None = None,
        ingestion_job_id: UUID | None = None,
    ) -> ExtractionRunSummary:
        started_at = datetime.now(UTC)
        batch = await self._run_batch(
            limit=limit or self._batch_size,
            source_id=source_id,
            ingestion_job_id=ingestion_job_id,
        )
        completed_at = datetime.now(UTC)
        return ExtractionRunSummary(
            source_id=source_id,
            ingestion_job_id=ingestion_job_id,
            requested=batch.processed,
            processed=batch.processed,
            completed=batch.completed,
            skipped=batch.skipped,
            failed=batch.failed,
            started_at=started_at,
            completed_at=completed_at,
        )

    async def _run_batch(
        self,
        *,
        limit: int,
        source_id: UUID | None,
        ingestion_job_id: UUID | None,
    ) -> ExtractionBatchSummary:
        return await ExtractionRunnerBatchProcessor(
            queue_repository=self._queue_repository,
            publication_repository=self._publication_repository,
            extraction_repository=self._extraction_repository,
            processor_registry=self._processor_registry,
            storage_coordinator=self._storage_coordinator,
        ).run_batch(
            limit=limit,
            source_id=source_id,
            ingestion_job_id=ingestion_job_id,
        )


__all__ = ["ExtractionRunSummary", "ExtractionRunnerService"]
