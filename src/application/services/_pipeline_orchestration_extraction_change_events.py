"""Helpers for recording extraction-stage mutation change events."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.agents.services.entity_recognition_service import (
        EntityRecognitionRunSummary,
    )

    from ._pipeline_orchestration_execution_runtime import PipelineExecutionRuntime


def record_extraction_change_events(
    *,
    runtime: PipelineExecutionRuntime,
    extraction_summary: EntityRecognitionRunSummary,
) -> None:
    relation_claims_count = _summary_int(
        extraction_summary,
        "relation_claims_count",
    )
    pending_review_relations_count = _summary_int(
        extraction_summary,
        "pending_review_relations_count",
    )
    undefined_relations_count = _summary_int(
        extraction_summary,
        "undefined_relations_count",
    )
    persisted_relations_count = _summary_int(
        extraction_summary,
        "persisted_relations_count",
    )
    if (
        relation_claims_count > 0
        or pending_review_relations_count > 0
        or undefined_relations_count > 0
        or persisted_relations_count > 0
    ):
        runtime.record_trace_event(
            event_type="relation_changes_recorded",
            scope_kind="relation",
            scope_id="extraction",
            stage="extraction",
            message="Recorded relation claim and persistence changes.",
            status="completed",
            payload={
                "relation_claims_count": relation_claims_count,
                "pending_review_relations_count": pending_review_relations_count,
                "undefined_relations_count": undefined_relations_count,
                "persisted_relations_count": persisted_relations_count,
            },
        )

    concept_members_created_count = _summary_int(
        extraction_summary,
        "concept_members_created_count",
    )
    concept_aliases_created_count = _summary_int(
        extraction_summary,
        "concept_aliases_created_count",
    )
    concept_decisions_proposed_count = _summary_int(
        extraction_summary,
        "concept_decisions_proposed_count",
    )
    if (
        concept_members_created_count > 0
        or concept_aliases_created_count > 0
        or concept_decisions_proposed_count > 0
    ):
        runtime.record_trace_event(
            event_type="concept_changes_recorded",
            scope_kind="concept",
            scope_id="extraction",
            stage="extraction",
            message="Recorded concept member and alias changes.",
            status="completed",
            payload={
                "concept_members_created_count": concept_members_created_count,
                "concept_aliases_created_count": concept_aliases_created_count,
                "concept_decisions_proposed_count": (concept_decisions_proposed_count),
            },
        )

    dictionary_variables_created = _summary_int(
        extraction_summary,
        "dictionary_variables_created",
    )
    dictionary_synonyms_created = _summary_int(
        extraction_summary,
        "dictionary_synonyms_created",
    )
    dictionary_entity_types_created = _summary_int(
        extraction_summary,
        "dictionary_entity_types_created",
    )
    if (
        dictionary_variables_created > 0
        or dictionary_synonyms_created > 0
        or dictionary_entity_types_created > 0
    ):
        runtime.record_trace_event(
            event_type="dictionary_changes_recorded",
            scope_kind="dictionary",
            scope_id="extraction",
            stage="extraction",
            message="Recorded dictionary bootstrap and mutation changes.",
            status="completed",
            payload={
                "dictionary_variables_created": dictionary_variables_created,
                "dictionary_synonyms_created": dictionary_synonyms_created,
                "dictionary_entity_types_created": (dictionary_entity_types_created),
            },
        )


def _summary_int(summary: object, attribute: str) -> int:
    raw_value = getattr(summary, attribute, 0)
    if isinstance(raw_value, bool):
        return 0
    if isinstance(raw_value, int):
        return max(raw_value, 0)
    return 0


__all__ = ["record_extraction_change_events"]
