"""Config and data models for the graph stage orchestration helper."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.application.services._pipeline_orchestration_graph_fallback_helpers import (
    resolve_graph_seed_limit,
)

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.services._pipeline_orchestration_contracts import (
        PipelineStageName,
        PipelineStageStatus,
    )
    from src.domain.agents.contracts.graph_connection import ProposedRelation
    from src.domain.entities.ingestion_job import IngestionJob

logger = logging.getLogger(__name__)

ENV_GRAPH_SEED_INFERENCE_TIMEOUT_SECONDS = (
    "ARTANA_PIPELINE_GRAPH_SEED_INFERENCE_TIMEOUT_SECONDS"
)
DEFAULT_GRAPH_SEED_INFERENCE_TIMEOUT_SECONDS = 120.0
ENV_GRAPH_STAGE_MAX_CONCURRENCY = "ARTANA_PIPELINE_GRAPH_STAGE_MAX_CONCURRENCY"
DEFAULT_GRAPH_STAGE_MAX_CONCURRENCY = 2
ENV_GRAPH_STAGE_SEED_TIMEOUT_SECONDS = (
    "ARTANA_PIPELINE_GRAPH_STAGE_SEED_TIMEOUT_SECONDS"
)
DEFAULT_GRAPH_STAGE_SEED_TIMEOUT_SECONDS = 180.0
ENV_GRAPH_MAX_SEEDS_PER_RUN = "ARTANA_GRAPH_MAX_SEEDS_PER_RUN"
DEFAULT_GRAPH_MAX_SEEDS_PER_RUN = 5


def read_positive_timeout_seconds(
    env_name: str,
    *,
    default_seconds: float,
) -> float:
    """Read a positive timeout override in seconds."""
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


def read_positive_int(
    env_name: str,
    *,
    default_value: int,
) -> int:
    """Read a positive integer override."""
    raw_value = os.getenv(env_name)
    if raw_value is None:
        return default_value
    try:
        parsed = int(raw_value)
    except ValueError:
        logger.warning(
            "Invalid integer override in %s=%r; using default %s",
            env_name,
            raw_value,
            default_value,
        )
        return default_value
    if parsed <= 0:
        logger.warning(
            "Non-positive integer override in %s=%r; using default %s",
            env_name,
            raw_value,
            default_value,
        )
        return default_value
    return parsed


def resolve_graph_stage_seed_limit() -> int:
    """Resolve the max graph seeds allowed for a single pipeline run."""
    return resolve_graph_seed_limit(
        env_name=ENV_GRAPH_MAX_SEEDS_PER_RUN,
        default=DEFAULT_GRAPH_MAX_SEEDS_PER_RUN,
    )


@dataclass(slots=True)
class GraphStageInput:
    source_id: UUID
    research_space_id: UUID
    run_id: str
    resume_from_stage: PipelineStageName | None
    should_run_graph: bool
    extraction_status: PipelineStageStatus
    normalized_source_type: str | None
    model_id: str | None
    shadow_mode: bool | None
    explicit_graph_seed_entity_ids: list[str]
    derived_graph_seed_entity_ids: list[str]
    extraction_graph_fallback_relations: dict[str, tuple[ProposedRelation, ...]]
    extraction_processed: int
    extraction_extracted: int
    extraction_failed: int
    extraction_persisted_relations: int
    extraction_concept_members_created: int
    extraction_concept_aliases_created: int
    extraction_concept_decisions_proposed: int
    total_persisted_relations: int
    graph_status: PipelineStageStatus
    errors: list[str]
    pipeline_error_category: str | None
    run_cancelled: bool
    pipeline_run_job: IngestionJob | None
    graph_relation_types: list[str] | None
    graph_max_depth: int


@dataclass(slots=True)
class GraphStageOutput:
    active_graph_seed_entity_ids: list[str]
    inferred_graph_seed_entity_ids: list[str]
    graph_seed_mode: str
    graph_seed_limit: int
    graph_requested: int
    graph_processed: int
    graph_stage_persisted_relations: int
    total_persisted_relations: int
    graph_status: PipelineStageStatus
    pipeline_error_category: str | None
    run_cancelled: bool
    pipeline_run_job: IngestionJob | None


__all__ = [
    "DEFAULT_GRAPH_SEED_INFERENCE_TIMEOUT_SECONDS",
    "DEFAULT_GRAPH_STAGE_MAX_CONCURRENCY",
    "DEFAULT_GRAPH_STAGE_SEED_TIMEOUT_SECONDS",
    "ENV_GRAPH_SEED_INFERENCE_TIMEOUT_SECONDS",
    "ENV_GRAPH_STAGE_MAX_CONCURRENCY",
    "ENV_GRAPH_STAGE_SEED_TIMEOUT_SECONDS",
    "GraphStageInput",
    "GraphStageOutput",
    "read_positive_int",
    "read_positive_timeout_seconds",
    "resolve_graph_stage_seed_limit",
]
