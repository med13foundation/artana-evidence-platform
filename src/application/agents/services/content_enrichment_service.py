"""Application service for Tier-2 content-enrichment orchestration."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from src.application.agents.services._content_enrichment_contract_helpers import (
    _ContentEnrichmentContractHelpers,
)
from src.application.agents.services._content_enrichment_helpers import (
    PASS_THROUGH_SOURCE_TYPES,
    build_content_enrichment_context,
    build_metadata_patch,
    merge_metadata,
    resolve_run_id,
)
from src.application.agents.services._content_enrichment_storage_helpers import (
    _ContentEnrichmentStorageHelpers,
)
from src.application.agents.services._content_enrichment_types import (
    ContentEnrichmentDocumentOutcome,
    ContentEnrichmentRunSummary,
)
from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.content_enrichment import ContentEnrichmentContract
from src.domain.entities.source_document import EnrichmentStatus, SourceDocument

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.services.pipeline_run_trace_service import (
        PipelineRunTraceService,
    )
    from src.application.services.storage_operation_coordinator import (
        StorageOperationCoordinator,
    )
    from src.domain.agents.ports.content_enrichment_port import ContentEnrichmentPort
    from src.domain.repositories.source_document_repository import (
        SourceDocumentRepository,
    )

logger = logging.getLogger(__name__)

_ENV_AGENT_TIMEOUT_SECONDS = "ARTANA_CONTENT_ENRICHMENT_AGENT_TIMEOUT_SECONDS"
_ENV_BATCH_MAX_CONCURRENCY = "ARTANA_CONTENT_ENRICHMENT_BATCH_MAX_CONCURRENCY"
_DEFAULT_AGENT_TIMEOUT_SECONDS = 180.0
_DEFAULT_BATCH_MAX_CONCURRENCY = 4


def _read_positive_timeout_seconds(
    env_name: str,
    *,
    default_seconds: float,
) -> float:
    raw_value = os.getenv(env_name)
    if raw_value is None:
        return default_seconds
    try:
        parsed = float(raw_value)
    except ValueError:
        logger.warning(
            "Invalid timeout override in %s=%r; using default %.1fs",
            env_name,
            raw_value,
            default_seconds,
        )
        return default_seconds
    if parsed <= 0:
        logger.warning(
            "Non-positive timeout override in %s=%r; using default %.1fs",
            env_name,
            raw_value,
            default_seconds,
        )
        return default_seconds
    return parsed


def _read_positive_int(
    env_name: str,
    *,
    default_value: int,
) -> int:
    raw_value = os.getenv(env_name)
    if raw_value is None:
        return default_value
    try:
        parsed = int(raw_value)
    except ValueError:
        logger.warning(
            "Invalid integer override in %s=%r; using default %d",
            env_name,
            raw_value,
            default_value,
        )
        return default_value
    if parsed <= 0:
        logger.warning(
            "Non-positive integer override in %s=%r; using default %d",
            env_name,
            raw_value,
            default_value,
        )
        return default_value
    return parsed


@dataclass(frozen=True)
class ContentEnrichmentServiceDependencies:
    source_document_repository: SourceDocumentRepository
    content_enrichment_agent: ContentEnrichmentPort | None = None
    storage_coordinator: StorageOperationCoordinator | None = None
    pipeline_trace_service: PipelineRunTraceService | None = None


class ContentEnrichmentService(
    _ContentEnrichmentStorageHelpers,
    _ContentEnrichmentContractHelpers,
):
    def __init__(
        self,
        dependencies: ContentEnrichmentServiceDependencies,
    ) -> None:
        self._agent = dependencies.content_enrichment_agent
        self._source_documents = dependencies.source_document_repository
        self._storage_coordinator = dependencies.storage_coordinator
        self._pipeline_trace = dependencies.pipeline_trace_service
        self._agent_timeout_seconds = _read_positive_timeout_seconds(
            _ENV_AGENT_TIMEOUT_SECONDS,
            default_seconds=_DEFAULT_AGENT_TIMEOUT_SECONDS,
        )
        self._batch_max_concurrency = _read_positive_int(
            _ENV_BATCH_MAX_CONCURRENCY,
            default_value=_DEFAULT_BATCH_MAX_CONCURRENCY,
        )

    async def process_pending_documents(  # noqa: PLR0913
        self,
        *,
        limit: int = 25,
        source_id: UUID | None = None,
        ingestion_job_id: UUID | None = None,
        research_space_id: UUID | None = None,
        source_type: str | None = None,
        model_id: str | None = None,
        pipeline_run_id: str | None = None,
    ) -> ContentEnrichmentRunSummary:
        started_at = datetime.now(UTC)
        requested_limit = max(limit, 1)
        fetch_limit = requested_limit
        if ingestion_job_id is not None:
            fetch_limit = max(requested_limit * 20, 200)
        normalized_source_type = (
            source_type.strip().lower() if isinstance(source_type, str) else None
        )
        pending_documents = self._source_documents.list_pending_enrichment(
            limit=fetch_limit,
            source_id=source_id,
            research_space_id=research_space_id,
            ingestion_job_id=ingestion_job_id,
            source_type=normalized_source_type,
        )
        pending_documents = sorted(
            pending_documents,
            key=lambda document: document.created_at,
            reverse=True,
        )[:requested_limit]

        if (
            self._pipeline_trace is not None
            and pipeline_run_id is not None
            and source_id is not None
            and research_space_id is not None
        ):
            self._pipeline_trace.record_event(
                research_space_id=research_space_id,
                source_id=source_id,
                pipeline_run_id=pipeline_run_id,
                event_type="enrichment_batch_started",
                stage="enrichment",
                scope_kind="run",
                message="Content enrichment batch started.",
                status="running",
                occurred_at=started_at,
                started_at=started_at,
                payload={
                    "requested_limit": requested_limit,
                    "candidate_count": len(pending_documents),
                },
            )

        outcomes_by_index: list[ContentEnrichmentDocumentOutcome | None] = [None] * len(
            pending_documents,
        )
        if pending_documents:
            worker_count = min(self._batch_max_concurrency, len(pending_documents))
            semaphore = asyncio.Semaphore(worker_count)

            async def _process_document_with_guard(
                *,
                index: int,
                document: SourceDocument,
            ) -> None:
                async with semaphore:
                    document_started_at = datetime.now(UTC)
                    if (
                        self._pipeline_trace is not None
                        and pipeline_run_id is not None
                        and document.research_space_id is not None
                    ):
                        self._pipeline_trace.record_event(
                            research_space_id=document.research_space_id,
                            source_id=document.source_id,
                            pipeline_run_id=pipeline_run_id,
                            event_type="document_started",
                            stage="enrichment",
                            scope_kind="document",
                            scope_id=str(document.id),
                            message=(
                                "Content enrichment started for document "
                                f"{document.external_record_id}."
                            ),
                            status="running",
                            occurred_at=document_started_at,
                            started_at=document_started_at,
                            payload={
                                "document_id": str(document.id),
                                "external_record_id": document.external_record_id,
                            },
                        )
                    try:
                        outcome = await self._process_document(
                            document=document,
                            model_id=model_id,
                            force=False,
                            pipeline_run_id=pipeline_run_id,
                        )
                    except (
                        Exception
                    ) as exc:  # noqa: BLE001 - isolate unexpected batch failures
                        logger.exception(
                            "Content enrichment unexpected document failure",
                            extra={
                                "document_id": str(document.id),
                                "pipeline_run_id": pipeline_run_id,
                                "error_class": type(exc).__name__,
                            },
                        )
                        failure_reason = "unexpected_batch_processing_error"
                        self._persist_document_with_status(
                            document=document,
                            status=EnrichmentStatus.FAILED,
                            run_id=None,
                            acquisition_method="skipped",
                            metadata_patch={
                                "content_enrichment_error": str(exc),
                                "content_enrichment_failure_reason": failure_reason,
                                "content_enrichment_batch_error_class": type(
                                    exc,
                                ).__name__,
                                "pipeline_run_id": pipeline_run_id,
                            },
                        )
                        outcome = ContentEnrichmentDocumentOutcome(
                            document_id=document.id,
                            status="failed",
                            execution_mode=self._resolve_execution_mode(
                                document=document,
                            ),
                            reason=failure_reason,
                            errors=(str(exc),),
                        )
                    outcomes_by_index[index] = outcome
                    document_completed_at = datetime.now(UTC)
                    if (
                        self._pipeline_trace is not None
                        and pipeline_run_id is not None
                        and document.research_space_id is not None
                    ):
                        self._pipeline_trace.record_event(
                            research_space_id=document.research_space_id,
                            source_id=document.source_id,
                            pipeline_run_id=pipeline_run_id,
                            event_type="document_finished",
                            stage="enrichment",
                            scope_kind="document",
                            scope_id=str(document.id),
                            message=(
                                "Content enrichment finished for document "
                                f"{document.external_record_id}."
                            ),
                            level="error" if outcome.status == "failed" else "info",
                            status=outcome.status,
                            agent_kind="content_enrichment",
                            agent_run_id=outcome.run_id,
                            occurred_at=document_completed_at,
                            started_at=document_started_at,
                            completed_at=document_completed_at,
                            duration_ms=int(
                                (
                                    document_completed_at - document_started_at
                                ).total_seconds()
                                * 1000,
                            ),
                            payload={
                                "document_id": str(document.id),
                                "external_record_id": document.external_record_id,
                                "reason": outcome.reason,
                                "execution_mode": outcome.execution_mode,
                                "acquisition_method": outcome.acquisition_method,
                                "content_storage_key": outcome.content_storage_key,
                                "content_length_chars": outcome.content_length_chars,
                                "errors": list(outcome.errors),
                            },
                        )

            await asyncio.gather(
                *(
                    _process_document_with_guard(index=index, document=document)
                    for index, document in enumerate(pending_documents)
                ),
            )

        outcomes: list[ContentEnrichmentDocumentOutcome] = [
            outcome for outcome in outcomes_by_index if outcome is not None
        ]

        completed_at = datetime.now(UTC)
        summary = self._build_run_summary(
            outcomes=outcomes,
            requested=len(pending_documents),
            started_at=started_at,
            completed_at=completed_at,
        )
        if (
            self._pipeline_trace is not None
            and pipeline_run_id is not None
            and source_id is not None
            and research_space_id is not None
        ):
            self._pipeline_trace.record_event(
                research_space_id=research_space_id,
                source_id=source_id,
                pipeline_run_id=pipeline_run_id,
                event_type="enrichment_batch_finished",
                stage="enrichment",
                scope_kind="run",
                message="Content enrichment batch finished.",
                level="error" if summary.failed > 0 else "info",
                status="completed" if summary.failed == 0 else "partial",
                occurred_at=completed_at,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=int((completed_at - started_at).total_seconds() * 1000),
                payload={
                    "requested": summary.requested,
                    "processed": summary.processed,
                    "enriched": summary.enriched,
                    "skipped": summary.skipped,
                    "failed": summary.failed,
                    "ai_runs": summary.ai_runs,
                    "deterministic_runs": summary.deterministic_runs,
                    "errors": list(summary.errors),
                },
            )
        return summary

    async def process_document(
        self,
        *,
        document_id: UUID,
        model_id: str | None = None,
        force: bool = False,
    ) -> ContentEnrichmentDocumentOutcome:
        document = self._source_documents.get_by_id(document_id)
        if document is None:
            msg = f"Source document not found: {document_id}"
            raise LookupError(msg)
        return await self._process_document(
            document=document,
            model_id=model_id,
            force=force,
            pipeline_run_id=None,
        )

    async def close(self) -> None:
        if self._agent is not None:
            await self._agent.close()

    async def _process_document(  # noqa: PLR0911
        self,
        *,
        document: SourceDocument,
        model_id: str | None,
        force: bool,
        pipeline_run_id: str | None,
    ) -> ContentEnrichmentDocumentOutcome:
        execution_mode = self._resolve_execution_mode(document=document)
        if not force and document.enrichment_status != EnrichmentStatus.PENDING:
            return ContentEnrichmentDocumentOutcome(
                document_id=document.id,
                status="skipped",
                execution_mode=execution_mode,
                reason=f"document_status={document.enrichment_status.value}",
            )

        try:
            contract = await self._build_contract(document=document, model_id=model_id)
        except TimeoutError:
            failure_reason = "agent_execution_timeout"
            self._persist_document_with_status(
                document=document,
                status=EnrichmentStatus.FAILED,
                run_id=None,
                acquisition_method="skipped",
                metadata_patch={
                    "content_enrichment_error": (
                        "content_enrichment_agent_timeout:"
                        f"{self._agent_timeout_seconds:.1f}s"
                    ),
                    "content_enrichment_failure_reason": failure_reason,
                    "content_enrichment_timeout_seconds": self._agent_timeout_seconds,
                    "pipeline_run_id": pipeline_run_id,
                },
            )
            return ContentEnrichmentDocumentOutcome(
                document_id=document.id,
                status="failed",
                execution_mode=execution_mode,
                reason=failure_reason,
                errors=(
                    "content_enrichment_agent_timeout:"
                    f"{self._agent_timeout_seconds:.1f}s",
                ),
            )
        except Exception as exc:  # noqa: BLE001
            failure_reason = "agent_execution_failed"
            self._persist_document_with_status(
                document=document,
                status=EnrichmentStatus.FAILED,
                run_id=None,
                acquisition_method="skipped",
                metadata_patch={
                    "content_enrichment_error": str(exc),
                    "content_enrichment_failure_reason": failure_reason,
                    "pipeline_run_id": pipeline_run_id,
                },
            )
            return ContentEnrichmentDocumentOutcome(
                document_id=document.id,
                status="failed",
                execution_mode=execution_mode,
                reason=failure_reason,
                errors=(str(exc),),
            )

        run_id = resolve_run_id(contract)

        full_text_validation_failure = self._validate_required_full_text_contract(
            document=document,
            contract=contract,
        )
        if full_text_validation_failure is not None:
            non_blocking_skip = self._should_treat_full_text_validation_as_skip(
                failure_reason=full_text_validation_failure,
                contract=contract,
            )
            persisted_status = (
                EnrichmentStatus.SKIPPED
                if non_blocking_skip
                else EnrichmentStatus.FAILED
            )
            outcome_status: Literal["skipped", "failed"] = (
                "skipped" if non_blocking_skip else "failed"
            )
            self._persist_document_with_status(
                document=document,
                status=persisted_status,
                run_id=run_id,
                acquisition_method=contract.acquisition_method,
                metadata_patch=build_metadata_patch(
                    contract=contract,
                    run_id=run_id,
                    pipeline_run_id=pipeline_run_id,
                    reason=full_text_validation_failure,
                    content_storage_key=None,
                    content_hash=None,
                ),
            )
            return ContentEnrichmentDocumentOutcome(
                document_id=document.id,
                status=outcome_status,
                execution_mode=execution_mode,
                reason=full_text_validation_failure,
                acquisition_method=contract.acquisition_method,
                run_id=run_id,
                errors=() if non_blocking_skip else (full_text_validation_failure,),
            )

        if contract.decision == "skipped":
            self._persist_document_with_status(
                document=document,
                status=EnrichmentStatus.SKIPPED,
                run_id=run_id,
                acquisition_method=contract.acquisition_method,
                metadata_patch=build_metadata_patch(
                    contract=contract,
                    run_id=run_id,
                    pipeline_run_id=pipeline_run_id,
                    reason="skipped",
                    content_storage_key=None,
                    content_hash=None,
                ),
            )
            return ContentEnrichmentDocumentOutcome(
                document_id=document.id,
                status="skipped",
                execution_mode=execution_mode,
                reason="skipped",
                acquisition_method=contract.acquisition_method,
                run_id=run_id,
            )

        if contract.decision == "failed":
            self._persist_document_with_status(
                document=document,
                status=EnrichmentStatus.FAILED,
                run_id=run_id,
                acquisition_method=contract.acquisition_method,
                metadata_patch=build_metadata_patch(
                    contract=contract,
                    run_id=run_id,
                    pipeline_run_id=pipeline_run_id,
                    reason="failed",
                    content_storage_key=None,
                    content_hash=None,
                ),
            )
            return ContentEnrichmentDocumentOutcome(
                document_id=document.id,
                status="failed",
                execution_mode=execution_mode,
                reason="failed",
                acquisition_method=contract.acquisition_method,
                run_id=run_id,
                errors=(contract.warning,) if contract.warning else (),
            )

        storage_result = await self._resolve_content_storage(
            document=document,
            contract=contract,
            run_id=run_id,
            pipeline_run_id=pipeline_run_id,
        )
        if storage_result is None:
            failure_reason = "missing_enriched_content"
            self._persist_document_with_status(
                document=document,
                status=EnrichmentStatus.FAILED,
                run_id=run_id,
                acquisition_method=contract.acquisition_method,
                metadata_patch=build_metadata_patch(
                    contract=contract,
                    run_id=run_id,
                    pipeline_run_id=pipeline_run_id,
                    reason=failure_reason,
                    content_storage_key=None,
                    content_hash=None,
                ),
            )
            return ContentEnrichmentDocumentOutcome(
                document_id=document.id,
                status="failed",
                execution_mode=execution_mode,
                reason=failure_reason,
                acquisition_method=contract.acquisition_method,
                run_id=run_id,
                errors=(failure_reason,),
            )

        updated = document.mark_enriched(
            enriched_storage_key=storage_result.storage_key,
            content_hash=storage_result.content_hash,
            content_length_chars=storage_result.content_length_chars,
            enrichment_method=contract.acquisition_method,
            enrichment_agent_run_id=run_id,
            enriched_at=datetime.now(UTC),
        )
        metadata_patch = build_metadata_patch(
            contract=contract,
            run_id=run_id,
            pipeline_run_id=pipeline_run_id,
            reason="enriched",
            content_storage_key=storage_result.storage_key,
            content_hash=storage_result.content_hash,
        )
        metadata_patch = merge_metadata(
            metadata_patch,
            self._build_extraction_input_patch(
                metadata=updated.metadata,
                contract=contract,
            ),
        )
        self._source_documents.upsert(
            updated.model_copy(
                update={
                    "metadata": merge_metadata(
                        updated.metadata,
                        metadata_patch,
                    ),
                },
            ),
        )

        return ContentEnrichmentDocumentOutcome(
            document_id=document.id,
            status="enriched",
            execution_mode=execution_mode,
            reason="enriched",
            acquisition_method=contract.acquisition_method,
            content_storage_key=storage_result.storage_key,
            content_length_chars=storage_result.content_length_chars,
            run_id=run_id,
            errors=(),
        )

    async def _build_contract(
        self,
        *,
        document: SourceDocument,
        model_id: str | None,
    ) -> ContentEnrichmentContract:
        if document.source_type in PASS_THROUGH_SOURCE_TYPES:
            return self._build_pass_through_contract(document=document)
        if self._agent is None:
            return ContentEnrichmentContract(
                decision="skipped",
                confidence_score=1.0,
                rationale=(
                    "Content-enrichment agent is disabled "
                    "(ARTANA_ENABLE_CONTENT_ENRICHMENT_AGENT != 1)."
                ),
                evidence=[
                    EvidenceItem(
                        source_type="note",
                        locator=f"document:{document.id}",
                        excerpt="Tier-2 agent execution skipped by configuration flag.",
                        relevance=1.0,
                    ),
                ],
                document_id=str(document.id),
                source_type=document.source_type.value,
                acquisition_method="skipped",
                content_format="text",
                content_length_chars=0,
                warning="Content-enrichment agent is disabled by configuration.",
                agent_run_id=None,
            )
        context = build_content_enrichment_context(document)
        return await asyncio.wait_for(
            self._agent.enrich(context, model_id=model_id),
            timeout=self._agent_timeout_seconds,
        )

    def _resolve_execution_mode(
        self,
        *,
        document: SourceDocument,
    ) -> Literal["ai", "deterministic"]:
        if document.source_type in PASS_THROUGH_SOURCE_TYPES:
            return "deterministic"
        if self._agent is None:
            return "deterministic"
        return "ai"


__all__ = [
    "ContentEnrichmentDocumentOutcome",
    "ContentEnrichmentRunSummary",
    "ContentEnrichmentService",
    "ContentEnrichmentServiceDependencies",
]
