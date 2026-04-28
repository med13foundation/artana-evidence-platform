"""Source-plan artifact builders for evidence-selection runs."""

from __future__ import annotations

from collections import Counter

from artana_evidence_api.evidence_selection_candidates import (
    EvidenceSelectionCandidateSearch,
)
from artana_evidence_api.evidence_selection_source_search import (
    EvidenceSelectionLiveSourceSearch,
)
from artana_evidence_api.source_registry import get_source_definition
from artana_evidence_api.types.common import JSONObject


def build_source_plan(
    *,
    goal: str,
    instructions: str | None,
    requested_sources: tuple[str, ...],
    source_searches: tuple[EvidenceSelectionLiveSourceSearch, ...],
    candidate_searches: tuple[EvidenceSelectionCandidateSearch, ...],
    inclusion_criteria: tuple[str, ...],
    exclusion_criteria: tuple[str, ...],
    population_context: str | None,
    evidence_types: tuple[str, ...],
    priority_outcomes: tuple[str, ...],
    planner_kind: str = "deterministic",
    planner_mode: str = "deterministic",
    planner_reason: str | None = None,
    model_id: str | None = None,
    planner_version: str | None = None,
    planned_searches: tuple[JSONObject, ...] = (),
    deferred_sources: tuple[JSONObject, ...] = (),
    validation_decisions: tuple[JSONObject, ...] = (),
    fallback_reason: str | None = None,
    agent_run_id: str | None = None,
) -> JSONObject:
    """Return the auditable source plan artifact for this run."""

    candidate_source_counts = Counter(search.source_key for search in candidate_searches)
    live_source_counts = Counter(search.source_key for search in source_searches)
    requested = list(dict.fromkeys(requested_sources))
    for source_key in live_source_counts:
        if source_key not in requested:
            requested.append(source_key)
    source_entries: list[JSONObject] = []
    for source_key in requested:
        source = get_source_definition(source_key)
        source_entries.append(
            {
                "source_key": source_key,
                "source_family": (
                    source.source_family if source is not None else "unknown"
                ),
                "candidate_search_count": candidate_source_counts.get(source_key, 0),
                "live_search_count": live_source_counts.get(source_key, 0),
                "action": (
                    "run_and_screen_source_searches"
                    if live_source_counts.get(source_key, 0) > 0
                    else "screen_saved_searches"
                    if candidate_source_counts.get(source_key, 0) > 0
                    else "defer_search_request"
                ),
                "reason": (
                    "The harness will create and screen source-search results "
                    "for this source."
                    if live_source_counts.get(source_key, 0) > 0
                    else "Saved source-search results were supplied for this source."
                    if candidate_source_counts.get(source_key, 0) > 0
                    else "No source-search request or saved source-search result "
                    "was supplied."
                ),
            },
        )
    return {
        "goal": goal,
        "instructions": instructions,
        "sources": source_entries,
        "selection_policy": {
            "harness_role": (
                "deterministically select relevant candidate evidence before "
                "human review"
            ),
            "human_role": "review and approve before trusted graph promotion",
            "inclusion_criteria": list(inclusion_criteria),
            "exclusion_criteria": list(exclusion_criteria),
            "population_context": population_context,
            "evidence_types": list(evidence_types),
            "priority_outcomes": list(priority_outcomes),
        },
        "current_capability": (
            "Creates supported structured source searches, screens durable "
            "source-search results, creates guarded handoffs, stages "
            "review-gated proposals/items, and can use a model planner to "
            "turn a research goal into source searches."
        ),
        "planner": {
            "kind": planner_kind,
            "mode": planner_mode,
            "agent_invoked": planner_kind == "model",
            "reason": planner_reason,
            "active_skill": "graph_harness.source_relevance",
            "model_id": model_id,
            "planner_version": planner_version,
            "fallback_reason": fallback_reason,
            "agent_run_id": agent_run_id,
            "planned_searches": list(planned_searches),
            "deferred_sources": list(deferred_sources),
            "validation_decisions": list(validation_decisions),
        },
    }


__all__ = ["build_source_plan"]
