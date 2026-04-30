"""Artifact writers for guarded full-AI orchestration state."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.full_ai_orchestrator.guarded.decision_proofs import (
    _guarded_decision_proof_summary,
)
from artana_evidence_api.full_ai_orchestrator.guarded.readiness import (
    _guarded_execution_summary,
    _guarded_readiness_summary,
)
from artana_evidence_api.full_ai_orchestrator.runtime_constants import (
    _DECISION_HISTORY_ARTIFACT_KEY,
    _GUARDED_DECISION_PROOF_SUMMARY_ARTIFACT_KEY,
    _GUARDED_EXECUTION_ARTIFACT_KEY,
    _GUARDED_READINESS_ARTIFACT_KEY,
    _SHADOW_PLANNER_COMPARISON_ARTIFACT_KEY,
    _SHADOW_PLANNER_RECOMMENDATION_ARTIFACT_KEY,
    _SHADOW_PLANNER_TIMELINE_ARTIFACT_KEY,
    _SHADOW_PLANNER_WORKSPACE_ARTIFACT_KEY,
)
from artana_evidence_api.full_ai_orchestrator_contracts import (
    FullAIOrchestratorPlannerMode,
    ResearchOrchestratorDecision,
    ResearchOrchestratorGuardedDecisionProof,
)
from artana_evidence_api.types.common import JSONObject

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore


def _put_decision_history_artifact(
    *,
    artifact_store: HarnessArtifactStore,
    space_id: UUID,
    run_id: str,
    decisions: list[ResearchOrchestratorDecision],
) -> None:
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_DECISION_HISTORY_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "decisions": [decision.model_dump(mode="json") for decision in decisions],
            "decision_count": len(decisions),
        },
    )


def _put_shadow_planner_artifacts(
    *,
    artifact_store: HarnessArtifactStore,
    space_id: UUID,
    run_id: str,
    timeline: list[JSONObject],
    latest_summary: JSONObject,
    mode: str,
) -> None:
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_SHADOW_PLANNER_TIMELINE_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "mode": mode,
            "checkpoints": timeline,
            "checkpoint_count": len(timeline),
        },
    )
    latest_workspace_summary = latest_summary.get("latest_workspace_summary")
    if isinstance(latest_workspace_summary, dict):
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run_id,
            artifact_key=_SHADOW_PLANNER_WORKSPACE_ARTIFACT_KEY,
            media_type="application/json",
            content=latest_workspace_summary,
        )
    latest_recommendation = latest_summary.get("latest_recommendation")
    if isinstance(latest_recommendation, dict):
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run_id,
            artifact_key=_SHADOW_PLANNER_RECOMMENDATION_ARTIFACT_KEY,
            media_type="application/json",
            content=latest_recommendation,
        )
    latest_comparison = latest_summary.get("latest_comparison")
    if isinstance(latest_comparison, dict):
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run_id,
            artifact_key=_SHADOW_PLANNER_COMPARISON_ARTIFACT_KEY,
            media_type="application/json",
            content=latest_comparison,
        )


def _put_guarded_execution_artifact(
    *,
    artifact_store: HarnessArtifactStore,
    space_id: UUID,
    run_id: str,
    planner_mode: FullAIOrchestratorPlannerMode,
    actions: list[JSONObject],
) -> None:
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_GUARDED_EXECUTION_ARTIFACT_KEY,
        media_type="application/json",
        content=_guarded_execution_summary(
            planner_mode=planner_mode,
            actions=actions,
        ),
    )


def _put_guarded_decision_proof_artifacts(
    *,
    artifact_store: HarnessArtifactStore,
    space_id: UUID,
    run_id: str,
    planner_mode: FullAIOrchestratorPlannerMode,
    guarded_rollout_profile: str,
    guarded_rollout_profile_source: str = "resolved",
    proofs: list[ResearchOrchestratorGuardedDecisionProof],
) -> None:
    for proof in proofs:
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run_id,
            artifact_key=proof.artifact_key,
            media_type="application/json",
            content=proof.model_dump(mode="json"),
        )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_GUARDED_DECISION_PROOF_SUMMARY_ARTIFACT_KEY,
        media_type="application/json",
        content=_guarded_decision_proof_summary(
            planner_mode=planner_mode,
            guarded_rollout_profile=guarded_rollout_profile,
            guarded_rollout_profile_source=guarded_rollout_profile_source,
            proofs=proofs,
        ),
    )


def _put_guarded_readiness_artifact(
    *,
    artifact_store: HarnessArtifactStore,
    space_id: UUID,
    run_id: str,
    planner_mode: FullAIOrchestratorPlannerMode,
    guarded_rollout_profile: str,
    guarded_rollout_profile_source: str = "resolved",
    actions: list[JSONObject],
    proofs: list[ResearchOrchestratorGuardedDecisionProof] | None = None,
) -> None:
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_GUARDED_READINESS_ARTIFACT_KEY,
        media_type="application/json",
        content=_guarded_readiness_summary(
            planner_mode=planner_mode,
            guarded_rollout_profile=guarded_rollout_profile,
            guarded_rollout_profile_source=guarded_rollout_profile_source,
            actions=actions,
            proofs=proofs,
        ),
    )


__all__ = [
    "_put_decision_history_artifact",
    "_put_guarded_decision_proof_artifacts",
    "_put_guarded_execution_artifact",
    "_put_guarded_readiness_artifact",
    "_put_shadow_planner_artifacts",
]
