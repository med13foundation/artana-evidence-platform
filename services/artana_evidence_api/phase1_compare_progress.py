"""Progress-observer helpers for Phase 1 comparison runs."""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar
from uuid import UUID

from artana_evidence_api.full_ai_orchestrator.guarded.rollout import (
    _guarded_profile_allows_chase,
    _guarded_rollout_profile,
)
from artana_evidence_api.full_ai_orchestrator_runtime import (
    _build_initial_decision_history,
    _FullAIOrchestratorProgressObserver,
    orchestrator_action_registry,
)
from artana_evidence_api.full_ai_orchestrator_shadow_planner import (
    build_shadow_planner_workspace_summary,
)
from artana_evidence_api.research_init_runtime import ResearchInitProgressObserver
from artana_evidence_api.research_init_source_results import build_source_results
from artana_evidence_api.types.common import JSONObject, json_object_or_empty

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.phase1_compare import Phase1CompareRequest

_T = TypeVar("_T")


def _source_payload(sources: object) -> JSONObject:
    return json_object_or_empty(sources)


def _build_compare_orchestrator_progress_observer(
    *,
    space_id: UUID,
    run_id: str,
    request: Phase1CompareRequest,
    artifact_store: HarnessArtifactStore,
) -> _FullAIOrchestratorProgressObserver:
    initial_decisions = _build_initial_decision_history(
        objective=request.objective,
        seed_terms=list(request.seed_terms),
        max_depth=request.max_depth,
        max_hypotheses=request.max_hypotheses,
        sources=request.sources,
    )
    action_registry = orchestrator_action_registry()
    guarded_rollout_profile = _guarded_rollout_profile(
        planner_mode=request.planner_mode,
    )
    initial_workspace_summary = build_shadow_planner_workspace_summary(
        checkpoint_key="before_first_action",
        mode=request.planner_mode.value,
        objective=request.objective,
        seed_terms=list(request.seed_terms),
        sources=request.sources,
        max_depth=request.max_depth,
        max_hypotheses=request.max_hypotheses,
        workspace_snapshot={
            "source_results": build_source_results(sources=request.sources),
            "current_round": 0,
            "documents_ingested": 0,
            "proposal_count": 0,
            "pending_questions": [],
            "errors": [],
        },
        prior_decisions=[
            decision.model_dump(mode="json") for decision in initial_decisions
        ],
        action_registry=action_registry,
    )
    return _FullAIOrchestratorProgressObserver(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=run_id,
        objective=request.objective,
        seed_terms=list(request.seed_terms),
        max_depth=request.max_depth,
        max_hypotheses=request.max_hypotheses,
        sources=request.sources,
        planner_mode=request.planner_mode,
        action_registry=action_registry,
        decisions=initial_decisions,
        initial_workspace_summary=initial_workspace_summary,
        phase_records={},
        guarded_rollout_profile=guarded_rollout_profile,
        guarded_chase_rollout_enabled=_guarded_profile_allows_chase(
            guarded_rollout_profile=guarded_rollout_profile,
        ),
    )


def _progress_event_payload(
    *,
    flow: str,
    phase: str,
    message: str,
    progress_percent: float,
    completed_steps: int,
    metadata: JSONObject | None = None,
) -> JSONObject:
    return {
        "flow": flow,
        "phase": phase,
        "message": message,
        "progress_percent": progress_percent,
        "completed_steps": completed_steps,
        "metadata": dict(metadata or {}),
    }


def _emit_compare_progress(
    *,
    flow: str,
    phase: str,
    message: str,
    progress_percent: float,
    completed_steps: int,
    metadata: JSONObject | None = None,
) -> None:
    payload = _progress_event_payload(
        flow=flow,
        phase=phase,
        message=message,
        progress_percent=progress_percent,
        completed_steps=completed_steps,
        metadata=metadata,
    )
    sys.stderr.write(json.dumps(payload, sort_keys=True) + "\n")
    sys.stderr.flush()


async def _await_compare_phase(
    *,
    awaitable: Awaitable[_T],
    timeout_seconds: float | None,
    flow: str,
    phase: str,
    message: str,
    metadata: JSONObject | None = None,
) -> _T:
    if timeout_seconds is None or timeout_seconds <= 0:
        return await awaitable
    try:
        return await asyncio.wait_for(awaitable, timeout=timeout_seconds)
    except TimeoutError as exc:
        timeout_metadata: JSONObject = dict(metadata or {})
        timeout_metadata["timeout_seconds"] = timeout_seconds
        _emit_compare_progress(
            flow=flow,
            phase=f"{phase}_timeout",
            message=f"{message} timed out after {timeout_seconds:.1f}s.",
            progress_percent=1.0,
            completed_steps=999,
            metadata=timeout_metadata,
        )
        raise TimeoutError(
            f"{flow} phase '{phase}' timed out after {timeout_seconds:.1f}s",
        ) from exc


@dataclass(slots=True)
class _CompareProgressObserver(ResearchInitProgressObserver):
    flow: str
    last_signature: tuple[str, str, int] | None = None

    def on_progress(
        self,
        *,
        phase: str,
        message: str,
        progress_percent: float,
        completed_steps: int,
        metadata: JSONObject,
        workspace_snapshot: JSONObject,
    ) -> None:
        del workspace_snapshot
        signature = (phase, message, completed_steps)
        if signature == self.last_signature:
            return
        self.last_signature = signature
        _emit_compare_progress(
            flow=self.flow,
            phase=phase,
            message=message,
            progress_percent=progress_percent,
            completed_steps=completed_steps,
            metadata=metadata,
        )


@dataclass(slots=True)
class _CompositeProgressObserver(ResearchInitProgressObserver):
    observers: tuple[ResearchInitProgressObserver, ...]

    def on_progress(
        self,
        *,
        phase: str,
        message: str,
        progress_percent: float,
        completed_steps: int,
        metadata: JSONObject,
        workspace_snapshot: JSONObject,
    ) -> None:
        for observer in self.observers:
            observer.on_progress(
                phase=phase,
                message=message,
                progress_percent=progress_percent,
                completed_steps=completed_steps,
                metadata=metadata,
                workspace_snapshot=workspace_snapshot,
            )


__all__ = [
    "_await_compare_phase",
    "_build_compare_orchestrator_progress_observer",
    "_emit_compare_progress",
]
