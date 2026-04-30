# mypy: disable-error-code="attr-defined,has-type,no-any-return"
"""Guarded planner-selection mixin for the full-AI orchestrator."""

from __future__ import annotations

from artana_evidence_api.full_ai_orchestrator.guarded.rollout import (
    _guarded_profile_allows,
)
from artana_evidence_api.full_ai_orchestrator.guarded.support import (
    _decision_payload_from_recommendation,
    _guarded_action_allowed_by_profile,
    _guarded_action_with_policy,
    _guarded_rejection_reason,
    _guarded_strategy_for_recommendation,
    _put_guarded_execution_artifact,
    _put_guarded_readiness_artifact,
)
from artana_evidence_api.full_ai_orchestrator.runtime_constants import (
    _GUARDED_SKIP_CHASE_ROUND_NUMBER,
    _GUARDED_STRATEGY_BRIEF_GENERATION,
    _GUARDED_STRATEGY_CHASE_SELECTION,
    _GUARDED_STRATEGY_STRUCTURED_SOURCE,
    _GUARDED_STRATEGY_TERMINAL_CONTROL,
)
from artana_evidence_api.full_ai_orchestrator.shadow.support import (
    _accepted_guarded_chase_selection_action,
    _accepted_guarded_control_flow_action,
    _accepted_guarded_generate_brief_action,
    _accepted_guarded_structured_source_action,
)
from artana_evidence_api.full_ai_orchestrator.shadow_planner import (
    build_shadow_planner_workspace_summary,
)
from artana_evidence_api.full_ai_orchestrator.workspace_support import (
    _planner_mode_value,
)
from artana_evidence_api.full_ai_orchestrator_contracts import (
    FullAIOrchestratorPlannerMode,
    ResearchOrchestratorActionType,
    ResearchOrchestratorChaseCandidate,
    ResearchOrchestratorChaseSelection,
)
from artana_evidence_api.types.common import JSONObject, json_string_list

__all__ = ["_FullAIOrchestratorGuardedSelectionMixin"]


