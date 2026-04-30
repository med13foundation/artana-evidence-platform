"""Workspace and result summary builders for the full-AI orchestrator."""

from __future__ import annotations

from copy import deepcopy

from artana_evidence_api.research_init_runtime import ResearchInitExecutionResult
from artana_evidence_api.types.common import (
    JSONObject,
    ResearchSpaceSourcePreferences,
    json_array_or_empty,
    json_object,
    json_object_or_empty,
)


def _build_workspace_summary(*, workspace_snapshot: JSONObject) -> JSONObject:
    return {
        "status": workspace_snapshot.get("status"),
        "current_round": workspace_snapshot.get("current_round", 0),
        "documents_ingested": workspace_snapshot.get("documents_ingested", 0),
        "proposal_count": workspace_snapshot.get("proposal_count", 0),
        "bootstrap_run_id": workspace_snapshot.get("bootstrap_run_id"),
        "bootstrap_source_type": workspace_snapshot.get("bootstrap_source_type"),
        "shadow_planner_mode": workspace_snapshot.get("shadow_planner_mode"),
        "planner_execution_mode": workspace_snapshot.get("planner_execution_mode"),
        "guarded_rollout_profile": workspace_snapshot.get("guarded_rollout_profile"),
        "guarded_rollout_profile_source": workspace_snapshot.get(
            "guarded_rollout_profile_source",
        ),
        "guarded_rollout_policy": json_object(
            workspace_snapshot.get("guarded_rollout_policy")
        ),
        "guarded_chase_rollout_enabled": workspace_snapshot.get(
            "guarded_chase_rollout_enabled",
        ),
        "shadow_planner_recommendation_key": workspace_snapshot.get(
            "shadow_planner_recommendation_key",
        ),
        "shadow_planner_comparison_key": workspace_snapshot.get(
            "shadow_planner_comparison_key",
        ),
        "shadow_planner_timeline_key": workspace_snapshot.get(
            "shadow_planner_timeline_key",
        ),
        "guarded_execution_log_key": workspace_snapshot.get(
            "guarded_execution_log_key",
        ),
        "guarded_readiness_key": workspace_snapshot.get("guarded_readiness_key"),
        "guarded_execution": json_object(workspace_snapshot.get("guarded_execution")),
        "guarded_readiness": json_object(workspace_snapshot.get("guarded_readiness")),
        "pending_question_count": len(
            json_array_or_empty(workspace_snapshot.get("pending_questions"))
        ),
        "artifact_keys": json_array_or_empty(workspace_snapshot.get("artifact_keys")),
        "result_keys": json_array_or_empty(workspace_snapshot.get("result_keys")),
    }


def _sanitize_replayed_workspace_snapshot(
    snapshot: JSONObject | None,
) -> JSONObject:
    if not isinstance(snapshot, dict):
        return {}
    sanitized = deepcopy(snapshot)
    for transient_key in ("artifact_keys", "result_keys", "primary_result_key"):
        sanitized.pop(transient_key, None)
    return sanitized


def _build_source_execution_summary(
    *,
    selected_sources: ResearchSpaceSourcePreferences,
    workspace_snapshot: JSONObject,
    research_init_result: ResearchInitExecutionResult,
) -> JSONObject:
    source_results = workspace_snapshot.get("source_results")
    return {
        "selected_sources": json_object_or_empty(selected_sources),
        "source_results": json_object_or_empty(source_results),
        "pubmed_result_count": len(research_init_result.pubmed_results),
        "documents_ingested": research_init_result.documents_ingested,
        "proposal_count": research_init_result.proposal_count,
    }


def _build_brief_metadata(
    *,
    workspace_snapshot: JSONObject,
    research_init_result: ResearchInitExecutionResult,
) -> JSONObject:
    research_brief = workspace_snapshot.get("research_brief")
    if not isinstance(research_brief, dict):
        return {
            "result_key": "research_brief",
            "present": False,
            "markdown_length": 0,
            "section_count": 0,
            "llm_markdown_present": research_init_result.research_brief_markdown
            is not None,
        }
    markdown = research_brief.get("markdown")
    sections = research_brief.get("sections")
    title = research_brief.get("title")
    return {
        "result_key": "research_brief",
        "present": True,
        "title": title if isinstance(title, str) else None,
        "markdown_length": len(markdown) if isinstance(markdown, str) else 0,
        "section_count": len(sections) if isinstance(sections, list) else 0,
        "llm_markdown_present": research_init_result.research_brief_markdown
        is not None,
    }


def _stop_reason(
    *,
    research_init_result: ResearchInitExecutionResult,
    workspace_snapshot: JSONObject,
) -> str:
    if research_init_result.errors:
        return "completed_with_errors"
    pending_questions = workspace_snapshot.get("pending_questions")
    if isinstance(pending_questions, list) and pending_questions:
        return "awaiting_scope_refinement"
    return "completed"


def _collect_chase_round_summaries(
    *, workspace_snapshot: JSONObject
) -> list[JSONObject]:
    summaries: list[JSONObject] = []
    for chase_round in (1, 2):
        summary = workspace_snapshot.get(f"chase_round_{chase_round}")
        if isinstance(summary, dict):
            summaries.append({"round_number": chase_round, **summary})
    return summaries


__all__ = [
    "_build_brief_metadata",
    "_build_source_execution_summary",
    "_build_workspace_summary",
    "_collect_chase_round_summaries",
    "_sanitize_replayed_workspace_snapshot",
    "_stop_reason",
]
