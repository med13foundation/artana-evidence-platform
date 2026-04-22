"""Post-ingestion pipeline hook wiring for scheduled ingestion."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
from uuid import UUID

from src.database.session import SessionLocal, set_session_rls_context
from src.infrastructure.platform_graph.artana_evidence_api.pipeline import (
    build_graph_connection_seed_runner_for_service,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from src.domain.entities.user_data_source import UserDataSource
    from src.domain.services.ingestion import IngestionRunSummary

logger = logging.getLogger(__name__)

_MAX_POST_INGESTION_GRAPH_SEEDS = 200


def build_post_ingestion_hook(
    *,
    enable_post_ingestion_graph_stage: bool,
    graph_seed_timeout_seconds: int,
) -> Callable[[UserDataSource, IngestionRunSummary], Awaitable[None]]:
    """Create the optional post-ingestion enrichment/extraction/graph hook."""
    from src.infrastructure.dependency_injection.dependencies import (
        get_legacy_dependency_container,
    )

    container = get_legacy_dependency_container()
    graph_seed_runner = build_graph_connection_seed_runner_for_service()

    async def _run_enrichment_stage_isolated_uow(
        *,
        source_id: UUID,
        research_space_id: UUID,
        source_type: str,
        ingestion_job_id: UUID | None,
    ) -> None:
        isolated_session = SessionLocal()
        set_session_rls_context(isolated_session, bypass_rls=True)
        isolated_enrichment_service = container.create_content_enrichment_service(
            isolated_session,
        )
        try:
            await isolated_enrichment_service.process_pending_documents(
                limit=200,
                source_id=source_id,
                ingestion_job_id=ingestion_job_id,
                research_space_id=research_space_id,
                source_type=source_type,
                model_id=None,
            )
        finally:
            await isolated_enrichment_service.close()
            isolated_session.close()

    async def _run_extraction_stage_isolated_uow(
        *,
        source_id: UUID,
        research_space_id: UUID,
        source_type: str,
        ingestion_job_id: UUID | None,
    ) -> object:
        isolated_session = SessionLocal()
        set_session_rls_context(isolated_session, bypass_rls=True)
        isolated_extraction_service = container.create_entity_recognition_service(
            isolated_session,
        )
        try:
            return await isolated_extraction_service.process_pending_documents(
                limit=200,
                source_id=source_id,
                ingestion_job_id=ingestion_job_id,
                research_space_id=research_space_id,
                source_type=source_type,
                model_id=None,
                shadow_mode=None,
            )
        finally:
            await isolated_extraction_service.close()
            isolated_session.close()

    async def _run_graph_seed_isolated_uow(
        *,
        source_id: UUID,
        research_space_id: UUID,
        source_type: str,
        seed_entity_id: str,
    ) -> None:
        await graph_seed_runner(
            source_id=str(source_id),
            research_space_id=str(research_space_id),
            seed_entity_id=seed_entity_id,
            source_type=source_type,
            model_id=None,
            relation_types=None,
            max_depth=2,
            shadow_mode=None,
            pipeline_run_id=None,
            fallback_relations=None,
        )

    async def _run_post_ingestion_pipeline(
        source: UserDataSource,
        summary: IngestionRunSummary,
    ) -> None:
        if source.research_space_id is None:
            return
        ingestion_job_id = _resolve_ingestion_job_id(source=source, summary=summary)
        source_type_value = source.source_type.value
        await _run_enrichment_stage_isolated_uow(
            source_id=source.id,
            research_space_id=source.research_space_id,
            source_type=source_type_value,
            ingestion_job_id=ingestion_job_id,
        )
        extraction_summary = await _run_extraction_stage_isolated_uow(
            source_id=source.id,
            ingestion_job_id=ingestion_job_id,
            research_space_id=source.research_space_id,
            source_type=source_type_value,
        )
        if not enable_post_ingestion_graph_stage:
            return
        extracted_seed_entity_ids = getattr(
            extraction_summary,
            "derived_graph_seed_entity_ids",
            (),
        )
        derived_seed_ids = _normalize_graph_seed_entity_ids(
            tuple(extracted_seed_entity_ids),
        )
        for seed_entity_id in derived_seed_ids:
            try:
                await asyncio.wait_for(
                    _run_graph_seed_isolated_uow(
                        source_id=source.id,
                        research_space_id=source.research_space_id,
                        source_type=source_type_value,
                        seed_entity_id=seed_entity_id,
                    ),
                    timeout=graph_seed_timeout_seconds,
                )
            except TimeoutError:
                logger.warning(
                    (
                        "Post-ingestion graph discovery timed out for "
                        "source_id=%s, seed=%s, timeout_seconds=%s"
                    ),
                    source.id,
                    seed_entity_id,
                    graph_seed_timeout_seconds,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Post-ingestion graph discovery failed for source_id=%s, seed=%s: %s",
                    source.id,
                    seed_entity_id,
                    exc,
                )

    return _run_post_ingestion_pipeline


def _resolve_ingestion_job_id(
    *,
    source: UserDataSource,
    summary: IngestionRunSummary,
) -> UUID | None:
    ingestion_job_id_raw: object = getattr(summary, "ingestion_job_id", None)
    if isinstance(ingestion_job_id_raw, UUID):
        return ingestion_job_id_raw
    if isinstance(ingestion_job_id_raw, str):
        normalized_ingestion_job_id = ingestion_job_id_raw.strip()
        if normalized_ingestion_job_id:
            try:
                return UUID(normalized_ingestion_job_id)
            except ValueError:
                logger.warning(
                    "Post-ingestion hook summary had invalid ingestion_job_id",
                    extra={
                        "source_id": str(source.id),
                        "ingestion_job_id": normalized_ingestion_job_id,
                    },
                )
    logger.warning(
        "Post-ingestion hook running without ingestion_job_id scope",
        extra={"source_id": str(source.id)},
    )
    return None


def _normalize_graph_seed_entity_ids(seed_entity_ids: tuple[str, ...]) -> list[str]:
    normalized_ids: list[str] = []
    for seed_entity_id in seed_entity_ids:
        normalized = seed_entity_id.strip()
        if not normalized or normalized in normalized_ids:
            continue
        normalized_ids.append(normalized)
        if len(normalized_ids) >= _MAX_POST_INGESTION_GRAPH_SEEDS:
            break
    return normalized_ids


__all__ = ["build_post_ingestion_hook"]
