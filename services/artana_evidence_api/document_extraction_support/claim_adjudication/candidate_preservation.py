"""Preserve deterministic extraction rejections for semantic review."""

from __future__ import annotations

from dataclasses import replace

from artana_evidence_api.document_extraction_contracts import (
    ExtractedRelationCandidate,
)
from artana_evidence_api.document_extraction_support.relation_candidate_quality_filter import (
    RelationCandidateQualityFilterResult,
)
from artana_evidence_api.document_extraction_support.relation_specificity_pruning import (
    RelationSpecificityPruningResult,
)


def preserve_pruned_candidates_for_adjudication(
    *,
    candidates: list[ExtractedRelationCandidate],
    pruning_result: RelationSpecificityPruningResult,
) -> tuple[ExtractedRelationCandidate, ...]:
    """Keep deterministic pruning decisions as review-only semantic inputs."""

    reason_by_index = {
        item.candidate_index: "generic_relation_shadowed_by_specific_sibling"
        for item in pruning_result.pruned_candidates
    }
    reason_by_index.update(
        {
            item.candidate_index: "weak_generic_relation_candidate"
            for item in pruning_result.weak_generic_candidates
        },
    )
    return tuple(
        as_review_only_candidate(candidate, reason_by_index[index])
        if index in reason_by_index
        else candidate
        for index, candidate in enumerate(candidates)
    )


def preserve_quality_filtered_candidates_for_adjudication(
    *,
    candidates: tuple[ExtractedRelationCandidate, ...],
    quality_filter_result: RelationCandidateQualityFilterResult,
) -> RelationCandidateQualityFilterResult:
    """Convert quality-filter removals into review-only semantic inputs."""

    filtered_by_index = {
        item.candidate_index: item for item in quality_filter_result.filtered_candidates
    }
    kept = iter(
        quality_filter_result.unmerged_candidates or quality_filter_result.candidates
    )
    preserved: list[ExtractedRelationCandidate] = []
    for index, _candidate in enumerate(candidates):
        filtered = filtered_by_index.get(index)
        if filtered is not None:
            preserved.append(
                as_review_only_candidate(
                    filtered.candidate,
                    f"quality_filter_{filtered.reason}",
                ),
            )
            continue
        preserved.append(next(kept))
    return RelationCandidateQualityFilterResult(
        candidates=tuple(preserved),
        filtered_candidates=quality_filter_result.filtered_candidates,
        unmerged_candidates=tuple(preserved),
    )


def as_review_only_candidate(
    candidate: ExtractedRelationCandidate,
    reason: str,
) -> ExtractedRelationCandidate:
    """Preserve one source-bound claim without making it promotion eligible."""

    return replace(
        candidate,
        review_status="review_only",
        review_reason_codes=tuple(
            dict.fromkeys((*candidate.review_reason_codes, reason)),
        ),
    )


__all__ = [
    "as_review_only_candidate",
    "preserve_pruned_candidates_for_adjudication",
    "preserve_quality_filtered_candidates_for_adjudication",
]
