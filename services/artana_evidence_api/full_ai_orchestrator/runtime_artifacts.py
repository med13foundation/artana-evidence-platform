"""Artifact helpers for the full-AI orchestrator runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.full_ai_orchestrator.guarded.support import (
    _put_guarded_execution_artifact,
)
from artana_evidence_api.full_ai_orchestrator.response_support import (
    _collect_chase_round_summaries,
)
from artana_evidence_api.full_ai_orchestrator.runtime_constants import (
    _BOOTSTRAP_ARTIFACT_KEY,
    _BRIEF_METADATA_ARTIFACT_KEY,
    _CHASE_ROUNDS_ARTIFACT_KEY,
    _DRIVEN_TERMS_ARTIFACT_KEY,
    _PUBMED_ARTIFACT_KEY,
    _PUBMED_REPLAY_ARTIFACT_KEY,
    _SHADOW_PLANNER_COMPARISON_ARTIFACT_KEY,
    _SHADOW_PLANNER_RECOMMENDATION_ARTIFACT_KEY,
    _SHADOW_PLANNER_TIMELINE_ARTIFACT_KEY,
    _SOURCE_EXECUTION_ARTIFACT_KEY,
)
from artana_evidence_api.full_ai_orchestrator.workspace_support import (
    _planner_mode_value,
    _workspace_list,
    _workspace_object,
)
from artana_evidence_api.full_ai_orchestrator_contracts import (
    FullAIOrchestratorPlannerMode,
)
from artana_evidence_api.research_init_runtime import (
    ResearchInitPubMedReplayBundle,
    deserialize_pubmed_replay_bundle,
    serialize_pubmed_replay_bundle,
)
from artana_evidence_api.types.common import (
    JSONObject,
    ResearchSpaceSourcePreferences,
    json_object_or_empty,
)

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore


__all__ = [
    "_build_live_bootstrap_summary",
    "_build_live_brief_metadata",
    "_build_live_chase_rounds_artifact",
    "_build_live_driven_terms_artifact",
    "_build_live_pubmed_summary",
    "_build_live_source_execution_summary",
    "_store_pending_action_output_artifacts",
    "load_pubmed_replay_bundle_artifact",
    "store_pubmed_replay_bundle_artifact",
]


def _build_live_brief_metadata(*, workspace_snapshot: JSONObject) -> JSONObject:
    workspace_status = workspace_snapshot.get("status")
    brief_generation = json_object_or_empty(
        workspace_snapshot.get("research_brief_generation")
    )
    generation_status = brief_generation.get("status")
    generation_reason = brief_generation.get("reason")
    generation_error = brief_generation.get("error")
    llm_status = brief_generation.get("llm_status")
    missing_reason = (
        "research_brief_not_stored"
        if generation_status == "completed"
        else generation_reason
        if isinstance(generation_reason, str)
        else "missing_research_brief"
        if workspace_status == "completed"
        else "not_yet_generated"
    )
    research_brief = workspace_snapshot.get("research_brief")
    if not isinstance(research_brief, dict):
        return {
            "result_key": "research_brief",
            "present": False,
            "markdown_length": 0,
            "section_count": 0,
            "llm_markdown_present": False,
            "brief_markdown_present": False,
            "status": "skipped" if workspace_status == "completed" else "pending",
            "reason": missing_reason,
            "error": generation_error if isinstance(generation_error, str) else None,
            "llm_status": llm_status if isinstance(llm_status, str) else "unknown",
        }
    markdown = research_brief.get("markdown")
    sections = research_brief.get("sections")
    title = research_brief.get("title")
    markdown_present = isinstance(markdown, str) and markdown.strip() != ""
    llm_markdown_present = llm_status == "completed" and markdown_present
    return {
        "result_key": "research_brief",
        "present": True,
        "title": title if isinstance(title, str) else None,
        "markdown_length": len(markdown) if isinstance(markdown, str) else 0,
        "section_count": len(sections) if isinstance(sections, list) else 0,
        "llm_markdown_present": llm_markdown_present,
        "brief_markdown_present": markdown_present,
        "status": "completed",
        "reason": None,
        "error": generation_error if isinstance(generation_error, str) else None,
        "llm_status": llm_status if isinstance(llm_status, str) else "unknown",
    }


def _build_live_pubmed_summary(
    *, workspace_snapshot: JSONObject, status: str
) -> JSONObject:
    source_results = _workspace_object(workspace_snapshot, "source_results")
    pubmed_summary = json_object_or_empty(source_results.get("pubmed"))
    return {
        "status": status,
        "pubmed_results": _workspace_list(workspace_snapshot, "pubmed_results"),
        "documents_ingested": workspace_snapshot.get("documents_ingested", 0),
        "pubmed_source_summary": pubmed_summary,
    }


def _build_live_driven_terms_artifact(
    *,
    objective: str,
    seed_terms: list[str],
    workspace_snapshot: JSONObject,
    status: str,
) -> JSONObject:
    return {
        "status": status,
        "objective": objective,
        "seed_terms": list(seed_terms),
        "driven_terms": _workspace_list(workspace_snapshot, "driven_terms"),
        "driven_genes_from_pubmed": _workspace_list(
            workspace_snapshot,
            "driven_genes_from_pubmed",
        ),
    }


def _build_live_source_execution_summary(
    *,
    selected_sources: ResearchSpaceSourcePreferences,
    workspace_snapshot: JSONObject,
    status: str,
) -> JSONObject:
    return {
        "status": status,
        "selected_sources": json_object_or_empty(selected_sources),
        "source_results": _workspace_object(workspace_snapshot, "source_results"),
        "documents_ingested": workspace_snapshot.get("documents_ingested", 0),
        "proposal_count": workspace_snapshot.get("proposal_count", 0),
    }


def _build_live_bootstrap_summary(
    *, workspace_snapshot: JSONObject, status: str
) -> JSONObject:
    return {
        "status": status,
        "bootstrap_run_id": workspace_snapshot.get("bootstrap_run_id"),
        "bootstrap_source_type": workspace_snapshot.get("bootstrap_source_type"),
        "summary": _workspace_object(workspace_snapshot, "bootstrap_summary"),
    }


def _build_live_chase_rounds_artifact(
    *,
    workspace_snapshot: JSONObject,
    status: str,
) -> JSONObject:
    return {
        "status": status,
        "rounds": _collect_chase_round_summaries(workspace_snapshot=workspace_snapshot),
    }


def _store_pending_action_output_artifacts(
    *,
    artifact_store: HarnessArtifactStore,
    space_id: UUID,
    run_id: str,
    objective: str,
    seed_terms: list[str],
    sources: ResearchSpaceSourcePreferences,
    planner_mode: FullAIOrchestratorPlannerMode,
    max_depth: int,
    max_hypotheses: int,
) -> None:
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_PUBMED_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "status": "pending",
            "planned_source": "pubmed",
            "seed_terms": list(seed_terms),
        },
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_DRIVEN_TERMS_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "status": "pending",
            "objective": objective,
            "seed_terms": list(seed_terms),
        },
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_SOURCE_EXECUTION_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "status": "pending",
            "selected_sources": json_object_or_empty(sources),
        },
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_BOOTSTRAP_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "status": "pending",
            "max_depth": max_depth,
            "max_hypotheses": max_hypotheses,
        },
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_CHASE_ROUNDS_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "status": "pending",
            "planned_rounds": list(range(1, min(max_depth, 2) + 1)),
        },
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_BRIEF_METADATA_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "status": "pending",
            "result_key": "research_brief",
        },
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_SHADOW_PLANNER_TIMELINE_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "mode": _planner_mode_value(planner_mode),
            "checkpoint_count": 0,
            "checkpoints": [],
        },
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_SHADOW_PLANNER_RECOMMENDATION_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "mode": _planner_mode_value(planner_mode),
            "planner_status": "pending",
        },
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_SHADOW_PLANNER_COMPARISON_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "mode": _planner_mode_value(planner_mode),
            "comparison_status": "pending",
        },
    )
    _put_guarded_execution_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=run_id,
        planner_mode=planner_mode,
        actions=[],
    )


def store_pubmed_replay_bundle_artifact(
    *,
    artifact_store: HarnessArtifactStore,
    space_id: UUID,
    run_id: str,
    replay_bundle: ResearchInitPubMedReplayBundle,
) -> None:
    """Persist one prepared PubMed replay bundle for queued orchestrator reuse."""
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_PUBMED_REPLAY_ARTIFACT_KEY,
        media_type="application/json",
        content=serialize_pubmed_replay_bundle(replay_bundle),
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run_id,
        patch={"pubmed_replay_bundle_key": _PUBMED_REPLAY_ARTIFACT_KEY},
    )


def load_pubmed_replay_bundle_artifact(
    *,
    artifact_store: HarnessArtifactStore,
    space_id: UUID,
    run_id: str,
) -> ResearchInitPubMedReplayBundle | None:
    """Load a previously stored PubMed replay bundle for one orchestrator run."""
    artifact = artifact_store.get_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_PUBMED_REPLAY_ARTIFACT_KEY,
    )
    if artifact is None:
        return None
    return deserialize_pubmed_replay_bundle(artifact.content)
