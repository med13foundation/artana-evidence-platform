"""Factory helpers for durable pipeline orchestration workers."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from src.application.services.pipeline_orchestration_service import (
    PipelineOrchestrationDependencies,
    PipelineOrchestrationService,
)
from src.application.services.pipeline_run_trace_service import (
    PipelineRunTraceService,
)
from src.database.session import SessionLocal, set_session_rls_context
from src.infrastructure.dependency_injection.dependencies import (
    get_legacy_dependency_container,
)
from src.infrastructure.factories.ingestion_scheduler_factory import (
    build_ingestion_scheduling_service,
)
from src.infrastructure.platform_graph.artana_evidence_api.pipeline import (
    build_graph_connection_seed_runner_for_service,
    build_graph_search_service_for_service,
)
from src.infrastructure.repositories import (
    SqlAlchemyPipelineRunEventRepository,
    SqlAlchemyResearchSpaceRepository,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from uuid import UUID

    from src.application.agents.services._content_enrichment_types import (
        ContentEnrichmentRunSummary,
    )
    from src.application.agents.services.entity_recognition_service import (
        EntityRecognitionRunSummary,
    )


@asynccontextmanager
async def pipeline_orchestration_service_context() -> (  # noqa: PLR0915
    AsyncIterator[PipelineOrchestrationService]
):
    """Provide a bypass-RLS pipeline orchestration service for background workers."""
    session = SessionLocal()
    set_session_rls_context(session, bypass_rls=True)
    container = get_legacy_dependency_container()
    content_enrichment_service = None
    entity_recognition_service = None
    graph_search_service = build_graph_search_service_for_service()
    try:
        scheduling_service = build_ingestion_scheduling_service(session=session)
        content_enrichment_service = container.create_content_enrichment_service(
            session,
        )
        entity_recognition_service = container.create_entity_recognition_service(
            session,
        )
        run_graph_seed_isolated_uow = build_graph_connection_seed_runner_for_service()

        async def run_enrichment_stage_isolated_uow(  # noqa: PLR0913
            *,
            limit: int,
            source_id: UUID | None,
            ingestion_job_id: UUID | None,
            research_space_id: UUID | None,
            source_type: str | None,
            model_id: str | None,
            pipeline_run_id: str | None,
        ) -> ContentEnrichmentRunSummary:
            isolated_session = SessionLocal()
            set_session_rls_context(isolated_session, bypass_rls=True)
            isolated_service = container.create_content_enrichment_service(
                isolated_session,
            )
            try:
                return await isolated_service.process_pending_documents(
                    limit=limit,
                    source_id=source_id,
                    ingestion_job_id=ingestion_job_id,
                    research_space_id=research_space_id,
                    source_type=source_type,
                    model_id=model_id,
                    pipeline_run_id=pipeline_run_id,
                )
            finally:
                # The agent services use the shared process-local Artana store.
                # Closing them per worker unit-of-work tears down shared asyncpg
                # pools and breaks sibling worker slots bound to the same loop.
                isolated_session.close()

        async def run_extraction_stage_isolated_uow(  # noqa: PLR0913
            *,
            limit: int,
            source_id: UUID | None,
            ingestion_job_id: UUID | None,
            research_space_id: UUID | None,
            source_type: str | None,
            model_id: str | None,
            shadow_mode: bool | None,
            pipeline_run_id: str | None,
        ) -> EntityRecognitionRunSummary:
            isolated_session = SessionLocal()
            set_session_rls_context(isolated_session, bypass_rls=True)
            isolated_service = container.create_entity_recognition_service(
                isolated_session,
            )
            try:
                return await isolated_service.process_pending_documents(
                    limit=limit,
                    source_id=source_id,
                    ingestion_job_id=ingestion_job_id,
                    research_space_id=research_space_id,
                    source_type=source_type,
                    model_id=model_id,
                    shadow_mode=shadow_mode,
                    pipeline_run_id=pipeline_run_id,
                )
            finally:
                # Keep the shared Artana store alive for the process lifetime.
                isolated_session.close()

        yield PipelineOrchestrationService(
            dependencies=PipelineOrchestrationDependencies(
                ingestion_scheduling_service=scheduling_service,
                content_enrichment_service=content_enrichment_service,
                entity_recognition_service=entity_recognition_service,
                content_enrichment_stage_runner=run_enrichment_stage_isolated_uow,
                entity_recognition_stage_runner=run_extraction_stage_isolated_uow,
                graph_connection_service=None,
                graph_connection_seed_runner=run_graph_seed_isolated_uow,
                graph_search_service=graph_search_service,
                research_space_repository=SqlAlchemyResearchSpaceRepository(session),
                pipeline_run_repository=scheduling_service.get_job_repository(),
                pipeline_trace_service=PipelineRunTraceService(
                    session,
                    event_repository=SqlAlchemyPipelineRunEventRepository(session),
                ),
            ),
        )
    finally:
        # These worker-scoped services are created with the container's shared
        # process-local Artana store. Closing them here tears down that shared
        # asyncpg pool from arbitrary worker contexts and can strand claimed
        # runs before execution starts. The SQLAlchemy session remains scoped
        # to this context and is still closed below.
        session.close()
