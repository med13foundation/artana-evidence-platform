# mypy: disable-error-code="attr-defined,has-type,no-any-return"
"""Guarded-action verification mixin for the full-AI orchestrator."""

from __future__ import annotations

from artana_evidence_api.full_ai_orchestrator.runtime_constants import (
    _GUARDED_STRATEGY_CHASE_SELECTION,
    _GUARDED_STRATEGY_STRUCTURED_SOURCE,
    _GUARDED_STRATEGY_TERMINAL_CONTROL,
)
from artana_evidence_api.full_ai_orchestrator.workspace_support import (
    _guarded_structured_verification_payload,
    _normalized_source_key_list,
    _workspace_object,
)
from artana_evidence_api.full_ai_orchestrator_contracts import (
    ResearchOrchestratorActionType,
)
from artana_evidence_api.types.common import JSONObject

__all__ = ["_FullAIOrchestratorGuardedVerificationMixin"]


class _FullAIOrchestratorGuardedVerificationMixin:
    def verify_guarded_structured_enrichment(
        self,
        *,
        workspace_snapshot: JSONObject,
    ) -> bool:
        source_results = _workspace_object(workspace_snapshot, "source_results")
        for action in reversed(self.guarded_execution_log):
            if (
                action.get("applied_action_type")
                != ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT.value
            ):
                continue
            guarded_strategy = action.get("guarded_strategy")
            if guarded_strategy not in {
                "single_structured_source",
                _GUARDED_STRATEGY_STRUCTURED_SOURCE,
            }:
                continue
            if action.get("verification_status") != "pending":
                continue
            (
                verification_status,
                verification_reason,
                verification_summary,
            ) = _guarded_structured_verification_payload(
                source_results=source_results,
                action=action,
            )
            guarded_strategy_value = (
                guarded_strategy if isinstance(guarded_strategy, str) else None
            )
            return self._update_guarded_action_verification(
                action_type=ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
                guarded_strategy=guarded_strategy_value,
                verification_status=verification_status,
                verification_reason=verification_reason,
                verification_summary=verification_summary,
                verified_at_phase="structured_enrichment",
            )
        return False

    def verify_guarded_chase_selection(
        self,
        *,
        workspace_snapshot: JSONObject,
    ) -> bool:
        for action in reversed(self.guarded_execution_log):
            if action.get("guarded_strategy") != _GUARDED_STRATEGY_CHASE_SELECTION:
                continue
            if action.get("verification_status") != "pending":
                continue
            round_number = action.get("round_number")
            if not isinstance(round_number, int):
                return False
            chase_summary = workspace_snapshot.get(f"chase_round_{round_number}")
            if not isinstance(chase_summary, dict):
                return False
            selected_entity_ids = _normalized_source_key_list(
                chase_summary.get("selected_entity_ids"),
            )
            selected_labels = _normalized_source_key_list(
                chase_summary.get("selected_labels"),
            )
            verification_status = "verified"
            verification_reason = "guarded_chase_selection_applied"
            if chase_summary.get("selection_mode") != "guarded":
                verification_status = "verification_failed"
                verification_reason = "guarded_chase_selection_marker_missing"
            elif selected_entity_ids != action.get(
                "selected_entity_ids"
            ) or selected_labels != action.get("selected_labels"):
                verification_status = "verification_failed"
                verification_reason = "guarded_chase_selection_mismatch"
            return self._update_guarded_action_verification(
                action_type=ResearchOrchestratorActionType.RUN_CHASE_ROUND,
                guarded_strategy=_GUARDED_STRATEGY_CHASE_SELECTION,
                verification_status=verification_status,
                verification_reason=verification_reason,
                verification_summary={
                    "chase_round": round_number,
                    "selected_entity_ids": selected_entity_ids,
                    "selected_labels": selected_labels,
                    "selection_mode": chase_summary.get("selection_mode"),
                },
                verified_at_phase="chase_round",
            )
        return False

    def verify_guarded_brief_generation(
        self,
        *,
        workspace_snapshot: JSONObject,
    ) -> bool:
        research_brief = workspace_snapshot.get("research_brief")
        chase_round_2 = workspace_snapshot.get("chase_round_2")
        guarded_stop_after_chase_round = workspace_snapshot.get(
            "guarded_stop_after_chase_round",
        )
        brief_present = isinstance(research_brief, dict)
        chase_round_2_present = isinstance(chase_round_2, dict)
        verification_status = "verified"
        verification_reason = "brief_generated_without_second_chase_round"
        if not brief_present:
            verification_status = "verification_failed"
            verification_reason = "brief_missing"
        elif chase_round_2_present:
            verification_status = "verification_failed"
            verification_reason = "unexpected_second_chase_round"
        elif guarded_stop_after_chase_round != 1:
            verification_status = "verification_failed"
            verification_reason = "guarded_stop_marker_missing"
        return self._update_guarded_action_verification(
            action_type=ResearchOrchestratorActionType.GENERATE_BRIEF,
            stop_reason="guarded_generate_brief",
            verification_status=verification_status,
            verification_reason=verification_reason,
            verification_summary={
                "brief_present": brief_present,
                "guarded_stop_after_chase_round": guarded_stop_after_chase_round,
                "chase_round_2_present": chase_round_2_present,
            },
            verified_at_phase="brief_generation",
        )

    def verify_guarded_terminal_control_flow(
        self,
        *,
        workspace_snapshot: JSONObject,
    ) -> bool:
        terminal_control_action = workspace_snapshot.get(
            "guarded_terminal_control_action",
        )
        terminal_control_after_round = workspace_snapshot.get(
            "guarded_terminal_control_after_chase_round",
        )
        human_review_required = workspace_snapshot.get(
            "guarded_human_review_required",
        )
        if not isinstance(terminal_control_action, dict):
            return False
        action_type = terminal_control_action.get("action_type")
        stop_reason = terminal_control_action.get("stop_reason")
        if action_type not in {
            ResearchOrchestratorActionType.STOP.value,
            ResearchOrchestratorActionType.ESCALATE_TO_HUMAN.value,
        }:
            return False
        if not isinstance(stop_reason, str) or stop_reason == "":
            return False

        checkpoint_key = terminal_control_action.get("checkpoint_key")
        expected_after_round_by_checkpoint = {
            "after_bootstrap": 0,
            "after_chase_round_1": 1,
        }
        expected_after_round = (
            expected_after_round_by_checkpoint.get(checkpoint_key)
            if isinstance(checkpoint_key, str)
            else None
        )

        verification_status = "verified"
        verification_reason = "terminal_control_action_verified"
        if expected_after_round is None:
            verification_status = "verification_failed"
            verification_reason = "terminal_control_checkpoint_invalid"
        elif terminal_control_after_round != expected_after_round:
            verification_status = "verification_failed"
            verification_reason = "terminal_control_round_marker_mismatch"

        if (
            verification_status == "verified"
            and action_type == ResearchOrchestratorActionType.ESCALATE_TO_HUMAN.value
        ):
            verification_reason = "human_review_requested"
            if human_review_required is not True:
                verification_status = "verification_failed"
                verification_reason = "human_review_marker_missing"
        elif verification_status == "verified" and human_review_required is True:
            verification_status = "verification_failed"
            verification_reason = "unexpected_human_review_marker"

        return self._update_guarded_action_verification(
            action_type=(
                ResearchOrchestratorActionType.ESCALATE_TO_HUMAN
                if action_type == ResearchOrchestratorActionType.ESCALATE_TO_HUMAN.value
                else ResearchOrchestratorActionType.STOP
            ),
            stop_reason=stop_reason,
            verification_status=verification_status,
            verification_reason=verification_reason,
            verification_summary={
                "guarded_terminal_control_action": terminal_control_action,
                "guarded_terminal_control_after_chase_round": terminal_control_after_round,
                "expected_after_chase_round": expected_after_round,
                "guarded_human_review_required": human_review_required,
            },
            verified_at_phase="control_flow",
            guarded_strategy=_GUARDED_STRATEGY_TERMINAL_CONTROL,
        )
