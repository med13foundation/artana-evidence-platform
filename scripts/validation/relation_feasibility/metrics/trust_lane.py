"""Trusted-lane metric aggregation for relation feasibility summaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from scripts.validation.relation_feasibility.trusted_metric_rules import (
    HIGH_VALUE_LEVELS,
    high_value_review_gold_index,
    is_review_only_context_relation,
    is_trusted_graph_evidence_candidate,
    is_trusted_high_value_match,
    low_value_review_gold_index,
)

if TYPE_CHECKING:
    from scripts.validation.relation_feasibility.models import (
        CandidateAssessment,
        GoldRelation,
    )


@dataclass(frozen=True, slots=True)
class TrustLaneMetricCounts:
    """Counts and rates for trusted and review-only evidence lanes."""

    trusted_high_value_match_count: int
    trusted_high_value_recall: float
    trusted_eligible_high_value_gold_relation_count: int
    trusted_eligible_high_value_match_count: int
    trusted_eligible_high_value_recall: float
    trusted_candidate_count: int
    trusted_candidate_supported_count: int
    trusted_candidate_valuable_count: int
    trusted_candidate_generic_relation_count: int
    review_only_gold_trusted_leakage_count: int
    trusted_candidate_precision_against_gold: float
    trusted_candidate_valuable_rate: float
    trusted_candidate_generic_relation_rate: float
    high_value_review_gold_relation_count: int
    high_value_review_candidate_count: int
    high_value_review_gold_match_count: int
    high_value_review_recall: float
    low_value_review_candidate_count: int
    low_value_review_gold_match_count: int
    low_value_review_recall: float


def build_trust_lane_metric_counts(
    *,
    case_gold_relations: tuple[tuple[GoldRelation, ...], ...],
    case_assessments: tuple[tuple[CandidateAssessment, ...], ...],
    case_agent_completed_flags: tuple[bool, ...],
    high_value_gold_relation_count: int,
    low_value_gold_relation_count: int,
) -> TrustLaneMetricCounts:
    """Build trusted auto-promotion and review-lane metrics."""

    trusted_high_value_matches: set[tuple[int, int]] = set()
    trusted_candidate_count = 0
    trusted_candidate_supported_count = 0
    trusted_candidate_valuable_count = 0
    trusted_candidate_generic_relation_count = 0
    review_only_gold_trusted_leaks: set[tuple[int, int]] = set()
    high_value_review_matches: set[tuple[int, int]] = set()
    high_value_review_candidate_count = 0
    low_value_review_matches: set[tuple[int, int]] = set()
    low_value_review_candidate_count = 0
    for case_index, (gold_relations, assessments, agent_completed) in enumerate(
        zip(
            case_gold_relations,
            case_assessments,
            case_agent_completed_flags,
            strict=True,
        ),
    ):
        for assessment in assessments:
            if agent_completed and is_trusted_graph_evidence_candidate(assessment):
                trusted_gold_match = _is_trusted_gold_match(
                    assessment=assessment,
                    gold_relations=gold_relations,
                )
                trusted_candidate_count += 1
                trusted_candidate_supported_count += int(trusted_gold_match)
                trusted_candidate_valuable_count += int(
                    trusted_gold_match and assessment.is_valuable,
                )
                trusted_candidate_generic_relation_count += int(
                    not assessment.is_relation_specific,
                )
                matched_index = assessment.matched_gold_index
                if (
                    matched_index is not None
                    and gold_relations[matched_index].review_status == "review_only"
                ):
                    review_only_gold_trusted_leaks.add((case_index, matched_index))
            if is_trusted_high_value_match(
                assessment=assessment,
                gold_relations=gold_relations,
                agent_completed=agent_completed,
            ):
                trusted_high_value_matches.add(
                    (case_index, assessment.matched_gold_index or 0),
                )
            high_value_review_index = high_value_review_gold_index(
                assessment=assessment,
                gold_relations=gold_relations,
            )
            if agent_completed and high_value_review_index is not None:
                high_value_review_candidate_count += 1
                high_value_review_matches.add((case_index, high_value_review_index))
            low_value_review_index = low_value_review_gold_index(
                assessment=assessment,
                gold_relations=gold_relations,
            )
            if agent_completed and low_value_review_index is not None:
                low_value_review_candidate_count += 1
                low_value_review_matches.add((case_index, low_value_review_index))
    trusted_eligible_high_value_gold_count = (
        _trusted_eligible_high_value_gold_relation_count(case_gold_relations)
    )
    high_value_review_gold_count = _high_value_review_gold_relation_count(
        case_gold_relations,
    )
    return TrustLaneMetricCounts(
        trusted_high_value_match_count=len(trusted_high_value_matches),
        trusted_high_value_recall=_ratio(
            len(trusted_high_value_matches),
            high_value_gold_relation_count,
        ),
        trusted_eligible_high_value_gold_relation_count=(
            trusted_eligible_high_value_gold_count
        ),
        trusted_eligible_high_value_match_count=len(trusted_high_value_matches),
        trusted_eligible_high_value_recall=_ratio(
            len(trusted_high_value_matches),
            trusted_eligible_high_value_gold_count,
        ),
        trusted_candidate_count=trusted_candidate_count,
        trusted_candidate_supported_count=trusted_candidate_supported_count,
        trusted_candidate_valuable_count=trusted_candidate_valuable_count,
        trusted_candidate_generic_relation_count=(
            trusted_candidate_generic_relation_count
        ),
        review_only_gold_trusted_leakage_count=len(
            review_only_gold_trusted_leaks,
        ),
        trusted_candidate_precision_against_gold=_ratio(
            trusted_candidate_supported_count,
            trusted_candidate_count,
        ),
        trusted_candidate_valuable_rate=_ratio(
            trusted_candidate_valuable_count,
            trusted_candidate_count,
        ),
        trusted_candidate_generic_relation_rate=_ratio(
            trusted_candidate_generic_relation_count,
            trusted_candidate_count,
        ),
        high_value_review_gold_relation_count=high_value_review_gold_count,
        high_value_review_candidate_count=high_value_review_candidate_count,
        high_value_review_gold_match_count=len(high_value_review_matches),
        high_value_review_recall=_ratio(
            len(high_value_review_matches),
            high_value_review_gold_count,
        ),
        low_value_review_candidate_count=low_value_review_candidate_count,
        low_value_review_gold_match_count=len(low_value_review_matches),
        low_value_review_recall=_ratio(
            len(low_value_review_matches),
            low_value_gold_relation_count,
        ),
    )


def _is_trusted_gold_match(
    *,
    assessment: CandidateAssessment,
    gold_relations: tuple[GoldRelation, ...],
) -> bool:
    matched_index = assessment.matched_gold_index
    if matched_index is None or not assessment.is_supported_by_gold:
        return False
    matched_gold = gold_relations[matched_index]
    return (
        matched_gold.review_status != "review_only"
        and matched_gold.value_level in HIGH_VALUE_LEVELS
        and not is_review_only_context_relation(matched_gold.relation_type)
    )


def _trusted_eligible_high_value_gold_relation_count(
    case_gold_relations: tuple[tuple[GoldRelation, ...], ...],
) -> int:
    return sum(
        1
        for gold_relations in case_gold_relations
        for gold_relation in gold_relations
        if gold_relation.value_level in HIGH_VALUE_LEVELS
        and gold_relation.review_status != "review_only"
        and not is_review_only_context_relation(gold_relation.relation_type)
    )


def _high_value_review_gold_relation_count(
    case_gold_relations: tuple[tuple[GoldRelation, ...], ...],
) -> int:
    return sum(
        1
        for gold_relations in case_gold_relations
        for gold_relation in gold_relations
        if gold_relation.value_level in HIGH_VALUE_LEVELS
        and gold_relation.review_status == "review_only"
    )


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


__all__ = ["TrustLaneMetricCounts", "build_trust_lane_metric_counts"]
