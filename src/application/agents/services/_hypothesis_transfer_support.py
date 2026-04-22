"""Helper functions for transfer-backed hypothesis generation."""

from __future__ import annotations

from dataclasses import dataclass

_ASSOCIATION_RELATION_FAMILY = frozenset({"ASSOCIATED_WITH", "CAUSES"})
_TOKEN_MIN_LENGTH = 3
_MAX_EXPLANATION_ENTITY_LABELS = 3
_TRANSFER_SCORE_THRESHOLD = 0.5


@dataclass(frozen=True)
class TransferScoreBreakdown:
    """Scoring components for one transfer-backed hypothesis candidate."""

    score: float
    direct_support_score: float
    transfer_support_score: float
    phenotype_overlap_score: float
    pathway_overlap_score: float
    contradiction_penalty: float


def normalize_text_tokens(value: str | None) -> frozenset[str]:
    """Return uppercase alphanumeric tokens for simple overlap matching."""
    if value is None:
        return frozenset()
    normalized = "".join(
        character if character.isalnum() else " " for character in value.upper()
    )
    return frozenset(
        token for token in normalized.split() if len(token) >= _TOKEN_MIN_LENGTH
    )


def label_overlap_score(
    left_label: str | None,
    right_label: str | None,
) -> float:
    """Return a simple Jaccard-style overlap score between two labels."""
    left_tokens = normalize_text_tokens(left_label)
    right_tokens = normalize_text_tokens(right_label)
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens.intersection(right_tokens))
    if overlap == 0:
        return 0.0
    union = len(left_tokens.union(right_tokens))
    if union == 0:
        return 0.0
    return overlap / float(union)


def relation_types_are_transfer_compatible(
    path_relation_type: str,
    candidate_relation_type: str,
) -> bool:
    """Return whether a nearby claim is structurally compatible with a path."""
    normalized_path = path_relation_type.strip().upper()
    normalized_candidate = candidate_relation_type.strip().upper()
    if normalized_path == normalized_candidate:
        return True
    return (
        normalized_path in _ASSOCIATION_RELATION_FAMILY
        and normalized_candidate in _ASSOCIATION_RELATION_FAMILY
    )


def score_transfer_candidate(
    *,
    direct_path_confidence: float,
    average_transfer_confidence: float,
    phenotype_overlap: float,
    transferred_entity_count: int,
    contradiction_count: int,
) -> TransferScoreBreakdown:
    """Compute a bounded score for one transfer-backed hypothesis candidate."""
    direct_support_score = max(0.0, min(1.0, direct_path_confidence)) * 0.45
    transfer_support_score = max(0.0, min(1.0, average_transfer_confidence)) * 0.25
    phenotype_overlap_score = max(0.0, min(1.0, phenotype_overlap)) * 0.20
    pathway_overlap_score = (
        max(0.0, min(1.0, float(transferred_entity_count) / 3.0)) * 0.15
    )
    contradiction_penalty = min(0.45, float(max(0, contradiction_count)) * 0.15)
    total = (
        direct_support_score
        + transfer_support_score
        + phenotype_overlap_score
        + pathway_overlap_score
        - contradiction_penalty
    )
    return TransferScoreBreakdown(
        score=max(0.0, min(1.0, total)),
        direct_support_score=round(direct_support_score, 6),
        transfer_support_score=round(transfer_support_score, 6),
        phenotype_overlap_score=round(phenotype_overlap_score, 6),
        pathway_overlap_score=round(pathway_overlap_score, 6),
        contradiction_penalty=round(contradiction_penalty, 6),
    )


def build_transfer_explanation(  # noqa: PLR0913
    *,
    source_label: str,
    target_label: str,
    transferred_entity_labels: tuple[str, ...],
    direct_supporting_claim_count: int,
    transferred_supporting_claim_count: int,
    contradiction_count: int,
) -> str:
    """Generate a short human-readable explanation for one candidate."""
    related_entities = ", ".join(
        transferred_entity_labels[:_MAX_EXPLANATION_ENTITY_LABELS],
    )
    if len(transferred_entity_labels) > _MAX_EXPLANATION_ENTITY_LABELS:
        related_entities = f"{related_entities}, and others"
    nearby_fragment = (
        f" nearby biology from {related_entities}"
        if related_entities
        else " nearby graph evidence"
    )
    contradiction_fragment = ""
    if contradiction_count > 0:
        contradiction_fragment = (
            f" Confidence is reduced by {contradiction_count} contradictory or"
            " uncertain claim(s)."
        )
    return (
        f"{source_label} may connect to {target_label} based on "
        f"{direct_supporting_claim_count} direct reasoning-path claim(s) and "
        f"{transferred_supporting_claim_count} transferred support claim(s) from"
        f"{nearby_fragment}.{contradiction_fragment}"
    )


__all__ = [
    "TransferScoreBreakdown",
    "_TRANSFER_SCORE_THRESHOLD",
    "build_transfer_explanation",
    "label_overlap_score",
    "relation_types_are_transfer_compatible",
    "score_transfer_candidate",
]
