"""Deterministic scoring helpers for hybrid graph + embedding workflows."""

from __future__ import annotations


def clamp_score(value: float) -> float:
    """Clamp scores into the canonical [0.0, 1.0] range."""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def compute_jaccard_overlap(
    left_neighbors: set[str],
    right_neighbors: set[str],
) -> float:
    """Compute Jaccard overlap for two neighbor sets."""
    if not left_neighbors and not right_neighbors:
        return 0.0
    union_size = len(left_neighbors | right_neighbors)
    if union_size == 0:
        return 0.0
    overlap_size = len(left_neighbors & right_neighbors)
    return clamp_score(float(overlap_size) / float(union_size))


def compute_similarity_score(
    *,
    vector_score: float,
    graph_overlap_score: float,
) -> float:
    """Blend vector and graph-overlap scores for similar-entity ranking."""
    return clamp_score(
        (0.8 * clamp_score(vector_score)) + (0.2 * clamp_score(graph_overlap_score)),
    )


def compute_relation_prior_score(
    *,
    pair_count: int,
    total_count: int,
    sparse_threshold: int = 3,
) -> float:
    """Compute normalized relation prior score with sparse-data defaulting."""
    if total_count < sparse_threshold or total_count <= 0 or pair_count < 0:
        return 0.5
    return clamp_score(float(pair_count) / float(total_count))


def compute_relation_suggestion_score(
    *,
    vector_score: float,
    graph_overlap_score: float,
    relation_prior_score: float,
) -> float:
    """Blend deterministic score components for relation suggestion ranking."""
    return clamp_score(
        (0.70 * clamp_score(vector_score))
        + (0.20 * clamp_score(graph_overlap_score))
        + (0.10 * clamp_score(relation_prior_score)),
    )


__all__ = [
    "clamp_score",
    "compute_jaccard_overlap",
    "compute_relation_prior_score",
    "compute_relation_suggestion_score",
    "compute_similarity_score",
]
