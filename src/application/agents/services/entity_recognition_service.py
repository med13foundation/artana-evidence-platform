"""Application service for Tier-3 entity recognition orchestration."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal

from src.application.agents.services._entity_recognition_bootstrap_helpers import (
    _EntityRecognitionBootstrapHelpers,
)
from src.application.agents.services._entity_recognition_metadata_helpers import (
    _EntityRecognitionMetadataHelpers,
)
from src.application.agents.services._entity_recognition_processing_helpers import (
    _EntityRecognitionProcessingContext,
    _EntityRecognitionProcessingHelpers,
)
from src.application.agents.services._entity_recognition_runtime_helpers import (
    _EntityRecognitionRuntimeHelpers,
)
from src.application.agents.services.governance_service import (
    GovernanceService,
)
from src.type_definitions.ingestion import RawRecord
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from uuid import UUID

    from artana_evidence_db.semantic_ports import DictionaryPort

    from src.application.agents.services.extraction_service import (
        ExtractionService,
    )
    from src.application.services.pipeline_run_trace_service import (
        PipelineRunTraceService,
    )
    from src.application.services.ports.ingestion_pipeline_port import (
        IngestionPipelinePort,
    )
    from src.domain.agents.contracts.entity_recognition import EntityRecognitionContract
    from src.domain.agents.graph_domain_ai_contracts import (
        EntityRecognitionBootstrapConfig,
    )
    from src.domain.agents.ports.entity_recognition_port import EntityRecognitionPort
    from src.domain.entities.source_document import SourceDocument
    from src.domain.repositories.research_space_repository import (
        ResearchSpaceRepository,
    )
    from src.domain.repositories.source_document_repository import (
        SourceDocumentRepository,
    )
    from src.type_definitions.common import JSONObject, ResearchSpaceSettings

logger = logging.getLogger(__name__)

_AGENT_CREATED_BY = "agent:entity_recognition"
_ENV_AGENT_TIMEOUT_SECONDS = "ARTANA_ENTITY_RECOGNITION_AGENT_TIMEOUT_SECONDS"
_ENV_EXTRACTION_STAGE_TIMEOUT_SECONDS = (
    "ARTANA_ENTITY_RECOGNITION_EXTRACTION_STAGE_TIMEOUT_SECONDS"
)
_ENV_STALE_IN_PROGRESS_SECONDS = "ARTANA_ENTITY_RECOGNITION_STALE_IN_PROGRESS_SECONDS"
_ENV_BATCH_MAX_CONCURRENCY = "ARTANA_ENTITY_RECOGNITION_BATCH_MAX_CONCURRENCY"
_ENV_AGENT_TIMEOUT_RETRY_ATTEMPTS = (
    "ARTANA_ENTITY_RECOGNITION_AGENT_TIMEOUT_RETRY_ATTEMPTS"
)
_ENV_AGENT_TIMEOUT_RETRY_BACKOFF_SECONDS = (
    "ARTANA_ENTITY_RECOGNITION_AGENT_TIMEOUT_RETRY_BACKOFF_SECONDS"
)
_ENV_AGENT_RAW_RECORD_MAX_TEXT_CHARS = (
    "ARTANA_ENTITY_RECOGNITION_AGENT_RAW_RECORD_MAX_TEXT_CHARS"
)
_DEFAULT_AGENT_TIMEOUT_SECONDS = 180.0
_DEFAULT_EXTRACTION_STAGE_TIMEOUT_SECONDS = 300.0
_DEFAULT_STALE_IN_PROGRESS_SECONDS = 900.0
_DEFAULT_BATCH_MAX_CONCURRENCY = 2
_DEFAULT_AGENT_TIMEOUT_RETRY_ATTEMPTS = 1
_DEFAULT_AGENT_TIMEOUT_RETRY_BACKOFF_SECONDS = 0.5
_DEFAULT_AGENT_RAW_RECORD_MAX_TEXT_CHARS = 20000
_BLOCKED_GRAPH_FALLBACK_REASONS = frozenset(
    {
        "relation_evidence_span_missing",
        "relation_endpoint_shape_rejected",
    },
)


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


def _read_non_negative_int(
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
    if parsed < 0:
        logger.warning(
            "Negative integer override in %s=%r; using default %d",
            env_name,
            raw_value,
            default_value,
        )
        return default_value
    return parsed


@dataclass(frozen=True)
class EntityRecognitionServiceDependencies:
    """Dependencies required by the entity-recognition orchestration service."""

    entity_recognition_agent: EntityRecognitionPort
    source_document_repository: SourceDocumentRepository
    ingestion_pipeline: IngestionPipelinePort
    dictionary_service: DictionaryPort
    entity_recognition_bootstrap: EntityRecognitionBootstrapConfig
    extraction_service: ExtractionService | None = None
    governance_service: GovernanceService | None = None
    research_space_repository: ResearchSpaceRepository | None = None
    pipeline_trace_service: PipelineRunTraceService | None = None


@dataclass(frozen=True)
class EntityRecognitionDocumentOutcome:
    """Outcome of processing a single source document."""

    document_id: UUID
    status: Literal["extracted", "failed", "skipped"]
    reason: str
    review_required: bool
    shadow_mode: bool
    wrote_to_kernel: bool
    run_id: str | None = None
    dictionary_variables_created: int = 0
    dictionary_synonyms_created: int = 0
    dictionary_entity_types_created: int = 0
    ingestion_entities_created: int = 0
    ingestion_observations_created: int = 0
    relation_claims_count: int = 0
    pending_review_relations_count: int = 0
    undefined_relations_count: int = 0
    persisted_relations_count: int = 0
    concept_members_created_count: int = 0
    concept_aliases_created_count: int = 0
    concept_decisions_proposed_count: int = 0
    seed_entity_ids: tuple[str, ...] = ()
    graph_fallback_relation_payloads: tuple[JSONObject, ...] = ()
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class EntityRecognitionRunSummary:
    """Batch summary for processing pending source documents."""

    requested: int
    processed: int
    extracted: int
    failed: int
    skipped: int
    review_required: int
    shadow_runs: int
    dictionary_variables_created: int
    dictionary_synonyms_created: int
    dictionary_entity_types_created: int
    ingestion_entities_created: int
    ingestion_observations_created: int
    relation_claims_count: int
    pending_review_relations_count: int
    undefined_relations_count: int
    derived_graph_seed_entity_ids: tuple[str, ...]
    errors: tuple[str, ...]
    started_at: datetime
    completed_at: datetime
    persisted_relations_count: int = 0
    concept_members_created_count: int = 0
    concept_aliases_created_count: int = 0
    concept_decisions_proposed_count: int = 0
    derived_graph_fallback_relation_payloads: tuple[JSONObject, ...] = ()


class EntityRecognitionService(
    _EntityRecognitionProcessingHelpers,
    _EntityRecognitionRuntimeHelpers,
    _EntityRecognitionBootstrapHelpers,
    _EntityRecognitionMetadataHelpers,
    _EntityRecognitionProcessingContext,
):
    """Coordinate Document Store -> Entity Agent -> Governance -> Kernel ingestion."""

    def __init__(
        self,
        dependencies: EntityRecognitionServiceDependencies,
        *,
        default_shadow_mode: bool = True,
        agent_created_by: str = _AGENT_CREATED_BY,
    ) -> None:
        self._agent = dependencies.entity_recognition_agent
        self._source_documents = dependencies.source_document_repository
        self._ingestion_pipeline = dependencies.ingestion_pipeline
        self._dictionary = dependencies.dictionary_service
        self._entity_recognition_bootstrap = dependencies.entity_recognition_bootstrap
        self._extraction_service = dependencies.extraction_service
        self._governance = dependencies.governance_service or GovernanceService()
        self._research_spaces = dependencies.research_space_repository
        self._pipeline_trace = dependencies.pipeline_trace_service
        self._default_shadow_mode = default_shadow_mode
        normalized_created_by = agent_created_by.strip()
        self._agent_created_by = normalized_created_by or _AGENT_CREATED_BY
        self._agent_timeout_seconds = _read_positive_timeout_seconds(
            _ENV_AGENT_TIMEOUT_SECONDS,
            default_seconds=_DEFAULT_AGENT_TIMEOUT_SECONDS,
        )
        self._extraction_stage_timeout_seconds = _read_positive_timeout_seconds(
            _ENV_EXTRACTION_STAGE_TIMEOUT_SECONDS,
            default_seconds=_DEFAULT_EXTRACTION_STAGE_TIMEOUT_SECONDS,
        )
        self._stale_in_progress_seconds = _read_positive_timeout_seconds(
            _ENV_STALE_IN_PROGRESS_SECONDS,
            default_seconds=_DEFAULT_STALE_IN_PROGRESS_SECONDS,
        )
        self._batch_max_concurrency = _read_positive_int(
            _ENV_BATCH_MAX_CONCURRENCY,
            default_value=_DEFAULT_BATCH_MAX_CONCURRENCY,
        )
        self._agent_timeout_retry_attempts = _read_non_negative_int(
            _ENV_AGENT_TIMEOUT_RETRY_ATTEMPTS,
            default_value=_DEFAULT_AGENT_TIMEOUT_RETRY_ATTEMPTS,
        )
        self._agent_timeout_retry_backoff_seconds = _read_positive_timeout_seconds(
            _ENV_AGENT_TIMEOUT_RETRY_BACKOFF_SECONDS,
            default_seconds=_DEFAULT_AGENT_TIMEOUT_RETRY_BACKOFF_SECONDS,
        )
        self._agent_raw_record_max_text_chars = _read_positive_int(
            _ENV_AGENT_RAW_RECORD_MAX_TEXT_CHARS,
            default_value=_DEFAULT_AGENT_RAW_RECORD_MAX_TEXT_CHARS,
        )

    async def process_pending_documents(  # noqa: C901, PLR0913
        self,
        *,
        limit: int = 25,
        source_id: UUID | None = None,
        ingestion_job_id: UUID | None = None,
        research_space_id: UUID | None = None,
        source_type: str | None = None,
        model_id: str | None = None,
        shadow_mode: bool | None = None,
        pipeline_run_id: str | None = None,
    ) -> EntityRecognitionRunSummary:
        """Process pending extraction documents through entity recognition."""
        started_at = datetime.now(UTC)
        requested_limit = max(limit, 1)
        fetch_limit = requested_limit
        if ingestion_job_id is not None:
            fetch_limit = max(requested_limit * 20, 200)
        stale_cutoff = datetime.now(UTC) - timedelta(
            seconds=self._stale_in_progress_seconds,
        )
        recovered_stale_documents = 0
        try:
            recovered_stale_documents = (
                self._source_documents.recover_stale_in_progress_extraction(
                    stale_before=stale_cutoff,
                    source_id=source_id,
                    research_space_id=research_space_id,
                    ingestion_job_id=ingestion_job_id,
                    limit=max(fetch_limit, 100),
                )
            )
        except Exception:  # noqa: BLE001 - recovery should not block extraction
            logger.exception(
                "Entity recognition stale in-progress recovery sweep failed",
                extra={
                    "pipeline_run_id": pipeline_run_id,
                    "source_id": str(source_id) if source_id is not None else None,
                    "ingestion_job_id": (
                        str(ingestion_job_id) if ingestion_job_id is not None else None
                    ),
                    "research_space_id": (
                        str(research_space_id)
                        if research_space_id is not None
                        else None
                    ),
                    "stale_threshold_seconds": self._stale_in_progress_seconds,
                },
            )
        if recovered_stale_documents > 0:
            logger.warning(
                "Entity recognition recovered stale in-progress documents",
                extra={
                    "pipeline_run_id": pipeline_run_id,
                    "source_id": str(source_id) if source_id is not None else None,
                    "ingestion_job_id": (
                        str(ingestion_job_id) if ingestion_job_id is not None else None
                    ),
                    "research_space_id": (
                        str(research_space_id)
                        if research_space_id is not None
                        else None
                    ),
                    "recovered_documents": recovered_stale_documents,
                    "stale_threshold_seconds": self._stale_in_progress_seconds,
                },
            )
        normalized_source_type = (
            source_type.strip().lower() if isinstance(source_type, str) else None
        )
        pending_documents = self._source_documents.list_pending_extraction(
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
                event_type="extraction_batch_started",
                stage="extraction",
                scope_kind="run",
                message="Entity recognition batch started.",
                status="running",
                occurred_at=started_at,
                started_at=started_at,
                payload={
                    "requested_limit": requested_limit,
                    "candidate_count": len(pending_documents),
                    "recovered_stale_documents": recovered_stale_documents,
                    "batch_max_concurrency": self._batch_max_concurrency,
                },
            )
        logger.info(
            "Entity recognition batch started",
            extra={
                "pipeline_run_id": pipeline_run_id,
                "source_id": str(source_id) if source_id is not None else None,
                "ingestion_job_id": (
                    str(ingestion_job_id) if ingestion_job_id is not None else None
                ),
                "research_space_id": (
                    str(research_space_id) if research_space_id is not None else None
                ),
                "source_type": normalized_source_type,
                "requested_limit": requested_limit,
                "candidate_count": len(pending_documents),
                "recovered_stale_documents": recovered_stale_documents,
                "agent_timeout_seconds": self._agent_timeout_seconds,
                "extraction_stage_timeout_seconds": (
                    self._extraction_stage_timeout_seconds
                ),
                "stale_in_progress_seconds": self._stale_in_progress_seconds,
                "batch_max_concurrency": self._batch_max_concurrency,
            },
        )

        outcomes_by_index: list[EntityRecognitionDocumentOutcome | None] = [None] * len(
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
                            stage="extraction",
                            scope_kind="document",
                            scope_id=str(document.id),
                            message=(
                                "Extraction started for document "
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
                    logger.info(
                        "Entity recognition document started",
                        extra={
                            "document_id": str(document.id),
                            "pipeline_run_id": pipeline_run_id,
                            "source_id": str(document.source_id),
                            "ingestion_job_id": (
                                str(document.ingestion_job_id)
                                if document.ingestion_job_id is not None
                                else None
                            ),
                            "external_record_id": document.external_record_id,
                            "worker_count": worker_count,
                        },
                    )
                    try:
                        outcome = await self._process_document_entity(
                            document=document,
                            model_id=model_id,
                            shadow_mode=shadow_mode,
                            force=False,
                            pipeline_run_id=pipeline_run_id,
                        )
                    except (
                        Exception
                    ) as exc:  # noqa: BLE001 - isolate one document failure
                        logger.exception(
                            "Entity recognition unexpected document failure",
                            extra={
                                "document_id": str(document.id),
                                "pipeline_run_id": pipeline_run_id,
                                "error_class": type(exc).__name__,
                            },
                        )
                        self._persist_failed_document(
                            document=document,
                            run_id=None,
                            metadata_patch={
                                "entity_recognition_error": (
                                    "unexpected_batch_processing_error"
                                ),
                                "entity_recognition_batch_error_class": type(
                                    exc,
                                ).__name__,
                                "entity_recognition_batch_error_message": str(exc),
                                "pipeline_run_id": pipeline_run_id,
                            },
                        )
                        outcome = EntityRecognitionDocumentOutcome(
                            document_id=document.id,
                            status="failed",
                            reason="unexpected_batch_processing_error",
                            review_required=False,
                            shadow_mode=False,
                            wrote_to_kernel=False,
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
                            stage="extraction",
                            scope_kind="document",
                            scope_id=str(document.id),
                            message=(
                                "Extraction finished for document "
                                f"{document.external_record_id}."
                            ),
                            level="error" if outcome.status == "failed" else "info",
                            status=outcome.status,
                            agent_kind="entity_recognition",
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
                                "review_required": outcome.review_required,
                                "shadow_mode": outcome.shadow_mode,
                                "wrote_to_kernel": outcome.wrote_to_kernel,
                                "relation_claims_count": (
                                    outcome.relation_claims_count
                                ),
                                "pending_review_relations_count": (
                                    outcome.pending_review_relations_count
                                ),
                                "undefined_relations_count": (
                                    outcome.undefined_relations_count
                                ),
                                "persisted_relations_count": (
                                    outcome.persisted_relations_count
                                ),
                                "concept_members_created_count": (
                                    outcome.concept_members_created_count
                                ),
                                "concept_aliases_created_count": (
                                    outcome.concept_aliases_created_count
                                ),
                                "concept_decisions_proposed_count": (
                                    outcome.concept_decisions_proposed_count
                                ),
                                "dictionary_variables_created": (
                                    outcome.dictionary_variables_created
                                ),
                                "dictionary_synonyms_created": (
                                    outcome.dictionary_synonyms_created
                                ),
                                "dictionary_entity_types_created": (
                                    outcome.dictionary_entity_types_created
                                ),
                                "errors": list(outcome.errors),
                            },
                        )
                    logger.info(
                        "Entity recognition document finished",
                        extra={
                            "document_id": str(document.id),
                            "pipeline_run_id": pipeline_run_id,
                            "status": outcome.status,
                            "reason": outcome.reason,
                            "shadow_mode": outcome.shadow_mode,
                            "wrote_to_kernel": outcome.wrote_to_kernel,
                            "run_id": outcome.run_id,
                            "error_count": len(outcome.errors),
                        },
                    )

            await asyncio.gather(
                *(
                    _process_document_with_guard(index=index, document=document)
                    for index, document in enumerate(pending_documents)
                ),
            )

        outcomes: list[EntityRecognitionDocumentOutcome] = [
            outcome for outcome in outcomes_by_index if outcome is not None
        ]

        completed_at = datetime.now(UTC)
        summary = self._build_run_summary(
            outcomes=outcomes,
            requested=len(pending_documents),
            started_at=started_at,
            completed_at=completed_at,
        )
        logger.info(
            "Entity recognition batch finished",
            extra={
                "pipeline_run_id": pipeline_run_id,
                "requested": summary.requested,
                "processed": summary.processed,
                "extracted": summary.extracted,
                "failed": summary.failed,
                "skipped": summary.skipped,
                "review_required": summary.review_required,
                "shadow_runs": summary.shadow_runs,
                "persisted_relations_count": summary.persisted_relations_count,
                "concept_members_created_count": (
                    summary.concept_members_created_count
                ),
                "concept_aliases_created_count": (
                    summary.concept_aliases_created_count
                ),
                "concept_decisions_proposed_count": (
                    summary.concept_decisions_proposed_count
                ),
                "error_count": len(summary.errors),
                "duration_ms": int(
                    (completed_at - started_at).total_seconds() * 1000,
                ),
            },
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
                event_type="extraction_batch_finished",
                stage="extraction",
                scope_kind="run",
                message="Entity recognition batch finished.",
                level="error" if summary.failed > 0 else "info",
                status="completed" if summary.failed == 0 else "partial",
                occurred_at=completed_at,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=int((completed_at - started_at).total_seconds() * 1000),
                payload={
                    "requested": summary.requested,
                    "processed": summary.processed,
                    "extracted": summary.extracted,
                    "failed": summary.failed,
                    "skipped": summary.skipped,
                    "review_required": summary.review_required,
                    "shadow_runs": summary.shadow_runs,
                    "relation_claims_count": summary.relation_claims_count,
                    "pending_review_relations_count": (
                        summary.pending_review_relations_count
                    ),
                    "undefined_relations_count": (summary.undefined_relations_count),
                    "persisted_relations_count": summary.persisted_relations_count,
                    "concept_members_created_count": (
                        summary.concept_members_created_count
                    ),
                    "concept_aliases_created_count": (
                        summary.concept_aliases_created_count
                    ),
                    "concept_decisions_proposed_count": (
                        summary.concept_decisions_proposed_count
                    ),
                    "errors": list(summary.errors),
                },
            )
        return summary

    async def process_document(
        self,
        *,
        document_id: UUID,
        model_id: str | None = None,
        shadow_mode: bool | None = None,
        force: bool = False,
    ) -> EntityRecognitionDocumentOutcome:
        """Process a single source document by id."""
        document = self._source_documents.get_by_id(document_id)
        if document is None:
            message = f"Source document not found: {document_id}"
            raise LookupError(message)
        return await self._process_document_entity(
            document=document,
            model_id=model_id,
            shadow_mode=shadow_mode,
            force=force,
            pipeline_run_id=None,
        )

    async def close(self) -> None:
        """Release resources held by the underlying entity-recognition adapter."""
        await self._agent.close()
        if self._extraction_service is not None:
            await self._extraction_service.close()

    @staticmethod
    def _document_outcome(  # noqa: PLR0913
        *,
        document_id: UUID,
        status: Literal["extracted", "failed", "skipped"],
        reason: str,
        review_required: bool,
        shadow_mode: bool,
        wrote_to_kernel: bool,
        run_id: str | None = None,
        dictionary_variables_created: int = 0,
        dictionary_synonyms_created: int = 0,
        dictionary_entity_types_created: int = 0,
        ingestion_entities_created: int = 0,
        ingestion_observations_created: int = 0,
        relation_claims_count: int = 0,
        pending_review_relations_count: int = 0,
        undefined_relations_count: int = 0,
        persisted_relations_count: int = 0,
        concept_members_created_count: int = 0,
        concept_aliases_created_count: int = 0,
        concept_decisions_proposed_count: int = 0,
        seed_entity_ids: tuple[str, ...] = (),
        graph_fallback_relation_payloads: tuple[JSONObject, ...] = (),
        errors: tuple[str, ...] = (),
    ) -> EntityRecognitionDocumentOutcome:
        return EntityRecognitionDocumentOutcome(
            document_id=document_id,
            status=status,
            reason=reason,
            review_required=review_required,
            shadow_mode=shadow_mode,
            wrote_to_kernel=wrote_to_kernel,
            run_id=run_id,
            dictionary_variables_created=dictionary_variables_created,
            dictionary_synonyms_created=dictionary_synonyms_created,
            dictionary_entity_types_created=dictionary_entity_types_created,
            ingestion_entities_created=ingestion_entities_created,
            ingestion_observations_created=ingestion_observations_created,
            relation_claims_count=relation_claims_count,
            pending_review_relations_count=pending_review_relations_count,
            undefined_relations_count=undefined_relations_count,
            persisted_relations_count=persisted_relations_count,
            concept_members_created_count=concept_members_created_count,
            concept_aliases_created_count=concept_aliases_created_count,
            concept_decisions_proposed_count=concept_decisions_proposed_count,
            seed_entity_ids=seed_entity_ids,
            graph_fallback_relation_payloads=graph_fallback_relation_payloads,
            errors=errors,
        )

    def _resolve_research_space_settings(  # noqa: C901, PLR0912, PLR0915
        self,
        document: SourceDocument,
    ) -> ResearchSpaceSettings:
        if self._research_spaces is None or document.research_space_id is None:
            return {}
        space = self._research_spaces.find_by_id(document.research_space_id)
        if space is None:
            return {}
        raw_settings = space.settings
        settings: ResearchSpaceSettings = {}

        auto_approve = raw_settings.get("auto_approve")
        if isinstance(auto_approve, bool):
            settings["auto_approve"] = auto_approve

        require_review = raw_settings.get("require_review")
        if isinstance(require_review, bool):
            settings["require_review"] = require_review

        review_threshold = raw_settings.get("review_threshold")
        if isinstance(review_threshold, float | int):
            normalized = max(0.0, min(float(review_threshold), 1.0))
            settings["review_threshold"] = normalized

        relation_default_review_threshold = raw_settings.get(
            "relation_default_review_threshold",
        )
        if isinstance(relation_default_review_threshold, float | int):
            settings["relation_default_review_threshold"] = max(
                0.0,
                min(float(relation_default_review_threshold), 1.0),
            )

        raw_relation_review_thresholds = raw_settings.get("relation_review_thresholds")
        if isinstance(raw_relation_review_thresholds, dict):
            relation_review_thresholds: dict[str, float] = {}
            for (
                raw_relation_type,
                raw_threshold,
            ) in raw_relation_review_thresholds.items():
                if not isinstance(raw_relation_type, str):
                    continue
                normalized_relation_type = raw_relation_type.strip().upper()
                if not normalized_relation_type:
                    continue
                if isinstance(raw_threshold, float | int):
                    relation_review_thresholds[normalized_relation_type] = max(
                        0.0,
                        min(float(raw_threshold), 1.0),
                    )
            if relation_review_thresholds:
                settings["relation_review_thresholds"] = relation_review_thresholds

        relation_governance_mode = raw_settings.get("relation_governance_mode")
        if isinstance(relation_governance_mode, str):
            normalized_mode = relation_governance_mode.strip().upper()
            if normalized_mode == "HUMAN_IN_LOOP":
                settings["relation_governance_mode"] = "HUMAN_IN_LOOP"
            elif normalized_mode == "FULL_AUTO":
                settings["relation_governance_mode"] = "FULL_AUTO"

        creation_policy = raw_settings.get("dictionary_agent_creation_policy")
        if isinstance(creation_policy, str):
            normalized_policy = creation_policy.strip().upper()
            if normalized_policy == "ACTIVE":
                settings["dictionary_agent_creation_policy"] = "ACTIVE"
            elif normalized_policy == "PENDING_REVIEW":
                settings["dictionary_agent_creation_policy"] = "PENDING_REVIEW"

        raw_custom = raw_settings.get("custom")
        if isinstance(raw_custom, dict):
            custom: dict[str, str | int | float | bool | None] = {}
            for key, value in raw_custom.items():
                if isinstance(value, str | int | float | bool) or value is None:
                    custom[str(key)] = value
            if custom:
                settings["custom"] = custom

        return settings

    @staticmethod
    def _enforce_active_dictionary_creation_policy(
        settings: ResearchSpaceSettings,
    ) -> ResearchSpaceSettings:
        return {
            **settings,
            "dictionary_agent_creation_policy": "ACTIVE",
        }

    def _resolve_shadow_mode(
        self,
        *,
        override: bool | None,
        settings: ResearchSpaceSettings,
    ) -> bool:
        if isinstance(override, bool):
            return override

        custom = settings.get("custom")
        if isinstance(custom, dict):
            explicit = custom.get("entity_recognition_shadow_mode")
            if isinstance(explicit, bool):
                return explicit

        return self._default_shadow_mode

    @staticmethod
    def _extract_raw_record(document: SourceDocument) -> JSONObject:
        raw_record = document.metadata.get("raw_record")
        if not isinstance(raw_record, dict):
            return {}
        return {str(key): to_json_value(value) for key, value in raw_record.items()}

    def _prepare_agent_raw_record(self, raw_record: JSONObject) -> JSONObject:
        prepared = {str(key): to_json_value(value) for key, value in raw_record.items()}
        text_limit = self._agent_raw_record_max_text_chars
        for text_key in ("full_text", "text", "abstract", "title"):
            raw_text = prepared.get(text_key)
            if not isinstance(raw_text, str):
                continue
            if len(raw_text) <= text_limit:
                continue
            prepared[text_key] = raw_text[:text_limit]
            prepared[f"{text_key}_truncated"] = True
            prepared[f"{text_key}_original_length"] = len(raw_text)

        raw_authors = prepared.get("authors")
        if isinstance(raw_authors, list):
            prepared["authors"] = self._compact_authors(raw_authors)
        return prepared

    @staticmethod
    def _compact_authors(authors: list[object]) -> list[JSONObject]:
        compacted: list[JSONObject] = []
        for raw_author in authors[:25]:
            if isinstance(raw_author, dict):
                author_payload: JSONObject = {}
                for key in ("first_name", "last_name", "initials", "name"):
                    value = raw_author.get(key)
                    if isinstance(value, str) and value.strip():
                        author_payload[key] = value.strip()
                if author_payload:
                    compacted.append(author_payload)
            elif isinstance(raw_author, str) and raw_author.strip():
                compacted.append({"name": raw_author.strip()})
        return compacted

    def _apply_dictionary_mutations(  # noqa: C901, PLR0912, PLR0913
        self,
        *,
        contract: EntityRecognitionContract,
        raw_record: JSONObject,
        source_type: str,
        source_ref: str,
        research_space_settings: ResearchSpaceSettings,
    ) -> tuple[int, int, int]:
        mutation_settings = self._enforce_active_dictionary_creation_policy(
            research_space_settings,
        )
        (
            bootstrap_variables_created,
            bootstrap_entity_types_created,
        ) = self._ensure_domain_bootstrap(
            source_type=source_type,
            source_ref=source_ref,
            research_space_settings=mutation_settings,
        )

        if (
            contract.decision == "generated"
            and isinstance(contract.agent_run_id, str)
            and contract.agent_run_id.strip()
        ):
            (
                reconciled_variables,
                reconciled_synonyms,
                reconciled_entity_types,
            ) = self._reconcile_agent_dictionary_mutations(contract)
            return (
                reconciled_variables + bootstrap_variables_created,
                reconciled_synonyms,
                reconciled_entity_types + bootstrap_entity_types_created,
            )

        domain_context = self._infer_domain_context(source_type)
        created_entity_types = bootstrap_entity_types_created
        for entity in contract.recognized_entities:
            entity_type_id = self._normalize_identifier(
                entity.entity_type,
                prefix="ENTITY",
                max_length=64,
            )
            if self._dictionary.get_entity_type(entity_type_id) is not None:
                continue
            self._dictionary.create_entity_type(
                entity_type=entity_type_id,
                display_name=self._to_display_name(entity_type_id),
                description=(
                    f"Autogenerated entity type from {source_type} "
                    "entity-recognition run"
                ),
                domain_context=domain_context,
                created_by=self._agent_created_by,
                source_ref=source_ref,
                research_space_settings=mutation_settings,
            )
            created_entity_types += 1

        created_variables = bootstrap_variables_created
        created_synonyms = 0
        for observation in contract.recognized_observations:
            field_name = observation.field_name.strip()
            if not field_name:
                continue

            matched_variable = self._dictionary.resolve_synonym(field_name)
            variable_id = self._resolve_variable_id(
                explicit_variable_id=observation.variable_id,
                field_name=field_name,
            )
            resolved_variable = matched_variable
            if matched_variable is not None:
                if matched_variable.id != variable_id:
                    logger.info(
                        "Remapped observation field '%s' to existing variable '%s' "
                        "(ignored candidate '%s')",
                        field_name,
                        matched_variable.id,
                        variable_id,
                    )
            else:
                resolved_variable = self._dictionary.get_variable(variable_id)
                if resolved_variable is None:
                    resolved_variable = self._dictionary.create_variable(
                        variable_id=variable_id,
                        canonical_name=self._to_canonical_name(field_name),
                        display_name=self._to_display_name(field_name),
                        data_type=self._infer_data_type(observation.value),
                        domain_context=domain_context,
                        sensitivity="INTERNAL",
                        description=(
                            f"Autogenerated variable from {source_type} "
                            f"field '{field_name}'"
                        ),
                        created_by=self._agent_created_by,
                        source_ref=source_ref,
                        research_space_settings=mutation_settings,
                    )
                    created_variables += 1
            if resolved_variable is None:
                continue
            self._dictionary.create_synonym(
                variable_id=resolved_variable.id,
                synonym=field_name,
                source=source_type.lower(),
                created_by=self._agent_created_by,
                source_ref=source_ref,
                research_space_settings=mutation_settings,
            )
            created_synonyms += 1

        if not contract.recognized_observations and raw_record:
            for raw_field, raw_value in raw_record.items():
                if self._dictionary.resolve_synonym(raw_field) is not None:
                    continue
                variable_id = self._resolve_variable_id(
                    explicit_variable_id=None,
                    field_name=raw_field,
                )
                existing_variable = self._dictionary.get_variable(variable_id)
                if existing_variable is None:
                    existing_variable = self._dictionary.create_variable(
                        variable_id=variable_id,
                        canonical_name=self._to_canonical_name(raw_field),
                        display_name=self._to_display_name(raw_field),
                        data_type=self._infer_data_type(raw_value),
                        domain_context=domain_context,
                        sensitivity="INTERNAL",
                        description=(
                            f"Autogenerated fallback variable from {source_type} "
                            f"field '{raw_field}'"
                        ),
                        created_by=self._agent_created_by,
                        source_ref=source_ref,
                        research_space_settings=mutation_settings,
                    )
                    created_variables += 1
                self._dictionary.create_synonym(
                    variable_id=existing_variable.id,
                    synonym=raw_field,
                    source=source_type.lower(),
                    created_by=self._agent_created_by,
                    source_ref=source_ref,
                    research_space_settings=mutation_settings,
                )
                created_synonyms += 1

        return created_variables, created_synonyms, created_entity_types

    def _reconcile_agent_dictionary_mutations(
        self,
        contract: EntityRecognitionContract,
    ) -> tuple[int, int, int]:
        """
        Reconcile dictionary mutations already applied by the agent tool loop.

        When an agent run id is present we treat dictionary writes as in-agent
        side effects and avoid duplicating them in post-hoc service logic.
        """
        created_variables = 0
        for variable_id in set(contract.created_definitions):
            if self._dictionary.get_variable(variable_id) is not None:
                created_variables += 1

        created_synonyms = 0
        for synonym in set(contract.created_synonyms):
            if self._dictionary.resolve_synonym(synonym) is not None:
                created_synonyms += 1

        created_entity_types = 0
        for entity_type_id in set(contract.created_entity_types):
            if self._dictionary.get_entity_type(entity_type_id) is not None:
                created_entity_types += 1

        return created_variables, created_synonyms, created_entity_types

    def _build_pipeline_records(
        self,
        *,
        contract: EntityRecognitionContract,
        document: SourceDocument,
        raw_record: JSONObject,
        run_id: str | None,
    ) -> list[RawRecord]:
        payloads = contract.pipeline_payloads or [raw_record]
        records: list[RawRecord] = []
        for index, payload in enumerate(payloads):
            source_record_id = (
                document.external_record_id
                if index == 0
                else f"{document.external_record_id}:{index}"
            )
            metadata: JSONObject = {
                "type": document.source_type.value,
                "entity_type": contract.primary_entity_type,
                "source_document_id": str(document.id),
                "source_record_id": source_record_id,
                "agent_decision": contract.decision,
            }
            if run_id:
                metadata["entity_recognition_run_id"] = run_id

            normalized_payload: JSONObject = {
                str(key): to_json_value(value) for key, value in payload.items()
            }
            records.append(
                RawRecord(
                    source_id=source_record_id,
                    data=normalized_payload,
                    metadata=metadata,
                ),
            )
        return records

    @staticmethod
    def _build_run_summary(  # noqa: C901
        *,
        outcomes: list[EntityRecognitionDocumentOutcome],
        requested: int,
        started_at: datetime,
        completed_at: datetime,
    ) -> EntityRecognitionRunSummary:
        extracted = sum(1 for outcome in outcomes if outcome.status == "extracted")
        failed = sum(1 for outcome in outcomes if outcome.status == "failed")
        skipped = sum(1 for outcome in outcomes if outcome.status == "skipped")
        review_required = sum(1 for outcome in outcomes if outcome.review_required)
        shadow_runs = sum(1 for outcome in outcomes if outcome.shadow_mode)

        dictionary_variables_created = sum(
            outcome.dictionary_variables_created for outcome in outcomes
        )
        dictionary_synonyms_created = sum(
            outcome.dictionary_synonyms_created for outcome in outcomes
        )
        dictionary_entity_types_created = sum(
            outcome.dictionary_entity_types_created for outcome in outcomes
        )
        ingestion_entities_created = sum(
            outcome.ingestion_entities_created for outcome in outcomes
        )
        ingestion_observations_created = sum(
            outcome.ingestion_observations_created for outcome in outcomes
        )
        relation_claims_count = sum(
            outcome.relation_claims_count for outcome in outcomes
        )
        pending_review_relations_count = sum(
            outcome.pending_review_relations_count for outcome in outcomes
        )
        undefined_relations_count = sum(
            outcome.undefined_relations_count for outcome in outcomes
        )
        persisted_relations_count = sum(
            outcome.persisted_relations_count for outcome in outcomes
        )
        concept_members_created_count = sum(
            outcome.concept_members_created_count for outcome in outcomes
        )
        concept_aliases_created_count = sum(
            outcome.concept_aliases_created_count for outcome in outcomes
        )
        concept_decisions_proposed_count = sum(
            outcome.concept_decisions_proposed_count for outcome in outcomes
        )

        errors: list[str] = []
        for outcome in outcomes:
            errors.extend(outcome.errors)
        derived_graph_seed_entity_ids: list[str] = []
        derived_graph_fallback_relation_payloads: list[JSONObject] = []
        fallback_relation_keys: set[tuple[str, str, str, str]] = set()
        fallback_seed_ids: list[str] = []
        for outcome in outcomes:
            for raw_payload in outcome.graph_fallback_relation_payloads:
                seed_value = raw_payload.get("seed_entity_id")
                source_value = raw_payload.get("source_id")
                relation_value = raw_payload.get("relation_type")
                target_value = raw_payload.get("target_id")
                if (
                    not isinstance(
                        seed_value,
                        str,
                    )
                    or not isinstance(
                        source_value,
                        str,
                    )
                    or not isinstance(
                        relation_value,
                        str,
                    )
                    or not isinstance(
                        target_value,
                        str,
                    )
                ):
                    continue
                normalized_seed = seed_value.strip()
                normalized_source = source_value.strip()
                normalized_relation = relation_value.strip().upper()
                normalized_target = target_value.strip()
                if (
                    not normalized_seed
                    or not normalized_source
                    or not normalized_relation
                    or not normalized_target
                ):
                    continue
                relation_key = (
                    normalized_seed,
                    normalized_source,
                    normalized_relation,
                    normalized_target,
                )
                if relation_key in fallback_relation_keys:
                    continue
                fallback_relation_keys.add(relation_key)
                normalized_payload: JSONObject = {
                    str(key): to_json_value(value) for key, value in raw_payload.items()
                }
                derived_graph_fallback_relation_payloads.append(normalized_payload)
                if normalized_seed not in fallback_seed_ids:
                    fallback_seed_ids.append(normalized_seed)

        for seed_entity_id in fallback_seed_ids:
            if seed_entity_id in derived_graph_seed_entity_ids:
                continue
            derived_graph_seed_entity_ids.append(seed_entity_id)

        for outcome in outcomes:
            for seed_entity_id in outcome.seed_entity_ids:
                if seed_entity_id in derived_graph_seed_entity_ids:
                    continue
                derived_graph_seed_entity_ids.append(seed_entity_id)

        return EntityRecognitionRunSummary(
            requested=requested,
            processed=len(outcomes),
            extracted=extracted,
            failed=failed,
            skipped=skipped,
            review_required=review_required,
            shadow_runs=shadow_runs,
            dictionary_variables_created=dictionary_variables_created,
            dictionary_synonyms_created=dictionary_synonyms_created,
            dictionary_entity_types_created=dictionary_entity_types_created,
            ingestion_entities_created=ingestion_entities_created,
            ingestion_observations_created=ingestion_observations_created,
            relation_claims_count=relation_claims_count,
            pending_review_relations_count=pending_review_relations_count,
            undefined_relations_count=undefined_relations_count,
            persisted_relations_count=persisted_relations_count,
            concept_members_created_count=concept_members_created_count,
            concept_aliases_created_count=concept_aliases_created_count,
            concept_decisions_proposed_count=concept_decisions_proposed_count,
            derived_graph_seed_entity_ids=tuple(derived_graph_seed_entity_ids),
            derived_graph_fallback_relation_payloads=tuple(
                derived_graph_fallback_relation_payloads,
            ),
            errors=tuple(errors),
            started_at=started_at,
            completed_at=completed_at,
        )

    @classmethod
    def _build_graph_fallback_relation_payloads(  # noqa: C901, PLR0912, PLR0915
        cls,
        *,
        seed_entity_ids: tuple[str, ...],
        rejected_relation_details: tuple[JSONObject, ...],
    ) -> tuple[JSONObject, ...]:
        fallback_payloads: list[JSONObject] = []
        seen_keys: set[tuple[str, str, str, str]] = set()

        known_seed_ids: list[str] = []
        for seed_entity_id in seed_entity_ids:
            normalized_seed = seed_entity_id.strip()
            if not normalized_seed:
                continue
            if cls._try_parse_uuid(normalized_seed) is None:
                continue
            if normalized_seed in known_seed_ids:
                continue
            known_seed_ids.append(normalized_seed)

        for detail in rejected_relation_details:
            reason_value = detail.get("reason")
            normalized_reason = (
                reason_value.strip()
                if isinstance(reason_value, str) and reason_value.strip()
                else "rejected_relation_candidate"
            )
            reason_key = normalized_reason.lower()
            if any(
                blocked_reason in reason_key
                for blocked_reason in _BLOCKED_GRAPH_FALLBACK_REASONS
            ):
                continue

            payload_value = detail.get("payload")
            if not isinstance(payload_value, dict):
                continue
            source_value = payload_value.get("source_entity_id")
            target_value = payload_value.get("target_entity_id")
            relation_value = payload_value.get("relation_type")
            if (
                not isinstance(source_value, str)
                or not isinstance(target_value, str)
                or not isinstance(relation_value, str)
            ):
                continue
            normalized_source = source_value.strip()
            normalized_target = target_value.strip()
            normalized_relation = relation_value.strip().upper()
            if (
                not normalized_source
                or not normalized_target
                or not normalized_relation
                or normalized_source == normalized_target
            ):
                continue
            if cls._try_parse_uuid(normalized_source) is None:
                continue
            if cls._try_parse_uuid(normalized_target) is None:
                continue

            validation_state_value = payload_value.get("validation_state")
            normalized_validation_state = (
                validation_state_value.strip().upper()
                if isinstance(validation_state_value, str)
                and validation_state_value.strip()
                else "UNDEFINED"
            )

            confidence_value = payload_value.get("confidence")
            if isinstance(confidence_value, bool):
                normalized_confidence = 0.35
            elif isinstance(confidence_value, float | int):
                normalized_confidence = max(
                    0.05,
                    min(float(confidence_value), 0.49),
                )
            else:
                normalized_confidence = 0.35

            evidence_summary = (
                "Promoted from extraction relation candidate "
                f"({normalized_validation_state}:{normalized_reason}) for graph "
                "fallback review."
            )

            endpoint_seed_ids: list[str] = []
            for endpoint_seed in (normalized_source, normalized_target):
                if endpoint_seed not in endpoint_seed_ids:
                    endpoint_seed_ids.append(endpoint_seed)
            for known_seed_id in known_seed_ids:
                if known_seed_id in endpoint_seed_ids:
                    continue
                if known_seed_id not in {normalized_source, normalized_target}:
                    continue
                endpoint_seed_ids.append(known_seed_id)

            for endpoint_seed in endpoint_seed_ids:
                relation_key = (
                    endpoint_seed,
                    normalized_source,
                    normalized_relation,
                    normalized_target,
                )
                if relation_key in seen_keys:
                    continue
                seen_keys.add(relation_key)
                fallback_payloads.append(
                    {
                        "seed_entity_id": endpoint_seed,
                        "source_id": normalized_source,
                        "relation_type": normalized_relation,
                        "target_id": normalized_target,
                        "confidence": normalized_confidence,
                        "reason": normalized_reason,
                        "validation_state": normalized_validation_state,
                        "evidence_summary": evidence_summary,
                    },
                )

        return tuple(fallback_payloads)


__all__ = [
    "EntityRecognitionDocumentOutcome",
    "EntityRecognitionRunSummary",
    "EntityRecognitionService",
    "EntityRecognitionServiceDependencies",
]
