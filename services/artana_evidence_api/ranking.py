"""Deterministic ranking helpers for graph-harness candidate proposals."""

from __future__ import annotations

from dataclasses import dataclass

from artana_evidence_api.types.common import JSONObject  # noqa: TC001


@dataclass(frozen=True, slots=True)
class ProposalRanking:
    """One deterministic ranking result for a candidate proposal."""

    score: float
    metadata: JSONObject


def rank_candidate_claim(
    *,
    confidence: float,
    supporting_document_count: int,
    evidence_reference_count: int,
) -> ProposalRanking:
    """Compute a bounded ranking score for one candidate claim."""
    confidence_component = max(0.0, min(confidence, 1.0))
    document_component = min(max(supporting_document_count, 0), 5) / 5
    evidence_component = min(max(evidence_reference_count, 0), 5) / 5
    score = round(
        min(
            1.0,
            (confidence_component * 0.7)
            + (document_component * 0.2)
            + (evidence_component * 0.1),
        ),
        6,
    )
    return ProposalRanking(
        score=score,
        metadata={
            "confidence_component": confidence_component,
            "supporting_document_count": supporting_document_count,
            "supporting_document_component": document_component,
            "evidence_reference_count": evidence_reference_count,
            "evidence_reference_component": evidence_component,
        },
    )


def rank_reviewed_candidate_claim(
    *,
    factual_confidence: float,
    goal_relevance: float,
    priority: float,
    supporting_document_count: int,
    evidence_reference_count: int,
) -> ProposalRanking:
    """Compute a ranking score for one reviewed document-extraction claim."""
    factual_component = max(0.0, min(factual_confidence, 1.0))
    relevance_component = max(0.0, min(goal_relevance, 1.0))
    priority_component = max(0.0, min(priority, 1.0))
    document_component = min(max(supporting_document_count, 0), 5) / 5
    evidence_component = min(max(evidence_reference_count, 0), 5) / 5
    score = round(
        min(
            1.0,
            (relevance_component * 0.4)
            + (priority_component * 0.3)
            + (factual_component * 0.2)
            + (document_component * 0.05)
            + (evidence_component * 0.05),
        ),
        6,
    )
    return ProposalRanking(
        score=score,
        metadata={
            "factual_confidence_component": factual_component,
            "goal_relevance_component": relevance_component,
            "priority_component": priority_component,
            "supporting_document_count": supporting_document_count,
            "supporting_document_component": document_component,
            "evidence_reference_count": evidence_reference_count,
            "evidence_reference_component": evidence_component,
        },
    )


def rank_chat_graph_write_candidate(
    *,
    evidence_relevance: float,
    suggestion_final_score: float,
    vector_score: float,
    graph_overlap_score: float,
    relation_prior_score: float,
) -> ProposalRanking:
    """Compute a bounded ranking score for one chat-derived graph-write candidate."""
    evidence_component = max(0.0, min(evidence_relevance, 1.0))
    suggestion_component = max(0.0, min(suggestion_final_score, 1.0))
    vector_component = max(0.0, min(vector_score, 1.0))
    overlap_component = max(0.0, min(graph_overlap_score, 1.0))
    prior_component = max(0.0, min(relation_prior_score, 1.0))
    score = round(
        min(
            1.0,
            (suggestion_component * 0.45)
            + (evidence_component * 0.25)
            + (overlap_component * 0.15)
            + (vector_component * 0.1)
            + (prior_component * 0.05),
        ),
        6,
    )
    return ProposalRanking(
        score=score,
        metadata={
            "evidence_relevance": evidence_component,
            "suggestion_final_score": suggestion_component,
            "vector_score": vector_component,
            "graph_overlap_score": overlap_component,
            "relation_prior_score": prior_component,
        },
    )


def rank_mechanism_candidate(
    *,
    confidence: float,
    path_count: int,
    supporting_claim_count: int,
    evidence_reference_count: int,
    average_path_length: float,
) -> ProposalRanking:
    """Compute a bounded ranking score for one mechanism candidate."""
    confidence_component = max(0.0, min(confidence, 1.0))
    path_count_component = min(max(path_count, 0), 6) / 6
    support_component = min(max(supporting_claim_count, 0), 8) / 8
    evidence_component = min(max(evidence_reference_count, 0), 8) / 8
    path_efficiency_component = max(
        0.0,
        min(1.0, 1.0 - ((max(average_path_length, 1.0) - 1.0) / 4.0)),
    )
    score = round(
        min(
            1.0,
            (confidence_component * 0.45)
            + (path_count_component * 0.2)
            + (support_component * 0.15)
            + (evidence_component * 0.1)
            + (path_efficiency_component * 0.1),
        ),
        6,
    )
    return ProposalRanking(
        score=score,
        metadata={
            "confidence_component": confidence_component,
            "path_count": path_count,
            "path_count_component": path_count_component,
            "supporting_claim_count": supporting_claim_count,
            "supporting_claim_component": support_component,
            "evidence_reference_count": evidence_reference_count,
            "evidence_reference_component": evidence_component,
            "average_path_length": round(average_path_length, 6),
            "path_efficiency_component": path_efficiency_component,
        },
    )


__all__ = [
    "ProposalRanking",
    "rank_chat_graph_write_candidate",
    "rank_candidate_claim",
    "rank_mechanism_candidate",
    "rank_reviewed_candidate_claim",
]
