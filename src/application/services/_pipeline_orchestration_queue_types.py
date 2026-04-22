"""Queue config, DTOs, protocols, and errors for pipeline orchestration."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from datetime import datetime
    from uuid import UUID

    from src.application.agents.services._content_enrichment_types import (
        ContentEnrichmentRunSummary,
    )
    from src.application.agents.services.content_enrichment_service import (
        ContentEnrichmentService,
    )
    from src.application.agents.services.entity_recognition_service import (
        EntityRecognitionRunSummary,
        EntityRecognitionService,
    )
    from src.application.agents.services.graph_connection_service import (
        GraphConnectionOutcome,
    )
    from src.application.services._pipeline_orchestration_contracts import (
        PipelineStageName,
    )
    from src.application.services.ingestion_scheduling_service import (
        IngestionSchedulingService,
    )
    from src.application.services.pipeline_run_trace_service import (
        PipelineRunTraceService,
    )
    from src.domain.agents.contracts.graph_connection import ProposedRelation
    from src.domain.agents.contracts.graph_search import GraphSearchContract
    from src.domain.repositories.ingestion_job_repository import IngestionJobRepository
    from src.domain.repositories.research_space_repository import (
        ResearchSpaceRepository,
    )

logger = logging.getLogger(__name__)

ENV_PIPELINE_QUEUE_MAX_SIZE = "ARTANA_PIPELINE_QUEUE_MAX_SIZE"
DEFAULT_PIPELINE_QUEUE_MAX_SIZE = 100
ENV_PIPELINE_QUEUE_RETRY_AFTER_SECONDS = "ARTANA_PIPELINE_QUEUE_RETRY_AFTER_SECONDS"
DEFAULT_PIPELINE_QUEUE_RETRY_AFTER_SECONDS = 30
ENV_PIPELINE_RETRY_MAX_ATTEMPTS = "ARTANA_PIPELINE_RETRY_MAX_ATTEMPTS"
DEFAULT_PIPELINE_RETRY_MAX_ATTEMPTS = 5
ENV_PIPELINE_RETRY_BASE_DELAY_SECONDS = "ARTANA_PIPELINE_RETRY_BASE_DELAY_SECONDS"
DEFAULT_PIPELINE_RETRY_BASE_DELAY_SECONDS = 30


class GraphConnectionExecutor(Protocol):
    """Minimal graph-connection interface needed by pipeline orchestration."""

    async def discover_connections_for_seed(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        seed_entity_id: str,
        source_id: str | None = None,
        source_type: str,
        model_id: str | None = None,
        relation_types: list[str] | None = None,
        max_depth: int = 2,
        shadow_mode: bool | None = None,
        pipeline_run_id: str | None = None,
        fallback_relations: tuple[ProposedRelation, ...] | None = None,
    ) -> GraphConnectionOutcome: ...


class GraphSearchExecutor(Protocol):
    """Minimal graph-search interface needed by pipeline orchestration."""

    async def search(  # noqa: PLR0913
        self,
        *,
        question: str,
        research_space_id: str,
        max_depth: int = 2,
        top_k: int = 25,
        curation_statuses: list[str] | None = None,
        include_evidence_chains: bool = True,
        force_agent: bool = False,
        model_id: str | None = None,
    ) -> GraphSearchContract: ...


def read_positive_int_env(env_name: str, *, default_value: int) -> int:
    """Read a positive integer env var, falling back to the supplied default."""
    raw_value = os.getenv(env_name)
    if raw_value is None or not raw_value.strip():
        return default_value
    try:
        parsed = int(raw_value.strip())
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


class ActivePipelineRunExistsError(RuntimeError):
    """Raised when a source already has queued or running pipeline work."""

    def __init__(self, *, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(
            "An active pipeline run already exists for this source "
            f"(run_id={run_id})",
        )


class PipelineQueueFullError(RuntimeError):
    """Raised when the durable pipeline queue is at capacity."""

    def __init__(self, *, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__("Pipeline queue is full")


@dataclass(frozen=True)
class QueuedPipelineRunRequest:
    """Resolved pipeline arguments stored in durable queue metadata."""

    run_id: str
    research_space_id: UUID
    resume_from_stage: PipelineStageName | None
    enrichment_limit: int
    extraction_limit: int
    source_type: str | None
    model_id: str | None
    shadow_mode: bool | None
    force_recover_lock: bool
    graph_seed_entity_ids: list[str] | None
    graph_max_depth: int
    graph_relation_types: list[str] | None


@dataclass(frozen=True)
class PipelineRunEnqueueResult:
    """Accepted durable queue response for async pipeline runs."""

    run_id: str
    source_id: UUID
    research_space_id: UUID
    status: str
    accepted_at: datetime


@dataclass(frozen=True)
class PipelineOrchestrationDependencies:
    """Dependencies required for end-to-end pipeline orchestration."""

    ingestion_scheduling_service: IngestionSchedulingService
    content_enrichment_service: ContentEnrichmentService
    entity_recognition_service: EntityRecognitionService
    content_enrichment_stage_runner: (
        Callable[..., Awaitable[ContentEnrichmentRunSummary]] | None
    ) = None
    entity_recognition_stage_runner: (
        Callable[..., Awaitable[EntityRecognitionRunSummary]] | None
    ) = None
    graph_connection_service: GraphConnectionExecutor | None = None
    graph_connection_seed_runner: (
        Callable[..., Awaitable[GraphConnectionOutcome]] | None
    ) = None
    graph_search_service: GraphSearchExecutor | None = None
    research_space_repository: ResearchSpaceRepository | None = None
    pipeline_run_repository: IngestionJobRepository | None = None
    pipeline_trace_service: PipelineRunTraceService | None = None


__all__ = [
    "ActivePipelineRunExistsError",
    "DEFAULT_PIPELINE_QUEUE_MAX_SIZE",
    "DEFAULT_PIPELINE_QUEUE_RETRY_AFTER_SECONDS",
    "DEFAULT_PIPELINE_RETRY_BASE_DELAY_SECONDS",
    "DEFAULT_PIPELINE_RETRY_MAX_ATTEMPTS",
    "ENV_PIPELINE_QUEUE_MAX_SIZE",
    "ENV_PIPELINE_QUEUE_RETRY_AFTER_SECONDS",
    "ENV_PIPELINE_RETRY_BASE_DELAY_SECONDS",
    "ENV_PIPELINE_RETRY_MAX_ATTEMPTS",
    "GraphConnectionExecutor",
    "GraphSearchExecutor",
    "PipelineOrchestrationDependencies",
    "PipelineQueueFullError",
    "PipelineRunEnqueueResult",
    "QueuedPipelineRunRequest",
    "read_positive_int_env",
]
