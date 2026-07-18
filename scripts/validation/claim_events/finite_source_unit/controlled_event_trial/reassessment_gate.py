"""Deterministic gate for offline reassessment of the adaptive replay."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReassessmentGateInputs:
    """Evidence that no new model output was used to change the decision."""

    artifact_verified: bool
    adaptive_replay_declared: bool
    offline_reassessment_declared: bool
    model_call_count: int
    source_identity_verified: bool
    prior_only_failed_requirement_was_matcher: bool
    prior_provider_receipts_verified: bool
    trusted_event_count: int
    expert_core_event_match_count: int


def reassessment_gate_requirements(
    inputs: ReassessmentGateInputs,
) -> dict[str, bool]:
    """Allow progress only when the immutable result passes the corrected matcher."""

    return {
        "artifact_verified": inputs.artifact_verified,
        "adaptive_replay_declared": inputs.adaptive_replay_declared,
        "offline_reassessment_declared": inputs.offline_reassessment_declared,
        "no_new_model_calls": inputs.model_call_count == 0,
        "source_identity_verified": inputs.source_identity_verified,
        "prior_only_failed_requirement_was_matcher": (
            inputs.prior_only_failed_requirement_was_matcher
        ),
        "prior_provider_receipts_verified": inputs.prior_provider_receipts_verified,
        "one_trusted_event": inputs.trusted_event_count == 1,
        "sealed_expert_core_recovered": inputs.expert_core_event_match_count == 1,
    }


__all__ = ["ReassessmentGateInputs", "reassessment_gate_requirements"]
