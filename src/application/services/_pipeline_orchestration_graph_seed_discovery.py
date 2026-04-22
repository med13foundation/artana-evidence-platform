"""Graph seed discovery helpers for pipeline orchestration."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.agents.services.graph_connection_service import (
        GraphConnectionOutcome,
    )
    from src.application.services._pipeline_orchestration_execution_protocols import (
        _PipelineExecutionSelf,
    )
    from src.application.services._pipeline_orchestration_graph_stage_models import (
        GraphStageInput,
    )


async def discover_graph_seed(  # noqa: C901, PLR0913
    execution_self: _PipelineExecutionSelf,
    *,
    graph_stage_input: GraphStageInput,
    graph_semaphore: asyncio.Semaphore,
    seed_entity_id: str,
    normalized_source: str,
    graph_seed_timeout_seconds: float,
) -> tuple[str, int, tuple[str, ...], str | None, bool]:
    """Discover graph relations for one seed entity with compatibility fallbacks."""
    async with graph_semaphore:
        if execution_self._is_pipeline_run_cancelled(  # noqa: SLF001
            source_id=graph_stage_input.source_id,
            run_id=graph_stage_input.run_id,
        ):
            return seed_entity_id, 0, (), None, True
        fallback_relations = graph_stage_input.extraction_graph_fallback_relations.get(
            seed_entity_id,
            (),
        )

        try:

            async def _run_graph_discovery() -> GraphConnectionOutcome:  # noqa: C901
                if execution_self._graph_seed_runner is not None:  # noqa: SLF001
                    return await execution_self._graph_seed_runner(  # noqa: SLF001
                        source_id=str(graph_stage_input.source_id),
                        research_space_id=str(
                            graph_stage_input.research_space_id,
                        ),
                        seed_entity_id=seed_entity_id,
                        source_type=normalized_source,
                        model_id=graph_stage_input.model_id,
                        relation_types=graph_stage_input.graph_relation_types,
                        max_depth=graph_stage_input.graph_max_depth,
                        shadow_mode=graph_stage_input.shadow_mode,
                        pipeline_run_id=graph_stage_input.run_id,
                        fallback_relations=fallback_relations,
                    )
                graph_service = execution_self._graph  # noqa: SLF001
                if graph_service is None:
                    msg = "graph service unavailable"
                    raise RuntimeError(msg)  # noqa: TRY301

                async def _call_graph_discovery(  # noqa: PLR0913
                    *,
                    include_source_id: bool,
                    include_fallback_relations: bool,
                ) -> GraphConnectionOutcome:
                    if include_source_id and include_fallback_relations:
                        return await graph_service.discover_connections_for_seed(
                            research_space_id=str(
                                graph_stage_input.research_space_id,
                            ),
                            seed_entity_id=seed_entity_id,
                            source_id=str(graph_stage_input.source_id),
                            source_type=normalized_source,
                            model_id=graph_stage_input.model_id,
                            relation_types=graph_stage_input.graph_relation_types,
                            max_depth=graph_stage_input.graph_max_depth,
                            shadow_mode=graph_stage_input.shadow_mode,
                            pipeline_run_id=graph_stage_input.run_id,
                            fallback_relations=fallback_relations,
                        )
                    if include_source_id and not include_fallback_relations:
                        return await graph_service.discover_connections_for_seed(
                            research_space_id=str(
                                graph_stage_input.research_space_id,
                            ),
                            seed_entity_id=seed_entity_id,
                            source_id=str(graph_stage_input.source_id),
                            source_type=normalized_source,
                            model_id=graph_stage_input.model_id,
                            relation_types=graph_stage_input.graph_relation_types,
                            max_depth=graph_stage_input.graph_max_depth,
                            shadow_mode=graph_stage_input.shadow_mode,
                            pipeline_run_id=graph_stage_input.run_id,
                        )
                    if not include_source_id and include_fallback_relations:
                        return await graph_service.discover_connections_for_seed(
                            research_space_id=str(
                                graph_stage_input.research_space_id,
                            ),
                            seed_entity_id=seed_entity_id,
                            source_type=normalized_source,
                            model_id=graph_stage_input.model_id,
                            relation_types=graph_stage_input.graph_relation_types,
                            max_depth=graph_stage_input.graph_max_depth,
                            shadow_mode=graph_stage_input.shadow_mode,
                            pipeline_run_id=graph_stage_input.run_id,
                            fallback_relations=fallback_relations,
                        )
                    return await graph_service.discover_connections_for_seed(
                        research_space_id=str(
                            graph_stage_input.research_space_id,
                        ),
                        seed_entity_id=seed_entity_id,
                        source_type=normalized_source,
                        model_id=graph_stage_input.model_id,
                        relation_types=graph_stage_input.graph_relation_types,
                        max_depth=graph_stage_input.graph_max_depth,
                        shadow_mode=graph_stage_input.shadow_mode,
                        pipeline_run_id=graph_stage_input.run_id,
                    )

                include_source_id = True
                include_fallback_relations = True
                while True:
                    try:
                        return await _call_graph_discovery(
                            include_source_id=include_source_id,
                            include_fallback_relations=include_fallback_relations,
                        )
                    except TypeError as exc:
                        fallback_message = str(exc)
                        removed_unsupported_key = False
                        if (
                            "fallback_relations" in fallback_message
                            and include_fallback_relations
                        ):
                            include_fallback_relations = False
                            removed_unsupported_key = True
                        if "source_id" in fallback_message and include_source_id:
                            include_source_id = False
                            removed_unsupported_key = True
                        if not removed_unsupported_key:
                            raise

            graph_outcome = await asyncio.wait_for(
                _run_graph_discovery(),
                timeout=graph_seed_timeout_seconds,
            )
        except TimeoutError:
            return (
                seed_entity_id,
                0,
                (),
                f"seed_timeout:{graph_seed_timeout_seconds:.1f}s",
                False,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced in run summary
            return seed_entity_id, 0, (), str(exc), False
        else:
            return (
                seed_entity_id,
                graph_outcome.persisted_relations_count,
                graph_outcome.errors,
                None,
                False,
            )


__all__ = ["discover_graph_seed"]
