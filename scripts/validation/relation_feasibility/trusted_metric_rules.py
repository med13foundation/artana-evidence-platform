"""Trusted and review-only metric predicates for relation feasibility scoring."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.validation.relation_feasibility.models import (
        CandidateAssessment,
        GoldRelation,
    )

HIGH_VALUE_LEVELS = frozenset({"high", "medium"})
LOW_VALUE_LEVELS = frozenset({"low", "reject"})
REVIEW_ONLY_CONTEXT_RELATION_TYPES = frozenset({"DOWNSTREAM_OF", "UPSTREAM_OF"})


def is_trusted_high_value_match(
    *,
    assessment: CandidateAssessment,
    gold_relations: tuple[GoldRelation, ...],
    agent_completed: bool,
) -> bool:
    """Return whether a candidate can count toward trusted high-value recall."""

    matched_index = assessment.matched_gold_index
    if matched_index is None:
        return False
    matched_gold = gold_relations[matched_index]
    return (
        agent_completed
        and not is_review_only_context_relation(assessment.candidate.relation_type)
        and matched_gold.review_status != "review_only"
        and matched_gold.value_level in HIGH_VALUE_LEVELS
        and assessment.is_valuable
        and assessment.is_trusted_evidence_eligible
        and has_verified_gold_curie_endpoints(
            assessment=assessment,
            matched_gold=matched_gold,
        )
    )


def is_review_only_context_relation(relation_type: str) -> bool:
    """Return whether a relation type is pathway context rather than trusted evidence."""

    return relation_type.strip().upper() in REVIEW_ONLY_CONTEXT_RELATION_TYPES


def has_verified_gold_curie_endpoints(
    *,
    assessment: CandidateAssessment,
    matched_gold: GoldRelation,
) -> bool:
    """Return whether both candidate endpoints are verified gold CURIE matches."""

    if matched_gold.subject_curie is None or matched_gold.object_curie is None:
        return False
    return (
        assessment.has_verified_subject_curie
        and assessment.subject_curie_matches_gold
        and assessment.has_verified_object_curie
        and assessment.object_curie_matches_gold
    )


def low_value_review_gold_index(
    *,
    assessment: CandidateAssessment,
    gold_relations: tuple[GoldRelation, ...],
) -> int | None:
    """Return the low-value gold index captured by a governed review proposal."""

    if assessment.candidate.review_status == "review_only":
        matched_index = assessment.matched_gold_index
        if matched_index is None:
            return None
        matched_gold = gold_relations[matched_index]
        if matched_gold.value_level not in LOW_VALUE_LEVELS:
            return None
        return matched_index
    matched_index = assessment.proposal_matched_gold_index
    if matched_index is None or not assessment.is_governed_relation_proposal:
        return None
    matched_gold = gold_relations[matched_index]
    if matched_gold.value_level not in LOW_VALUE_LEVELS:
        return None
    return matched_index


def high_value_review_gold_index(
    *,
    assessment: CandidateAssessment,
    gold_relations: tuple[GoldRelation, ...],
) -> int | None:
    """Return the high-value review-only gold index captured by an agent candidate."""

    if assessment.candidate.review_status == "review_only":
        matched_index = assessment.matched_gold_index
        if matched_index is None:
            return None
        matched_gold = gold_relations[matched_index]
        if (
            matched_gold.value_level not in HIGH_VALUE_LEVELS
            or matched_gold.review_status != "review_only"
        ):
            return None
        return matched_index
    matched_index = assessment.proposal_matched_gold_index
    if matched_index is None or not assessment.is_governed_relation_proposal:
        return None
    matched_gold = gold_relations[matched_index]
    if (
        matched_gold.value_level not in HIGH_VALUE_LEVELS
        or matched_gold.review_status != "review_only"
    ):
        return None
    return matched_index
