"""Shared payload builders for graph-stage workflow progress updates."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.type_definitions.common import JSONObject


def build_graph_progress_payload(  # noqa: PLR0913
    *,
    status: str,
    requested: int,
    completed: int,
    processed: int,
    extraction_processed: int,
    extraction_completed: int,
    extraction_failed: int,
    persisted_relations: int,
    extraction_persisted_relations: int,
    extraction_concept_members_created: int,
    extraction_concept_aliases_created: int,
    extraction_concept_decisions_proposed: int,
    graph_stage_persisted_relations: int,
    max_concurrency: int,
    last_seed_entity_id: str | None = None,
    last_error: str | None = None,
) -> JSONObject:
    """Build the normalized graph progress payload persisted during a run."""
    return {
        "status": status,
        "requested": requested,
        "completed": completed,
        "processed": processed,
        "extraction_processed": extraction_processed,
        "extraction_completed": extraction_completed,
        "extraction_failed": extraction_failed,
        "persisted_relations": persisted_relations,
        "extraction_persisted_relations": extraction_persisted_relations,
        "extraction_concept_members_created": extraction_concept_members_created,
        "extraction_concept_aliases_created": extraction_concept_aliases_created,
        "extraction_concept_decisions_proposed": (
            extraction_concept_decisions_proposed
        ),
        "graph_stage_persisted_relations": graph_stage_persisted_relations,
        "max_concurrency": max_concurrency,
        "last_seed_entity_id": last_seed_entity_id,
        "last_error": last_error,
    }


__all__ = ["build_graph_progress_payload"]
