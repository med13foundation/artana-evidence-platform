"""Shared helper mixins for pipeline orchestration stage and seed handling."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from src.application.services._pipeline_orchestration_contracts import (
    PIPELINE_STAGE_ORDER,
    PipelineStageName,
)

if TYPE_CHECKING:
    from src.application.services._pipeline_orchestration_execution_protocols import (
        _PipelineExecutionSelf,
    )


class _PipelineOrchestrationStageHelpers:
    """Shared helpers for stage control and seed normalization."""

    _MAX_GRAPH_SEED_ENTITY_IDS = 5

    @staticmethod
    def _resolve_run_id(raw_run_id: str | None) -> str:
        if raw_run_id is None:
            return str(uuid4())
        normalized = raw_run_id.strip()
        if normalized:
            return normalized
        return str(uuid4())

    @staticmethod
    def _resolve_resume_stage(
        resume_from_stage: PipelineStageName | None,
    ) -> PipelineStageName | None:
        if resume_from_stage is None:
            return None
        if resume_from_stage in PIPELINE_STAGE_ORDER:
            return resume_from_stage
        return None

    @staticmethod
    def _should_run_stage(
        *,
        stage: PipelineStageName,
        resume_from_stage: PipelineStageName | None,
    ) -> bool:
        if resume_from_stage is None:
            return True
        stage_index = PIPELINE_STAGE_ORDER.index(stage)
        resume_index = PIPELINE_STAGE_ORDER.index(resume_from_stage)
        return stage_index >= resume_index

    @classmethod
    def _normalize_graph_seed_entity_ids(
        cls,
        seed_entity_ids: list[str] | None,
    ) -> list[str]:
        normalized_ids: list[str] = []
        for seed_entity_id in seed_entity_ids or []:
            normalized = seed_entity_id.strip()
            if not normalized or normalized in normalized_ids:
                continue
            normalized_ids.append(normalized)
            if len(normalized_ids) >= cls._MAX_GRAPH_SEED_ENTITY_IDS:
                break
        return normalized_ids

    @classmethod
    def _extract_seed_entity_ids_from_extraction_summary(
        cls,
        extraction_summary: object,
    ) -> list[str]:
        raw_seed_ids = getattr(
            extraction_summary,
            "derived_graph_seed_entity_ids",
            (),
        )
        if not isinstance(raw_seed_ids, list | tuple):
            return []
        normalized_ids: list[str] = []
        for seed_entity_id in raw_seed_ids:
            if not isinstance(seed_entity_id, str):
                continue
            normalized = seed_entity_id.strip()
            if not normalized or normalized in normalized_ids:
                continue
            normalized_ids.append(normalized)
            if len(normalized_ids) >= cls._MAX_GRAPH_SEED_ENTITY_IDS:
                break
        return normalized_ids


class _PipelineOrchestrationContextSeedHelpers(_PipelineOrchestrationStageHelpers):
    """Helpers for AI-assisted seed inference from project and run context."""

    async def _infer_seed_entity_ids_with_context(
        self: _PipelineExecutionSelf,
        *,
        source_id: UUID,
        research_space_id: UUID,
        source_type: str | None,
        model_id: str | None,
    ) -> list[str]:
        graph_search_service = self._graph_search
        if graph_search_service is None:
            return []

        prompt = self._build_seed_inference_prompt(
            source_id=source_id,
            research_space_id=research_space_id,
            source_type=source_type,
        )
        try:
            search_contract = await graph_search_service.search(
                question=prompt,
                research_space_id=str(research_space_id),
                max_depth=1,
                top_k=5,
                include_evidence_chains=False,
                force_agent=True,
                model_id=model_id,
            )
        except Exception:  # noqa: BLE001 - seed inference must never block pipeline
            return []

        return self._extract_seed_entity_ids_from_graph_search(search_contract)

    def _build_seed_inference_prompt(
        self: _PipelineExecutionSelf,
        *,
        source_id: UUID,
        research_space_id: UUID,
        source_type: str | None,
    ) -> str:
        research_space_summary = self._resolve_research_space_summary(
            research_space_id=research_space_id,
        )
        run_query_hints = self._resolve_recent_run_query_hints(source_id=source_id)
        source_label = source_type if source_type else "unspecified"
        query_summary = (
            "; ".join(run_query_hints)
            if run_query_hints
            else "No prior run query hints available."
        )
        return (
            "Select the best existing graph entities to use as graph-discovery "
            "seeds for this research space. "
            f"Source type: {source_label}. "
            f"Research space context: {research_space_summary} "
            f"Previous run query hints: {query_summary}"
        )

    def _resolve_research_space_summary(
        self: _PipelineExecutionSelf,
        *,
        research_space_id: UUID,
    ) -> str:
        research_space_repository = self._research_spaces
        if research_space_repository is None:
            return "Not available."
        space = research_space_repository.find_by_id(research_space_id)
        if space is None:
            return "Not available."
        tag_summary = ", ".join(space.tags[:5]) if space.tags else "none"
        return (
            f"name={space.name}; description={space.description}; tags={tag_summary}."
        )

    def _resolve_recent_run_query_hints(
        self: _PipelineExecutionSelf,
        *,
        source_id: UUID,
    ) -> tuple[str, ...]:
        recent_hints: list[str] = []
        try:
            recent_jobs = self._ingestion.get_job_repository().find_by_source(
                source_id,
                limit=5,
            )
        except Exception:  # noqa: BLE001 - hint collection should never block runs
            return ()
        for job in recent_jobs:
            query_hint = self._extract_job_query_hint(metadata=job.metadata)
            if query_hint is None or query_hint in recent_hints:
                continue
            recent_hints.append(query_hint)
        return tuple(recent_hints)

    @staticmethod
    def _extract_job_query_hint(
        *,
        metadata: object,
    ) -> str | None:
        if not isinstance(metadata, dict):
            return None
        executed_query = metadata.get("executed_query")
        if isinstance(executed_query, str) and executed_query.strip():
            return executed_query.strip()
        query_generation = metadata.get("query_generation")
        if isinstance(query_generation, dict):
            for key in ("query", "generated_query", "base_query"):
                value = query_generation.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None

    @classmethod
    def _extract_seed_entity_ids_from_graph_search(
        cls,
        search_contract: object,
    ) -> list[str]:
        raw_results = getattr(search_contract, "results", ())
        if not isinstance(raw_results, list | tuple):
            return []
        normalized_ids: list[str] = []
        for result in raw_results:
            entity_id = getattr(result, "entity_id", None)
            if not isinstance(entity_id, str):
                continue
            normalized = entity_id.strip()
            if not normalized or normalized in normalized_ids:
                continue
            normalized_ids.append(normalized)
            if len(normalized_ids) >= cls._MAX_GRAPH_SEED_ENTITY_IDS:
                break
        return normalized_ids


__all__ = [
    "_PipelineOrchestrationContextSeedHelpers",
    "_PipelineOrchestrationStageHelpers",
]
