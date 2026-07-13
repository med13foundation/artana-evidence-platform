"""Frozen-protocol checks for the review-ranking calibration gate."""

from __future__ import annotations

from artana_evidence_api.evidence_selection.ranking.contracts import (
    ReviewRankingCalibrationDecision,
    ReviewRankingCalibrationGateThresholds,
    ReviewRankingCalibrationProtocol,
)
from artana_evidence_api.evidence_selection.ranking.protocol_integrity import (
    verify_calibration_protocol_signature,
)


def calibration_protocol_blocking_reasons(
    *,
    decisions: tuple[ReviewRankingCalibrationDecision, ...],
    protocol: ReviewRankingCalibrationProtocol | None,
    thresholds: ReviewRankingCalibrationGateThresholds,
) -> tuple[str, ...]:
    """Return authentication, partition, and provenance blockers."""

    if protocol is None:
        if (
            thresholds.require_calibrated_probabilities
            or thresholds.require_authenticated_protocol
        ):
            return (
                "Calibration validation is unavailable because the study has no "
                "predeclared training/held-out calibration protocol.",
            )
        return ()
    reasons: list[str] = []
    if thresholds.require_authenticated_protocol:
        try:
            verify_calibration_protocol_signature(protocol)
        except ValueError as exc:
            reasons.append(str(exc))
    if (
        len(protocol.training_research_question_ids)
        < thresholds.min_training_research_questions
    ):
        reasons.append(
            "Calibration requires at least "
            f"{thresholds.min_training_research_questions} training research "
            "questions; got "
            f"{len(protocol.training_research_question_ids)}.",
        )
    if (
        len(protocol.held_out_research_question_ids)
        < thresholds.min_held_out_research_questions
    ):
        reasons.append(
            "Calibration requires at least "
            f"{thresholds.min_held_out_research_questions} held-out research "
            "questions; got "
            f"{len(protocol.held_out_research_question_ids)}.",
        )
    if thresholds.require_independent_expert_labels and not (
        protocol.independent_expert_labels
    ):
        reasons.append("Production calibration requires independent expert labels.")
    held_out_ids = set(protocol.held_out_research_question_ids)
    observed_held_out_ids = {
        decision.research_question_id
        for decision in decisions
        if decision.research_question_id in held_out_ids
    }
    if (
        len(observed_held_out_ids)
        < thresholds.min_observed_held_out_research_questions
    ):
        reasons.append(
            "Calibration evaluation requires observations from at least "
            f"{thresholds.min_observed_held_out_research_questions} held-out "
            f"research questions; got {len(observed_held_out_ids)}.",
        )
    non_held_out_ids = sorted(
        {
            decision.research_question_id
            for decision in decisions
            if decision.research_question_id not in held_out_ids
        },
    )
    if non_held_out_ids:
        reasons.append(
            "Calibration evaluation decisions must belong only to the frozen "
            "held-out research-question partition: "
            f"{', '.join(non_held_out_ids)}.",
        )
    identity = protocol.identity
    mismatched_items = tuple(
        f"{decision.source_kind}:{decision.item_id}"
        for decision in decisions
        if (
            decision.operational_ranking.policy_id != identity.input_policy_id
            or decision.operational_ranking.policy_version
            != identity.input_policy_version
            or decision.operational_ranking.mapping_version
            != identity.input_mapping_version
        )
    )
    if mismatched_items:
        reasons.append(
            "Operational ranking policy identity drifted from the calibration "
            f"protocol for: {', '.join(mismatched_items)}.",
        )
    mismatched_probabilities = tuple(
        f"{decision.source_kind}:{decision.item_id}"
        for decision in decisions
        if decision.calibrated_probability is not None
        and (
            decision.calibrated_probability.identity != protocol.identity
            or decision.calibrated_probability.training_set_sha256
            != protocol.training_set_sha256
            or decision.calibrated_probability.partition_manifest_sha256
            != protocol.partition_manifest_sha256
            or decision.calibrated_probability.held_out_protocol
            != protocol.held_out_protocol
        )
    )
    if mismatched_probabilities:
        reasons.append(
            "Calibrated probability provenance drifted from the frozen protocol "
            f"for: {', '.join(mismatched_probabilities)}.",
        )
    return tuple(reasons)


__all__ = ["calibration_protocol_blocking_reasons"]
