"""Shared contracts for unified pipeline orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from src.type_definitions.common import JSONObject

PipelineStageStatus = Literal["completed", "failed", "skipped"]
PipelineStageName = Literal["ingestion", "enrichment", "extraction", "graph"]
PIPELINE_STAGE_ORDER: tuple[PipelineStageName, ...] = (
    "ingestion",
    "enrichment",
    "extraction",
    "graph",
)


@dataclass(frozen=True)
class PipelineRunSummary:
    """Summary of one orchestrated pipeline run."""

    run_id: str
    source_id: UUID
    research_space_id: UUID
    started_at: datetime
    completed_at: datetime
    status: Literal["completed", "failed", "cancelled"]
    resume_from_stage: PipelineStageName | None
    ingestion_status: PipelineStageStatus
    enrichment_status: PipelineStageStatus
    extraction_status: PipelineStageStatus
    graph_status: PipelineStageStatus
    fetched_records: int = 0
    parsed_publications: int = 0
    created_publications: int = 0
    updated_publications: int = 0
    enrichment_processed: int = 0
    enrichment_enriched: int = 0
    enrichment_failed: int = 0
    extraction_processed: int = 0
    extraction_extracted: int = 0
    extraction_failed: int = 0
    graph_requested: int = 0
    graph_processed: int = 0
    graph_persisted_relations: int = 0
    executed_query: str | None = None
    errors: tuple[str, ...] = ()
    metadata: JSONObject | None = None


__all__ = [
    "PIPELINE_STAGE_ORDER",
    "PipelineRunSummary",
    "PipelineStageName",
    "PipelineStageStatus",
]