class _FullAIOrchestratorGuardedSelectionMixin:
    async def maybe_skip_chase_round(  # noqa: PLR0911
        self,
        *,
        next_round_number: int,
        workspace_snapshot: JSONObject,
    ) -> bool:
        if self.planner_mode is not FullAIOrchestratorPlannerMode.GUARDED:
            return False
        if not self.guarded_chase_rollout_enabled:
            return False
        if next_round_number != _GUARDED_SKIP_CHASE_ROUND_NUMBER:
            return False
        if not isinstance(workspace_snapshot.get("chase_round_1"), dict):
            return False

        checkpoint_key = "after_chase_round_1"
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
        recommendation_payload, comparison = await self._get_or_emit_shadow_checkpoint(
            checkpoint_key=checkpoint_key,
            workspace_summary=workspace_summary,
            deterministic_decisions=[
                decision.model_copy(deep=True) for decision in self.decisions
            ],
        )
        guarded_action = _accepted_guarded_generate_brief_action(
            recommendation_payload=recommendation_payload,
            comparison=comparison,
        )
        if guarded_action is None:
            guarded_action = _accepted_guarded_control_flow_action(
                recommendation_payload=recommendation_payload,
                comparison=comparison,
            )
        if guarded_action is None:
            decision_payload = _decision_payload_from_recommendation(
                recommendation_payload,
            )
            if (
                decision_payload.get("action_type")
                == ResearchOrchestratorActionType.RUN_CHASE_ROUND.value
            ):
                return False
            self._record_guarded_decision_proof(
                checkpoint_key=checkpoint_key,
                guarded_strategy=_guarded_strategy_for_recommendation(
                    recommendation_payload=recommendation_payload,
                    default_strategy=_GUARDED_STRATEGY_BRIEF_GENERATION,
                ),
                decision_outcome="blocked",
                outcome_reason=_guarded_rejection_reason(
                    recommendation_payload=recommendation_payload,
                    comparison=comparison,
                    default_reason="not_an_eligible_guarded_terminal_action",
                ),
                recommendation_payload=recommendation_payload,
                comparison=comparison,
            )
            return False
        if not _guarded_action_allowed_by_profile(
            action=guarded_action,
            guarded_rollout_profile=self.guarded_rollout_profile,
        ):
            self._record_guarded_decision_proof(
                checkpoint_key=checkpoint_key,
                guarded_strategy=str(guarded_action["guarded_strategy"]),
                decision_outcome="blocked",
                outcome_reason="guarded_rollout_profile_disallows_strategy",
                recommendation_payload=recommendation_payload,
                comparison=comparison,
                guarded_action=guarded_action,
                policy_allowed=False,
            )
            return False
        guarded_action = _guarded_action_with_policy(
            action=guarded_action,
            guarded_rollout_profile=self.guarded_rollout_profile,
            guarded_rollout_profile_source=self.guarded_rollout_profile_source,
        )
        self._record_guarded_decision_proof(
            checkpoint_key=checkpoint_key,
            guarded_strategy=str(guarded_action["guarded_strategy"]),
            decision_outcome="allowed",
            outcome_reason="guarded_policy_allowed",
            recommendation_payload=recommendation_payload,
            comparison=comparison,
            guarded_action=guarded_action,
            policy_allowed=True,
        )

        self.guarded_execution_log.append(guarded_action)
        guarded_action_type = guarded_action.get("applied_action_type")
        guarded_stop_reason = guarded_action.get("stop_reason")
        self._update_decision(
            action_type=ResearchOrchestratorActionType.RUN_CHASE_ROUND,
            round_number=next_round_number,
            status="skipped",
            metadata={"guarded_execution": guarded_action},
            stop_reason=(
                guarded_stop_reason
                if isinstance(guarded_stop_reason, str)
                else "guarded_generate_brief"
            ),
        )
        self._persist()
        if guarded_action_type == ResearchOrchestratorActionType.GENERATE_BRIEF.value:
            self._persist_guarded_execution_state(
                extra_patch={
                    "guarded_stop_after_chase_round": next_round_number - 1,
                },
            )
        else:
            self._persist_guarded_execution_state(
                extra_patch={
                    "guarded_terminal_control_after_chase_round": (
                        next_round_number - 1
                    ),
                    "guarded_terminal_control_action": {
                        "action_type": guarded_action_type,
                        "stop_reason": guarded_stop_reason,
                        "checkpoint_key": guarded_action.get("checkpoint_key"),
                        "human_review_required": (
                            guarded_action_type
                            == ResearchOrchestratorActionType.ESCALATE_TO_HUMAN.value
                        ),
                    },
                    "guarded_human_review_required": (
                        guarded_action_type
                        == ResearchOrchestratorActionType.ESCALATE_TO_HUMAN.value
                    ),
                },
            )
        return True

    async def maybe_select_structured_enrichment_sources(  # noqa: PLR0911
        self,
        *,
        available_source_keys: tuple[str, ...],
        workspace_snapshot: JSONObject,
    ) -> tuple[str, ...] | None:
        if self.planner_mode is not FullAIOrchestratorPlannerMode.GUARDED:
            return None
        if not _guarded_profile_allows(
            guarded_rollout_profile=self.guarded_rollout_profile,
            guarded_strategy=_GUARDED_STRATEGY_STRUCTURED_SOURCE,
        ):
            return None
        if len(available_source_keys) <= 1:
            return None

        checkpoint_key = "after_driven_terms_ready"
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
        recommendation_payload, comparison = await self._get_or_emit_shadow_checkpoint(
            checkpoint_key=checkpoint_key,
            workspace_summary=workspace_summary,
            deterministic_decisions=[
                decision.model_copy(deep=True) for decision in self.decisions
            ],
        )
        guarded_action = _accepted_guarded_structured_source_action(
            recommendation_payload=recommendation_payload,
            comparison=comparison,
            available_source_keys=available_source_keys,
        )
        if guarded_action is None:
            decision = _decision_payload_from_recommendation(recommendation_payload)
            recommended_source_key = decision.get("source_key")
            self._record_guarded_decision_proof(
                checkpoint_key=checkpoint_key,
                guarded_strategy=_GUARDED_STRATEGY_STRUCTURED_SOURCE,
                decision_outcome="blocked",
                outcome_reason=_guarded_rejection_reason(
                    recommendation_payload=recommendation_payload,
                    comparison=comparison,
                    default_reason="not_an_eligible_guarded_structured_source_action",
                ),
                recommendation_payload=recommendation_payload,
                comparison=comparison,
                disabled_source_violation=(
                    isinstance(recommended_source_key, str)
                    and recommended_source_key not in set(available_source_keys)
                ),
            )
            return None
        if not _guarded_action_allowed_by_profile(
            action=guarded_action,
            guarded_rollout_profile=self.guarded_rollout_profile,
        ):
            self._record_guarded_decision_proof(
                checkpoint_key=checkpoint_key,
                guarded_strategy=_GUARDED_STRATEGY_STRUCTURED_SOURCE,
                decision_outcome="blocked",
                outcome_reason="guarded_rollout_profile_disallows_strategy",
                recommendation_payload=recommendation_payload,
                comparison=comparison,
                guarded_action=guarded_action,
                policy_allowed=False,
            )
            return None
        guarded_action = _guarded_action_with_policy(
            action=guarded_action,
            guarded_rollout_profile=self.guarded_rollout_profile,
            guarded_rollout_profile_source=self.guarded_rollout_profile_source,
        )
        self._record_guarded_decision_proof(
            checkpoint_key=checkpoint_key,
            guarded_strategy=_GUARDED_STRATEGY_STRUCTURED_SOURCE,
            decision_outcome="allowed",
            outcome_reason="guarded_policy_allowed",
            recommendation_payload=recommendation_payload,
            comparison=comparison,
            guarded_action=guarded_action,
            policy_allowed=True,
        )

        selected_source_key = guarded_action.get("applied_source_key")
        if not isinstance(selected_source_key, str):
            return None
        ordered_source_keys = [selected_source_key]
        ordered_source_keys.extend(
            source_key
            for source_key in available_source_keys
            if source_key != selected_source_key
        )
        guarded_action["ordered_source_keys"] = ordered_source_keys
        guarded_action["deferred_source_keys"] = []
        self.guarded_execution_log.append(guarded_action)
        _put_guarded_execution_artifact(
            artifact_store=self.artifact_store,
            space_id=self.space_id,
            run_id=self.run_id,
            planner_mode=self.planner_mode,
            actions=self.guarded_execution_log,
        )
        _put_guarded_readiness_artifact(
            artifact_store=self.artifact_store,
            space_id=self.space_id,
            run_id=self.run_id,
            planner_mode=self.planner_mode,
            guarded_rollout_profile=self.guarded_rollout_profile,
            guarded_rollout_profile_source=self.guarded_rollout_profile_source,
            actions=self.guarded_execution_log,
            proofs=self.guarded_decision_proofs,
        )
        for source_index, source_key in enumerate(ordered_source_keys):
            self._update_decision(
                action_type=ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
                round_number=0,
                source_key=source_key,
                status="running" if source_index == 0 else "pending",
                metadata={
                    "guarded_execution": guarded_action,
                    "guarded_priority": source_index,
                },
            )
        self._persist()
        self._persist_guarded_execution_state(
            extra_patch={
                "guarded_structured_enrichment_selection": {
                    "selected_source_key": selected_source_key,
                    "ordered_source_keys": ordered_source_keys,
                    "deferred_source_keys": [],
                },
            },
        )
        return tuple(ordered_source_keys)

    async def maybe_select_chase_round_selection(  # noqa: PLR0911
        self,
        *,
        round_number: int,
        chase_candidates: tuple[ResearchOrchestratorChaseCandidate, ...],
        deterministic_selection: ResearchOrchestratorChaseSelection,
        workspace_snapshot: JSONObject,
    ) -> ResearchOrchestratorChaseSelection | None:
        if self.planner_mode is not FullAIOrchestratorPlannerMode.GUARDED:
            return None
        if not self.guarded_chase_rollout_enabled:
            return None
        checkpoint_key_by_round = {
            1: "after_bootstrap",
            2: "after_chase_round_1",
        }
        checkpoint_key = checkpoint_key_by_round.get(round_number)
        if checkpoint_key is None:
            return None

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
        recommendation_payload, comparison = await self._get_or_emit_shadow_checkpoint(
            checkpoint_key=checkpoint_key,
            workspace_summary=workspace_summary,
            deterministic_decisions=[
                decision.model_copy(deep=True) for decision in self.decisions
            ],
        )

        guarded_action = _accepted_guarded_chase_selection_action(
            recommendation_payload=recommendation_payload,
            comparison=comparison,
            round_number=round_number,
            chase_candidates=chase_candidates,
            deterministic_selection=deterministic_selection,
        )
        if guarded_action is not None:
            if not _guarded_action_allowed_by_profile(
                action=guarded_action,
                guarded_rollout_profile=self.guarded_rollout_profile,
            ):
                self._record_guarded_decision_proof(
                    checkpoint_key=checkpoint_key,
                    guarded_strategy=_GUARDED_STRATEGY_CHASE_SELECTION,
                    decision_outcome="blocked",
                    outcome_reason="guarded_rollout_profile_disallows_strategy",
                    recommendation_payload=recommendation_payload,
                    comparison=comparison,
                    guarded_action=guarded_action,
                    policy_allowed=False,
                )
                return None
            guarded_action = _guarded_action_with_policy(
                action=guarded_action,
                guarded_rollout_profile=self.guarded_rollout_profile,
                guarded_rollout_profile_source=self.guarded_rollout_profile_source,
            )
            self._record_guarded_decision_proof(
                checkpoint_key=checkpoint_key,
                guarded_strategy=_GUARDED_STRATEGY_CHASE_SELECTION,
                decision_outcome="allowed",
                outcome_reason="guarded_policy_allowed",
                recommendation_payload=recommendation_payload,
                comparison=comparison,
                guarded_action=guarded_action,
                policy_allowed=True,
            )
            self.guarded_execution_log.append(guarded_action)
            self._persist_guarded_execution_state(
                extra_patch={
                    f"guarded_chase_round_{round_number}": {
                        "selected_entity_ids": guarded_action["selected_entity_ids"],
                        "selected_labels": guarded_action["selected_labels"],
                        "selection_basis": guarded_action["selection_basis"],
                    },
                },
            )
            return ResearchOrchestratorChaseSelection(
                selected_entity_ids=json_string_list(
                    guarded_action.get("selected_entity_ids")
                ),
                selected_labels=json_string_list(guarded_action.get("selected_labels")),
                stop_instead=False,
                stop_reason=None,
                selection_basis=str(guarded_action["selection_basis"]),
            )

        control_flow_action = _accepted_guarded_control_flow_action(
            recommendation_payload=recommendation_payload,
            comparison=comparison,
        )
        if control_flow_action is None:
            self._record_guarded_decision_proof(
                checkpoint_key=checkpoint_key,
                guarded_strategy=_guarded_strategy_for_recommendation(
                    recommendation_payload=recommendation_payload,
                    default_strategy=_GUARDED_STRATEGY_CHASE_SELECTION,
                ),
                decision_outcome="blocked",
                outcome_reason=_guarded_rejection_reason(
                    recommendation_payload=recommendation_payload,
                    comparison=comparison,
                    default_reason="not_an_eligible_guarded_chase_action",
                ),
                recommendation_payload=recommendation_payload,
                comparison=comparison,
            )
            return None
        if not _guarded_action_allowed_by_profile(
            action=control_flow_action,
            guarded_rollout_profile=self.guarded_rollout_profile,
        ):
            self._record_guarded_decision_proof(
                checkpoint_key=checkpoint_key,
                guarded_strategy=_GUARDED_STRATEGY_TERMINAL_CONTROL,
                decision_outcome="blocked",
                outcome_reason="guarded_rollout_profile_disallows_strategy",
                recommendation_payload=recommendation_payload,
                comparison=comparison,
                guarded_action=control_flow_action,
                policy_allowed=False,
            )
            return None
        control_flow_action = _guarded_action_with_policy(
            action=control_flow_action,
            guarded_rollout_profile=self.guarded_rollout_profile,
            guarded_rollout_profile_source=self.guarded_rollout_profile_source,
        )
        self._record_guarded_decision_proof(
            checkpoint_key=checkpoint_key,
            guarded_strategy=_GUARDED_STRATEGY_TERMINAL_CONTROL,
            decision_outcome="allowed",
            outcome_reason="guarded_policy_allowed",
            recommendation_payload=recommendation_payload,
            comparison=comparison,
            guarded_action=control_flow_action,
            policy_allowed=True,
        )
        self.guarded_execution_log.append(control_flow_action)
        self._persist_guarded_execution_state(
            extra_patch={
                "guarded_terminal_control_after_chase_round": round_number - 1,
                "guarded_terminal_control_action": {
                    "action_type": control_flow_action.get("applied_action_type"),
                    "stop_reason": control_flow_action.get("stop_reason"),
                    "checkpoint_key": control_flow_action.get("checkpoint_key"),
                    "human_review_required": (
                        control_flow_action.get("applied_action_type")
                        == ResearchOrchestratorActionType.ESCALATE_TO_HUMAN.value
                    ),
                },
                "guarded_human_review_required": (
                    control_flow_action.get("applied_action_type")
                    == ResearchOrchestratorActionType.ESCALATE_TO_HUMAN.value
                ),
            },
        )
        stop_reason = control_flow_action.get("stop_reason")
        return ResearchOrchestratorChaseSelection(
            selected_entity_ids=[],
            selected_labels=[],
            stop_instead=True,
            stop_reason=(
                stop_reason
                if isinstance(stop_reason, str) and stop_reason
                else "guarded_stop_requested"
            ),
            selection_basis=str(control_flow_action["qualitative_rationale"]),
        )
