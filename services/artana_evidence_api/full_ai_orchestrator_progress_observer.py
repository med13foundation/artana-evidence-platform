"""Progress observer composition for the full-AI orchestrator runtime."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.full_ai_orchestrator_contracts import (
    FullAIOrchestratorPlannerMode,
    ResearchOrchestratorActionSpec,
    ResearchOrchestratorDecision,
    ResearchOrchestratorGuardedDecisionProof,
)
from artana_evidence_api.full_ai_orchestrator_guarded_selection import (
    _FullAIOrchestratorGuardedSelectionMixin,
)
from artana_evidence_api.full_ai_orchestrator_guarded_verification import (
    _FullAIOrchestratorGuardedVerificationMixin,
)
from artana_evidence_api.full_ai_orchestrator_progress_state import (
    _FullAIOrchestratorProgressStateMixin,
)
from artana_evidence_api.full_ai_orchestrator_runtime_constants import (
    _GUARDED_PROFILE_SHADOW_ONLY,
)
from artana_evidence_api.full_ai_orchestrator_shadow_checkpoints import (
    _FullAIOrchestratorShadowCheckpointMixin,
)
from artana_evidence_api.research_init_runtime import ResearchInitProgressObserver
from artana_evidence_api.types.common import JSONObject, ResearchSpaceSourcePreferences

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore


@dataclass(slots=True)
class _FullAIOrchestratorProgressObserver(
    _FullAIOrchestratorProgressStateMixin,
    _FullAIOrchestratorGuardedSelectionMixin,
    _FullAIOrchestratorGuardedVerificationMixin,
    _FullAIOrchestratorShadowCheckpointMixin,
    ResearchInitProgressObserver,
):
    """Mirror research-init phase changes into orchestrator artifacts."""

    artifact_store: HarnessArtifactStore
    space_id: UUID
    run_id: str
    objective: str
    seed_terms: list[str]
    max_depth: int
    max_hypotheses: int
    sources: ResearchSpaceSourcePreferences
    planner_mode: FullAIOrchestratorPlannerMode
    action_registry: tuple[ResearchOrchestratorActionSpec, ...]
    decisions: list[ResearchOrchestratorDecision]
    initial_workspace_summary: JSONObject
    phase_records: dict[str, list[JSONObject]]
    shadow_timeline: list[JSONObject] = field(default_factory=list)
    guarded_execution_log: list[JSONObject] = field(default_factory=list)
    guarded_decision_proofs: list[ResearchOrchestratorGuardedDecisionProof] = field(
        default_factory=list,
    )
    emitted_shadow_checkpoints: set[str] = field(default_factory=set)
    guarded_rollout_profile: str = _GUARDED_PROFILE_SHADOW_ONLY
    guarded_rollout_profile_source: str = "resolved"
    guarded_chase_rollout_enabled: bool = False
    _shadow_planner_task: asyncio.Task[None] | None = None
    _progress_artifact_backoff_until: float | None = None
    _progress_decision_backoff_until: float | None = None
