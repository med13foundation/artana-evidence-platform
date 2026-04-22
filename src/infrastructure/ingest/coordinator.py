"""
Ingestion coordinator for Artana Resource Library.
Orchestrates parallel data ingestion from multiple biomedical sources.
"""

import asyncio
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from src.domain.value_objects import DataSource, Provenance
from src.type_definitions.common import JSONObject, JSONValue

from .base_ingestor import (
    BaseIngestor,
    IngestionError,
    IngestionResult,
    IngestionStatus,
)
from .clinvar_ingestor import ClinVarIngestor
from .hpo_ingestor import HPOIngestor
from .pubmed_ingestor import PubMedIngestor
from .uniprot_ingestor import UniProtIngestor


class IngestionPhase(Enum):
    """Phases of the ingestion process."""

    INITIALIZING = "initializing"
    INGESTING = "ingesting"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class IngestionTask:
    """Represents a single ingestion task."""

    source: str
    ingestor_class: Callable[[], BaseIngestor]
    parameters: dict[str, JSONValue]
    priority: int = 1  # Lower number = higher priority


@dataclass
class CoordinatorResult:
    """Result of coordinated ingestion across multiple sources."""

    total_sources: int
    completed_sources: int
    failed_sources: int
    total_records: int
    total_errors: int
    duration_seconds: float
    source_results: dict[str, IngestionResult]
    start_time: datetime
    end_time: datetime
    phase: IngestionPhase


