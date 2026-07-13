"""Unit tests for deterministic harness ranking helpers."""

from __future__ import annotations

from artana_evidence_api.ranking import (
    rank_chat_graph_write_candidate,
    rank_mechanism_candidate,
    rank_reviewed_candidate_claim,
)


def test_rank_chat_graph_write_candidate_rewards_stronger_suggestions() -> None:
    stronger = rank_chat_graph_write_candidate(
        evidence_relevance=0.92,
        suggestion_final_score=0.95,
        vector_score=0.9,
        graph_overlap_score=0.88,
        relation_prior_score=0.8,
    )
    weaker = rank_chat_graph_write_candidate(
        evidence_relevance=0.81,
        suggestion_final_score=0.78,
        vector_score=0.74,
        graph_overlap_score=0.71,
        relation_prior_score=0.68,
    )

    assert stronger.score > weaker.score
    assert stronger.metadata["evidence_relevance"] == 0.92
    assert stronger.metadata["suggestion_final_score"] == 0.95
    assert stronger.metadata["graph_overlap_score"] == 0.88


def test_rank_mechanism_candidate_rewards_support_and_short_paths() -> None:
    stronger = rank_mechanism_candidate(
        confidence=0.9,
        path_count=4,
        supporting_claim_count=6,
        evidence_reference_count=5,
        average_path_length=1.5,
    )
    weaker = rank_mechanism_candidate(
        confidence=0.55,
        path_count=1,
        supporting_claim_count=1,
        evidence_reference_count=1,
        average_path_length=4.0,
    )

    assert stronger.score > weaker.score
    assert stronger.metadata["path_count"] == 4
    assert stronger.metadata["supporting_claim_count"] == 6
    assert stronger.metadata["average_path_length"] == 1.5


def test_rank_reviewed_candidate_claim_rewards_grounded_entailed_specific_evidence() -> None:
    strong = rank_reviewed_candidate_claim(
        factual_confidence=0.92,
        goal_relevance=0.96,
        priority=0.96,
        supporting_document_count=1,
        evidence_reference_count=1,
        grounded_sentence=True,
        both_arguments_present=True,
        entailment_supported=True,
        relation_specific=True,
    )
    weak = rank_reviewed_candidate_claim(
        factual_confidence=0.92,
        goal_relevance=0.96,
        priority=0.96,
        supporting_document_count=1,
        evidence_reference_count=1,
        grounded_sentence=False,
        both_arguments_present=False,
        entailment_supported=False,
        relation_specific=False,
    )

    assert strong.score > weak.score
    assert strong.metadata["evidence_quality_component"] == 1.0
    assert weak.metadata["evidence_quality_component"] == 0.0
