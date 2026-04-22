"""Application service coordinating scheduled ingestion across sources."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.application.services._ingestion_scheduling_core_helpers import (
    _IngestionSchedulingCoreHelpers,
)
from src.application.services._ingestion_scheduling_metadata_helpers import (
    _IngestionSchedulingMetadataHelpers,
)
from src.application.services._ingestion_scheduling_queue_helpers import (
    _IngestionSchedulingQueueHelpers,
)
from src.domain.entities import user_data_source
from src.domain.entities.ingestion_job import IngestionTrigger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping
    from datetime import datetime
    from uuid import UUID

    from src.application.services import (
        ExtractionQueueService,
        ExtractionRunnerService,
    )
    from src.application.services.ports.scheduler_port import (
        ScheduledJob,
        SchedulerPort,
    )
    from src.application.services.pubmed_discovery_service import PubMedDiscoveryService
    from src.domain.entities.user_data_source import UserDataSource
    from src.domain.repositories import (
        ingestion_job_repository,
        storage_repository,
        user_data_source_repository,
    )
    from src.domain.repositories import (
        ingestion_source_lock_repository as source_lock_repo,
    )
    from src.domain.repositories import (
        source_record_ledger_repository as source_record_ledger_repo,
    )
    from src.domain.repositories import (
        source_sync_state_repository as source_sync_state_repo,
    )
    from src.domain.services.ingestion import (
        IngestionProgressCallback,
        IngestionRunSummary,
    )


@dataclass(frozen=True)
class IngestionSchedulingOptions:
    storage_operation_repository: (
        storage_repository.StorageOperationRepository | None
    ) = None
    pubmed_discovery_service: PubMedDiscoveryService | None = None
    extraction_queue_service: ExtractionQueueService | None = None
    extraction_runner_service: ExtractionRunnerService | None = None
    source_sync_state_repository: (
        source_sync_state_repo.SourceSyncStateRepository | None
    ) = None
    source_record_ledger_repository: (
        source_record_ledger_repo.SourceRecordLedgerRepository | None
    ) = None
    scheduler_heartbeat_seconds: int = 30
    scheduler_lease_ttl_seconds: int = 120
    scheduler_stale_running_timeout_seconds: int = 300
    ingestion_job_hard_timeout_seconds: int = 7200
    post_ingestion_hook_timeout_seconds: int = 1800
    # Backward-compatible aliases retained while transitioning option names.
    source_lock_repository: source_lock_repo.IngestionSourceLockRepository | None = None
    source_lock_lease_ttl_seconds: int | None = None
    source_lock_heartbeat_seconds: int | None = None
    source_lock_owner: str = "ingestion-scheduler"
    source_ledger_retention_days: int | None = 180
    source_ledger_cleanup_batch_size: int = 1000
    retry_batch_size: int = 25
    post_ingestion_hook: (
        Callable[[UserDataSource, IngestionRunSummary], Awaitable[None]] | None
    ) = None


class IngestionSchedulingService(
    _IngestionSchedulingCoreHelpers,
    _IngestionSchedulingMetadataHelpers,
    _IngestionSchedulingQueueHelpers,
):
    """Coordinates scheduler registration and execution of ingestion jobs."""

    def __init__(
        self,
        scheduler: SchedulerPort,
        source_repository: user_data_source_repository.UserDataSourceRepository,
        job_repository: ingestion_job_repository.IngestionJobRepository,
        ingestion_services: Mapping[
            user_data_source.SourceType,
            Callable[..., Awaitable[IngestionRunSummary]],
        ],
        options: IngestionSchedulingOptions | None = None,
    ) -> None:
        resolved_options = options or IngestionSchedulingOptions()
        self._scheduler = scheduler
        self._source_repository = source_repository
        self._job_repository = job_repository
        self._ingestion_services = dict(ingestion_services)
        self._storage_operation_repository = (
            resolved_options.storage_operation_repository
        )
        self._pubmed_discovery_service = resolved_options.pubmed_discovery_service
        self._extraction_queue_service = resolved_options.extraction_queue_service
        self._extraction_runner_service = resolved_options.extraction_runner_service
        self._source_sync_state_repository = (
            resolved_options.source_sync_state_repository
        )
        self._source_record_ledger_repository = (
            resolved_options.source_record_ledger_repository
        )
        resolved_ingestion_hard_timeout_seconds = max(
            resolved_options.ingestion_job_hard_timeout_seconds,
            1,
        )
        resolved_scheduler_stale_timeout_seconds = max(
            resolved_options.scheduler_stale_running_timeout_seconds,
            1,
        )
        # Stale-running recovery must never preempt an in-flight job before the
        # configured hard timeout window.
        self._ingestion_job_hard_timeout_seconds = (
            resolved_ingestion_hard_timeout_seconds
        )
        self._scheduler_stale_running_timeout_seconds = max(
            resolved_scheduler_stale_timeout_seconds,
            resolved_ingestion_hard_timeout_seconds,
        )
        self._source_lock_repository = resolved_options.source_lock_repository
        resolved_lease_ttl_seconds = (
            resolved_options.source_lock_lease_ttl_seconds
            if resolved_options.source_lock_lease_ttl_seconds is not None
            else resolved_options.scheduler_lease_ttl_seconds
        )
        resolved_heartbeat_seconds = (
            resolved_options.source_lock_heartbeat_seconds
            if resolved_options.source_lock_heartbeat_seconds is not None
            else resolved_options.scheduler_heartbeat_seconds
        )
        self._source_lock_lease_ttl_seconds = max(
            resolved_lease_ttl_seconds,
            1,
        )
        self._source_lock_heartbeat_seconds = max(
            resolved_heartbeat_seconds,
            1,
        )
        self._source_lock_owner = (
            resolved_options.source_lock_owner.strip() or "ingestion-scheduler"
        )
        if resolved_options.source_ledger_retention_days is None:
            self._source_ledger_retention_days = None
        else:
            self._source_ledger_retention_days = max(
                resolved_options.source_ledger_retention_days,
                1,
            )
        self._source_ledger_cleanup_batch_size = max(
            resolved_options.source_ledger_cleanup_batch_size,
            1,
        )
        self._retry_batch_size = max(resolved_options.retry_batch_size, 1)
        self._post_ingestion_hook = resolved_options.post_ingestion_hook
        self._post_ingestion_hook_timeout_seconds = max(
            resolved_options.post_ingestion_hook_timeout_seconds,
            1,
        )

    def get_job_repository(self) -> ingestion_job_repository.IngestionJobRepository:
        """Expose the ingestion-job repository for cross-service orchestration."""
        return self._job_repository

    async def schedule_source(self, source_id: UUID) -> ScheduledJob:
        """Register a source with the scheduler backend."""
        source = self._get_source(source_id)
        self._assert_extraction_contract(source)
        schedule = source.ingestion_schedule
        if not schedule.requires_scheduler:
            msg = "Source schedule must be enabled with non-manual frequency"
            raise ValueError(msg)

        scheduled = self._scheduler.register_job(source_id, schedule)
        updated_schedule = schedule.model_copy(
            update={
                "backend_job_id": scheduled.job_id,
                "next_run_at": scheduled.next_run_at,
            },
        )
        self._source_repository.update_ingestion_schedule(source_id, updated_schedule)
        return scheduled

    def unschedule_source(self, source_id: UUID) -> None:
        """Remove a scheduled job for the given source if present."""
        source = self._get_source(source_id)
        job_id = source.ingestion_schedule.backend_job_id
        if job_id:
            self._scheduler.remove_job(job_id)
            updated = source.ingestion_schedule.model_copy(
                update={"backend_job_id": None, "next_run_at": None},
            )
            self._source_repository.update_ingestion_schedule(source_id, updated)

    async def run_due_jobs(self, *, as_of: datetime | None = None) -> None:
        """Execute all jobs that are due as of the provided timestamp."""
        self._recover_stale_running_jobs()
        due_jobs = self._scheduler.get_due_jobs(as_of=as_of)
        for job in due_jobs:
            await self._execute_job(job)
        await self._retry_failed_pdf_downloads()
        self._compact_source_record_ledger()

    async def trigger_ingestion(  # noqa: PLR0913
        self,
        source_id: UUID,
        *,
        skip_post_ingestion_hook: bool = False,
        skip_legacy_extraction_queue: bool = False,
        force_recover_lock: bool = False,
        pipeline_run_id: str | None = None,
        progress_callback: IngestionProgressCallback | None = None,
    ) -> IngestionRunSummary:
        """Manually trigger ingestion for a source outside scheduler cadence."""
        source = self._get_source(source_id)
        if source.status != user_data_source.SourceStatus.ACTIVE:
            msg = "Source must be active before ingestion can run"
            raise ValueError(msg)
        if not source.ingestion_schedule.requires_scheduler:
            msg = "Source must have an enabled non-manual ingestion schedule"
            raise ValueError(msg)
        return await self._run_ingestion_for_source(
            source,
            trigger=IngestionTrigger.API,
            skip_post_ingestion_hook=skip_post_ingestion_hook,
            skip_legacy_extraction_queue=skip_legacy_extraction_queue,
            force_recover_lock=force_recover_lock,
            pipeline_run_id=pipeline_run_id,
            progress_callback=progress_callback,
        )