class IngestionCoordinator:
    """
    Coordinates parallel data ingestion from multiple biomedical sources.

    Manages concurrent execution of ingestors, handles dependencies between
    data sources, and aggregates results with comprehensive error handling.
    """

    def __init__(
        self,
        max_concurrent_ingestors: int = 4,
        enable_parallel: bool = True,  # noqa: FBT001, FBT002
        progress_callback: Callable[[str, IngestionPhase, float], None] | None = None,
    ):
        self.max_concurrent_ingestors = max_concurrent_ingestors
        self.enable_parallel = enable_parallel
        self.progress_callback = progress_callback

        # Ingestion results storage
        self.results: dict[str, IngestionResult] = {}

        # Configure logging
        self.logger = logging.getLogger(__name__)

        # Thread pool for CPU-bound operations
        self.executor = ThreadPoolExecutor(max_workers=max_concurrent_ingestors)

    async def coordinate_ingestion(
        self,
        tasks: list[IngestionTask],
        **global_params: JSONValue,
    ) -> CoordinatorResult:
        start_time = datetime.now(UTC)

        # Update phase
        self._update_progress("all", IngestionPhase.INITIALIZING, 0.0)

        global_params_dict: dict[str, JSONValue] = dict(global_params)

        try:
            # Sort tasks by priority
            sorted_tasks = sorted(tasks, key=lambda t: t.priority)

            if self.enable_parallel:
                # Execute tasks in parallel with concurrency control
                results = await self._execute_parallel(sorted_tasks, global_params_dict)
            else:
                # Execute tasks sequentially
                results = await self._execute_sequential(
                    sorted_tasks,
                    global_params_dict,
                )

            # Aggregate results
            coordinator_result = self._aggregate_results(results, start_time)

        except Exception:
            self.logger.exception("Ingestion coordination failed")
            # Return failed result
            return CoordinatorResult(
                total_sources=len(tasks),
                completed_sources=0,
                failed_sources=len(tasks),
                total_records=0,
                total_errors=1,
                duration_seconds=(datetime.now(UTC) - start_time).total_seconds(),
                source_results={},
                start_time=start_time,
                end_time=datetime.now(UTC),
                phase=IngestionPhase.FAILED,
            )
        else:
            # Update final phase and return
            self._update_progress("all", IngestionPhase.COMPLETED, 100.0)
            return coordinator_result

    async def _execute_parallel(
        self,
        tasks: list[IngestionTask],
        global_params: dict[str, JSONValue],
    ) -> list[IngestionResult]:
        semaphore = asyncio.Semaphore(self.max_concurrent_ingestors)
        results: list[IngestionResult] = []

        async def execute_with_semaphore(task: IngestionTask) -> IngestionResult:
            async with semaphore:
                return await self._execute_single_task(task, global_params)

        # Create tasks
        execution_tasks = [execute_with_semaphore(task) for task in tasks]

        # Execute with progress tracking
        for completed, coro in enumerate(
            asyncio.as_completed(execution_tasks),
            start=1,
        ):
            result = await coro
            results.append(result)

            # Update progress
            progress = (completed / len(tasks)) * 100
            self._update_progress("all", IngestionPhase.INGESTING, progress)

        return results

    async def _execute_sequential(
        self,
        tasks: list[IngestionTask],
        global_params: dict[str, JSONValue],
    ) -> list[IngestionResult]:
        results: list[IngestionResult] = []

        for i, task in enumerate(tasks):
            result = await self._execute_single_task(task, global_params)
            results.append(result)

            # Update progress
            progress = ((i + 1) / len(tasks)) * 100
            self._update_progress("all", IngestionPhase.INGESTING, progress)

        return results

    async def _execute_single_task(
        self,
        task: IngestionTask,
        global_params: dict[str, JSONValue],
    ) -> IngestionResult:
        try:
            self.logger.info("Starting ingestion from %s", task.source)

            # Merge task parameters with global parameters
            task_params: dict[str, JSONValue] = {**global_params, **task.parameters}

            # Create and execute ingestor
            ingestor_instance: BaseIngestor = task.ingestor_class()
            async with ingestor_instance as ingestor:
                result = await ingestor.ingest(**task_params)

            self.logger.info(
                "Completed ingestion from %s: %d records processed, %d failed",
                task.source,
                result.records_processed,
                result.records_failed,
            )

            # Store result
            self.results[task.source] = result

        except Exception as e:
            self.logger.exception("Ingestion failed for %s", task.source)

            # Return failed result
            failed_provenance = Provenance(
                source=DataSource(task.source),
                source_version=None,
                source_url=None,
                acquired_at=datetime.now(UTC),
                acquired_by="MED13-Resource-Library-Coordinator",
                processing_steps=(f"Failed ingestion: {e!s}",),
                validation_status="failed",
                quality_score=0.0,
            )

            return IngestionResult(
                source=task.source,
                status=IngestionStatus.FAILED,
                records_processed=0,
                records_failed=1,
                data=[],
                provenance=failed_provenance,
                errors=[IngestionError(str(e), task.source)],
                duration_seconds=0.0,
                timestamp=datetime.now(UTC),
            )
        else:
            return result

    def _aggregate_results(
        self,
        results: list[IngestionResult],
        start_time: datetime,
    ) -> CoordinatorResult:
        total_sources = len(results)
        completed_sources = sum(
            1 for r in results if r.status == IngestionStatus.COMPLETED
        )
        failed_sources = total_sources - completed_sources

        total_records = sum(r.records_processed for r in results)
        total_errors = sum(len(r.errors) for r in results)

        # Group results by source
        source_results = {r.source: r for r in results}

        return CoordinatorResult(
            total_sources=total_sources,
            completed_sources=completed_sources,
            failed_sources=failed_sources,
            total_records=total_records,
            total_errors=total_errors,
            duration_seconds=(datetime.now(UTC) - start_time).total_seconds(),
            source_results=source_results,
            start_time=start_time,
            end_time=datetime.now(UTC),
            phase=IngestionPhase.COMPLETED,
        )

    def _update_progress(
        self,
        source: str,
        phase: IngestionPhase,
        progress: float,
    ) -> None:
        if self.progress_callback:
            self.progress_callback(source, phase, progress)

    async def ingest_all_sources(
        self,
        gene_symbol: str = "MED13",
        **global_params: JSONValue,
    ) -> CoordinatorResult:
        tasks = [
            IngestionTask(
                source="clinvar",
                ingestor_class=ClinVarIngestor,
                parameters={"gene_symbol": gene_symbol},
                priority=1,  # High priority
            ),
            IngestionTask(
                source="pubmed",
                ingestor_class=PubMedIngestor,
                parameters={"query": gene_symbol},
                priority=2,  # Medium priority
            ),
            IngestionTask(
                source="hpo",
                ingestor_class=HPOIngestor,
                parameters={"med13_only": True},
                priority=3,  # Lower priority (can be large)
            ),
            IngestionTask(
                source="uniprot",
                ingestor_class=UniProtIngestor,
                parameters={"query": gene_symbol},
                priority=1,  # High priority
            ),
        ]

        return await self.coordinate_ingestion(tasks, **global_params)

    async def ingest_critical_sources_only(
        self,
        gene_symbol: str = "MED13",
        **global_params: JSONValue,
    ) -> CoordinatorResult:
        tasks = [
            IngestionTask(
                source="clinvar",
                ingestor_class=ClinVarIngestor,
                parameters={"gene_symbol": gene_symbol},
                priority=1,
            ),
            IngestionTask(
                source="uniprot",
                ingestor_class=UniProtIngestor,
                parameters={"query": gene_symbol},
                priority=1,
            ),
        ]

        return await self.coordinate_ingestion(tasks, **global_params)

    def get_ingestion_summary(self, result: CoordinatorResult) -> JSONObject:
        source_details: dict[str, JSONObject] = {}

        for source, source_result in result.source_results.items():
            source_details[source] = {
                "status": source_result.status.name,
                "records_processed": source_result.records_processed,
                "records_failed": source_result.records_failed,
                "errors_count": len(source_result.errors),
                "duration_seconds": source_result.duration_seconds,
            }

        success_rate = (
            result.completed_sources / result.total_sources * 100
            if result.total_sources > 0
            else 0
        )
        records_per_second = (
            result.total_records / result.duration_seconds
            if result.duration_seconds > 0
            else 0
        )

        summary: JSONObject = {
            "total_sources": result.total_sources,
            "completed_sources": result.completed_sources,
            "failed_sources": result.failed_sources,
            "success_rate": success_rate,
            "total_records": result.total_records,
            "total_errors": result.total_errors,
            "duration_seconds": result.duration_seconds,
            "records_per_second": records_per_second,
            "source_details": source_details,
        }

        return summary

    async def retry_failed_sources(
        self,
        previous_result: CoordinatorResult,
        **retry_params: JSONValue,
    ) -> CoordinatorResult:
        failed_sources: list[str] = [
            source
            for source, result in previous_result.source_results.items()
            if result.status.name == "FAILED"
        ]

        if not failed_sources:
            # No failures to retry
            return previous_result

        self.logger.info("Retrying %d failed sources", len(failed_sources))

        # Create retry tasks (would need to reconstruct original task parameters)
        # For now, create basic retry tasks
        retry_tasks: list[IngestionTask] = []
        for source in failed_sources:
            if source == "clinvar":
                retry_tasks.append(
                    IngestionTask(
                        source=source,
                        ingestor_class=ClinVarIngestor,
                        parameters={"gene_symbol": "MED13"},
                        priority=1,
                    ),
                )
            elif source == "pubmed":
                retry_tasks.append(
                    IngestionTask(
                        source=source,
                        ingestor_class=PubMedIngestor,
                        parameters={"query": "MED13"},
                        priority=2,
                    ),
                )
            elif source == "hpo":
                retry_tasks.append(
                    IngestionTask(
                        source=source,
                        ingestor_class=HPOIngestor,
                        parameters={"med13_only": True},
                        priority=3,
                    ),
                )
            elif source == "uniprot":
                retry_tasks.append(
                    IngestionTask(
                        source=source,
                        ingestor_class=UniProtIngestor,
                        parameters={"query": "MED13"},
                        priority=1,
                    ),
                )

        return await self.coordinate_ingestion(retry_tasks, **retry_params)
