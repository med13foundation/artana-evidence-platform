"""Endpoint metric splits for trusted and review-only relation evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from scripts.validation.relation_feasibility.trusted_metric_rules import (
    HIGH_VALUE_LEVELS,
    LOW_VALUE_LEVELS,
)

if TYPE_CHECKING:
    from scripts.validation.relation_feasibility.models import (
        CandidateAssessment,
        GoldRelation,
    )


@dataclass(frozen=True, slots=True)
class EndpointMetricSummary:
    """Endpoint recovery split by trusted-eligible and review-only lanes."""

    trusted_eligible_gold_curie_endpoint_count: int
    trusted_eligible_curie_linked_gold_endpoint_count: int
    trusted_eligible_curie_linked_gold_endpoint_rate: float
    low_value_review_gold_curie_endpoint_count: int
    low_value_review_curie_linked_gold_endpoint_count: int
    low_value_review_curie_endpoint_capture_rate: float
    weak_claim_trusted_leakage_count: int


def build_endpoint_metric_summary(
    *,
    case_assessments: tuple[tuple[CandidateAssessment, ...], ...],
    case_gold_relations: tuple[tuple[GoldRelation, ...], ...],
    case_agent_completed_flags: tuple[bool, ...],
) -> EndpointMetricSummary:
    """Build endpoint metrics that separate trusted and review-only evidence."""

    trusted_gold_endpoints = _gold_endpoint_keys(
        case_gold_relations=case_gold_relations,
        value_levels=HIGH_VALUE_LEVELS,
        review_status="candidate",
    )
    trusted_linked_endpoints = _linked_endpoint_keys(
        case_assessments=case_assessments,
        case_gold_relations=case_gold_relations,
        case_agent_completed_flags=case_agent_completed_flags,
        value_levels=HIGH_VALUE_LEVELS,
        lane="trusted",
    )
    low_value_gold_endpoints = _gold_endpoint_keys(
        case_gold_relations=case_gold_relations,
        value_levels=LOW_VALUE_LEVELS,
        review_status=None,
    )
    low_value_review_linked_endpoints = _linked_endpoint_keys(
        case_assessments=case_assessments,
        case_gold_relations=case_gold_relations,
        case_agent_completed_flags=case_agent_completed_flags,
        value_levels=LOW_VALUE_LEVELS,
        lane="review",
    )
    return EndpointMetricSummary(
        trusted_eligible_gold_curie_endpoint_count=len(trusted_gold_endpoints),
        trusted_eligible_curie_linked_gold_endpoint_count=len(
            trusted_linked_endpoints,
        ),
        trusted_eligible_curie_linked_gold_endpoint_rate=_ratio(
            len(trusted_linked_endpoints),
            len(trusted_gold_endpoints),
        ),
        low_value_review_gold_curie_endpoint_count=len(low_value_gold_endpoints),
        low_value_review_curie_linked_gold_endpoint_count=len(
            low_value_review_linked_endpoints,
        ),
        low_value_review_curie_endpoint_capture_rate=_ratio(
            len(low_value_review_linked_endpoints),
            len(low_value_gold_endpoints),
        ),
        weak_claim_trusted_leakage_count=_weak_claim_trusted_leakage_count(
            case_assessments=case_assessments,
            case_gold_relations=case_gold_relations,
        ),
    )


def _gold_endpoint_keys(
    *,
    case_gold_relations: tuple[tuple[GoldRelation, ...], ...],
    value_levels: frozenset[str],
    review_status: str | None,
) -> set[tuple[int, int, str]]:
    endpoint_keys: set[tuple[int, int, str]] = set()
    for case_index, gold_relations in enumerate(case_gold_relations):
        for gold_index, gold_relation in enumerate(gold_relations):
            if gold_relation.value_level not in value_levels:
                continue
            if (
                review_status is not None
                and gold_relation.review_status != review_status
            ):
                continue
            if gold_relation.subject_curie is not None:
                endpoint_keys.add((case_index, gold_index, "subject"))
            if gold_relation.object_curie is not None:
                endpoint_keys.add((case_index, gold_index, "object"))
    return endpoint_keys


def _linked_endpoint_keys(
    *,
    case_assessments: tuple[tuple[CandidateAssessment, ...], ...],
    case_gold_relations: tuple[tuple[GoldRelation, ...], ...],
    case_agent_completed_flags: tuple[bool, ...],
    value_levels: frozenset[str],
    lane: Literal["trusted", "review"],
) -> set[tuple[int, int, str]]:
    endpoint_keys: set[tuple[int, int, str]] = set()
    for case_index, (assessments, agent_completed) in enumerate(
        zip(case_assessments, case_agent_completed_flags, strict=True),
    ):
        if not agent_completed:
            continue
        for assessment in assessments:
            gold_index = _review_or_match_gold_index(
                assessment=assessment,
                require_review_only=lane == "review",
            )
            if gold_index is None:
                continue
            gold_relation = case_gold_relations[case_index][gold_index]
            if gold_relation.value_level not in value_levels:
                continue
            if lane == "trusted" and gold_relation.review_status == "review_only":
                continue
            if lane == "trusted" and not assessment.is_trusted_evidence_eligible:
                continue
            if assessment.subject_curie_matches_gold:
                endpoint_keys.add((case_index, gold_index, "subject"))
            if assessment.object_curie_matches_gold:
                endpoint_keys.add((case_index, gold_index, "object"))
    return endpoint_keys


def _review_or_match_gold_index(
    *,
    assessment: CandidateAssessment,
    require_review_only: bool,
) -> int | None:
    if require_review_only:
        if assessment.candidate.review_status == "review_only":
            return assessment.matched_gold_index
        if assessment.is_governed_relation_proposal:
            return assessment.proposal_matched_gold_index
        return None
    return assessment.matched_gold_index


def _weak_claim_trusted_leakage_count(
    *,
    case_assessments: tuple[tuple[CandidateAssessment, ...], ...],
    case_gold_relations: tuple[tuple[GoldRelation, ...], ...],
) -> int:
    leaked_gold: set[tuple[int, int]] = set()
    for case_index, assessments in enumerate(case_assessments):
        for assessment in assessments:
            matched_index = assessment.matched_gold_index
            if matched_index is None:
                continue
            gold_relation = case_gold_relations[case_index][matched_index]
            if gold_relation.value_level not in LOW_VALUE_LEVELS:
                continue
            if assessment.is_trusted_evidence_eligible:
                leaked_gold.add((case_index, matched_index))
    return len(leaked_gold)


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


__all__ = ["EndpointMetricSummary", "build_endpoint_metric_summary"]
