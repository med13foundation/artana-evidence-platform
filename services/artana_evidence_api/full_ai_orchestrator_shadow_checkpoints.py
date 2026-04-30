# mypy: disable-error-code="attr-defined,has-type,no-any-return"
"""Shadow-checkpoint mixin for the full-AI orchestrator progress observer."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import cast

from artana_evidence_api.full_ai_orchestrator_common_support import (
    _planner_mode_value,
    _workspace_list,
)
from artana_evidence_api.full_ai_orchestrator_contracts import (
    ResearchOrchestratorDecision,
)
from artana_evidence_api.full_ai_orchestrator_guarded_support import (
    _put_shadow_planner_artifacts,
)
from artana_evidence_api.full_ai_orchestrator_runtime_constants import (
    _HARNESS_ID,
    _SHADOW_PLANNER_CHECKPOINT_ORDER,
    _SHADOW_PLANNER_COMPARISON_ARTIFACT_KEY,
    _SHADOW_PLANNER_RECOMMENDATION_ARTIFACT_KEY,
    _SHADOW_PLANNER_TIMELINE_ARTIFACT_KEY,
    _STEP_KEY_VERSION,
)
from artana_evidence_api.full_ai_orchestrator_shadow_planner import (
    ShadowPlannerRecommendationResult,
    build_shadow_planner_comparison,
    build_shadow_planner_workspace_summary,
)
from artana_evidence_api.full_ai_orchestrator_shadow_planner import (
    recommend_shadow_planner_action as _default_recommend_shadow_planner_action,
)
from artana_evidence_api.full_ai_orchestrator_shadow_support import (
    _build_shadow_planner_summary,
    _checkpoint_phase_record_map,
    _checkpoint_target_decision,
    _shadow_planner_recommendation_payload,
)
from artana_evidence_api.types.common import JSONObject, json_object

_ShadowPlannerRecommender = Callable[..., Awaitable[ShadowPlannerRecommendationResult]]


async def recommend_shadow_planner_action(
    **kwargs: object,
) -> ShadowPlannerRecommendationResult:
    facade = sys.modules.get("artana_evidence_api.full_ai_orchestrator_runtime")
    candidate = getattr(facade, "recommend_shadow_planner_action", None)
    if candidate is None or candidate is recommend_shadow_planner_action:
        candidate = _default_recommend_shadow_planner_action
    return await cast("_ShadowPlannerRecommender", candidate)(**kwargs)


class _FullAIOrchestratorShadowCheckpointMixin:
    def enqueue_initial_shadow_checkpoint(self) -> None:
        self._enqueue_shadow_checkpoint(
            checkpoint_key="before_first_action",
            workspace_summary=self.initial_workspace_summary,
            deterministic_decisions=[
                decision.model_copy(deep=True) for decision in self.decisions
            ],
        )

    async def finalize_shadow_planner(
        self,
        *,
        final_workspace_snapshot: JSONObject,
        final_decisions: list[ResearchOrchestratorDecision],
    ) -> list[JSONObject]:
        await self.wait_for_shadow_planner_updates()
        checkpoint_records = _checkpoint_phase_record_map(
            initial_workspace_summary=self.initial_workspace_summary,
            initial_decisions=self.decisions,
            phase_records=self.phase_records,
            final_workspace_snapshot=final_workspace_snapshot,
            final_decisions=final_decisions,
        )
        for checkpoint_key in _SHADOW_PLANNER_CHECKPOINT_ORDER:
            if checkpoint_key in self.emitted_shadow_checkpoints:
                continue
            record = checkpoint_records.get(checkpoint_key)
            if not isinstance(record, dict):
                continue
            record_workspace = record.get("workspace_summary")
            if isinstance(record_workspace, dict):
                workspace_summary = record_workspace
            else:
                workspace_snapshot = record.get("workspace_snapshot")
                workspace_summary = build_shadow_planner_workspace_summary(
                    checkpoint_key=checkpoint_key,
                    mode=_planner_mode_value(self.planner_mode),
                    objective=self.objective,
                    seed_terms=self.seed_terms,
                    sources=self.sources,
                    max_depth=self.max_depth,
                    max_hypotheses=self.max_hypotheses,
                    workspace_snapshot=(
                        workspace_snapshot
                        if isinstance(workspace_snapshot, dict)
                        else {}
                    ),
                    prior_decisions=[
                        decision_payload
                        for item in _workspace_list(record, "decisions")
                        if (decision_payload := json_object(item)) is not None
                    ],
                    action_registry=self.action_registry,
                )
            await self._emit_shadow_checkpoint(
                checkpoint_key=checkpoint_key,
                workspace_summary=workspace_summary,
                deterministic_decisions=final_decisions,
            )
        return list(self.shadow_timeline)

    async def wait_for_shadow_planner_updates(self) -> None:
        if self._shadow_planner_task is None:
            return
        await self._shadow_planner_task

    def _enqueue_shadow_checkpoint_updates(
        self,
        *,
        phase: str,
        workspace_snapshot: JSONObject,
    ) -> None:
        for checkpoint_key in self._checkpoint_keys_for_phase(
            phase=phase,
            workspace_snapshot=workspace_snapshot,
        ):
            workspace_summary = build_shadow_planner_workspace_summary(
                checkpoint_key=checkpoint_key,
                mode=_planner_mode_value(self.planner_mode),
                objective=self.objective,
                seed_terms=self.seed_terms,
                sources=self.sources,
                max_depth=self.max_depth,
                max_hypotheses=self.max_hypotheses,
                workspace_snapshot=workspace_snapshot,
                prior_decisions=[
                    decision.model_dump(mode="json") for decision in self.decisions
                ],
                action_registry=self.action_registry,
            )
            self._enqueue_shadow_checkpoint(
                checkpoint_key=checkpoint_key,
                workspace_summary=workspace_summary,
                deterministic_decisions=[
                    decision.model_copy(deep=True) for decision in self.decisions
                ],
            )

    def _enqueue_shadow_checkpoint(
        self,
        *,
        checkpoint_key: str,
        workspace_summary: JSONObject,
        deterministic_decisions: list[ResearchOrchestratorDecision],
    ) -> None:
        if checkpoint_key in self.emitted_shadow_checkpoints:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        previous_task = self._shadow_planner_task
        workspace_summary_copy = deepcopy(workspace_summary)
        decisions_copy = [
            decision.model_copy(deep=True) for decision in deterministic_decisions
        ]

        async def _run_after_previous() -> None:
            if previous_task is not None:
                await previous_task
            if checkpoint_key in self.emitted_shadow_checkpoints:
                return
            await self._emit_shadow_checkpoint(
                checkpoint_key=checkpoint_key,
                workspace_summary=workspace_summary_copy,
                deterministic_decisions=decisions_copy,
            )

        self._shadow_planner_task = loop.create_task(_run_after_previous())

    async def _emit_shadow_checkpoint(
        self,
        *,
        checkpoint_key: str,
        workspace_summary: JSONObject,
        deterministic_decisions: list[ResearchOrchestratorDecision],
    ) -> tuple[ShadowPlannerRecommendationResult, JSONObject]:
        if checkpoint_key in self.emitted_shadow_checkpoints:
            raise RuntimeError(
                f"Checkpoint '{checkpoint_key}' was already emitted and cannot be replayed synchronously.",
            )
        planner_result = await recommend_shadow_planner_action(
            checkpoint_key=checkpoint_key,
            objective=self.objective,
            workspace_summary=workspace_summary,
            sources=self.sources,
            action_registry=self.action_registry,
            harness_id=_HARNESS_ID,
            step_key_version=_STEP_KEY_VERSION,
        )
        comparison = build_shadow_planner_comparison(
            checkpoint_key=checkpoint_key,
            planner_result=planner_result,
            deterministic_target=_checkpoint_target_decision(
                checkpoint_key=checkpoint_key,
                decisions=deterministic_decisions,
                workspace_summary=workspace_summary,
            ),
            workspace_summary=workspace_summary,
            mode=_planner_mode_value(self.planner_mode),
        )
        self.shadow_timeline.append(
            {
                "checkpoint_key": checkpoint_key,
                "workspace_summary": workspace_summary,
                "recommendation": _shadow_planner_recommendation_payload(
                    planner_result=planner_result,
                    mode=_planner_mode_value(self.planner_mode),
                ),
                "comparison": comparison,
            }
        )
        self.emitted_shadow_checkpoints.add(checkpoint_key)
        shadow_planner_summary = _build_shadow_planner_summary(
            timeline=self.shadow_timeline,
            mode=_planner_mode_value(self.planner_mode),
        )
        _put_shadow_planner_artifacts(
            artifact_store=self.artifact_store,
            space_id=self.space_id,
            run_id=self.run_id,
            timeline=self.shadow_timeline,
            latest_summary=shadow_planner_summary,
            mode=_planner_mode_value(self.planner_mode),
        )
        self.artifact_store.patch_workspace(
            space_id=self.space_id,
            run_id=self.run_id,
            patch={
                "shadow_planner": shadow_planner_summary,
                "shadow_planner_mode": _planner_mode_value(self.planner_mode),
                "planner_execution_mode": _planner_mode_value(self.planner_mode),
                "shadow_planner_timeline_key": _SHADOW_PLANNER_TIMELINE_ARTIFACT_KEY,
                "shadow_planner_recommendation_key": (
                    _SHADOW_PLANNER_RECOMMENDATION_ARTIFACT_KEY
                ),
                "shadow_planner_comparison_key": (
                    _SHADOW_PLANNER_COMPARISON_ARTIFACT_KEY
                ),
            },
        )
        return planner_result, comparison

    def _shadow_timeline_entry(self, checkpoint_key: str) -> JSONObject | None:
        for entry in reversed(self.shadow_timeline):
            if entry.get("checkpoint_key") != checkpoint_key:
                continue
            if not isinstance(entry.get("recommendation"), dict):
                continue
            if not isinstance(entry.get("comparison"), dict):
                continue
            return entry
        return None

    async def _get_or_emit_shadow_checkpoint(
        self,
        *,
        checkpoint_key: str,
        workspace_summary: JSONObject,
        deterministic_decisions: list[ResearchOrchestratorDecision],
    ) -> tuple[JSONObject, JSONObject]:
        await self.wait_for_shadow_planner_updates()
        existing_entry = self._shadow_timeline_entry(checkpoint_key)
        if existing_entry is not None:
            recommendation = existing_entry.get("recommendation")
            comparison = existing_entry.get("comparison")
            if isinstance(recommendation, dict) and isinstance(comparison, dict):
                return dict(recommendation), dict(comparison)

        planner_result, comparison = await self._emit_shadow_checkpoint(
            checkpoint_key=checkpoint_key,
            workspace_summary=workspace_summary,
            deterministic_decisions=deterministic_decisions,
        )
        return (
            _shadow_planner_recommendation_payload(
                planner_result=planner_result,
                mode=_planner_mode_value(self.planner_mode),
            ),
            comparison,
        )

    def _checkpoint_keys_for_phase(
        self,
        *,
        phase: str,
        workspace_snapshot: JSONObject,
    ) -> list[str]:
        checkpoint_keys: list[str] = []
        if phase == "document_ingestion":
            checkpoint_keys = ["after_pubmed_discovery"]
        elif phase == "structured_enrichment":
            checkpoint_keys = [
                "after_pubmed_ingest_extract",
                "after_driven_terms_ready",
            ]
        elif phase == "chase_round_1":
            checkpoint_keys = ["after_bootstrap"]
        elif phase == "chase_round_2":
            checkpoint_keys = ["after_chase_round_1"]
        elif phase == "deferred_mondo":
            checkpoint_keys = self._checkpoint_keys_for_terminal_phase(
                workspace_snapshot=workspace_snapshot,
                include_terminal=False,
            )
        elif phase == "completed":
            checkpoint_keys = self._checkpoint_keys_for_terminal_phase(
                workspace_snapshot=workspace_snapshot,
                include_terminal=True,
            )
        return checkpoint_keys

    def _checkpoint_keys_for_terminal_phase(
        self,
        *,
        workspace_snapshot: JSONObject,
        include_terminal: bool,
    ) -> list[str]:
        checkpoint_keys: list[str] = []
        if "after_bootstrap" not in self.emitted_shadow_checkpoints:
            checkpoint_keys.append("after_bootstrap")
        if (
            isinstance(workspace_snapshot.get("chase_round_1"), dict)
            and "after_chase_round_1" not in self.emitted_shadow_checkpoints
        ):
            checkpoint_keys.append("after_chase_round_1")
        if (
            isinstance(workspace_snapshot.get("chase_round_2"), dict)
            and "after_chase_round_2" not in self.emitted_shadow_checkpoints
        ):
            checkpoint_keys.append("after_chase_round_2")
        if include_terminal:
            checkpoint_keys.extend(
                checkpoint_key
                for checkpoint_key in (
                    "before_brief_generation",
                    "before_terminal_stop",
                )
                if checkpoint_key not in self.emitted_shadow_checkpoints
            )
        return checkpoint_keys
