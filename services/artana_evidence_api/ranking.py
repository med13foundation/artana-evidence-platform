"""Deterministic ranking helpers for graph-harness candidate proposals."""

from __future__ import annotations

from dataclasses import dataclass

from artana_evidence_api.types.common import JSONObject  # noqa: TC001


@dataclass(frozen=True, slots=True)
class ProposalRanking:
    """One deterministic ranking result for a candidate proposal."""

    score: float
    metadata: JSONObject


@dataclass(frozen=True, slots=True)
class ReviewRankingCalibrationObservation:
    """One decided review-ranking observation for calibration accounting."""

    ranking_score: float
    outcome_positive: bool


@dataclass(frozen=True, slots=True)
class ReviewRankingCalibrationSummary:
    """Expected calibration error summary for human-review ranking scores."""

    sample_count: int
    mean_score: float
    observed_positive_rate: float
    expected_calibration_error: float

    def to_json(self) -> JSONObject:
        """Return a stable JSON payload for artifacts and snapshots."""
        return {
            "sample_count": self.sample_count,
            "mean_score": self.mean_score,
            "observed_positive_rate": self.observed_positive_rate,
            "expected_calibration_error": self.expected_calibration_error,
        }


def build_review_ranking_calibration_summary(
    observations: tuple[ReviewRankingCalibrationObservation, ...],
    *,
    bin_count: int = 10,
) -> ReviewRankingCalibrationSummary:
    """Measure review-ranking calibration against human decision outcomes."""
    scored_observations = tuple(
        (
            _bounded_score(observation.ranking_score),
            1.0 if observation.outcome_positive else 0.0,
        )
        for observation in observations
    )
    sample_count = len(scored_observations)
    if sample_count == 0:
        return ReviewRankingCalibrationSummary(
            sample_count=0,
            mean_score=0.0,
            observed_positive_rate=0.0,
            expected_calibration_error=0.0,
        )
    return ReviewRankingCalibrationSummary(
        sample_count=sample_count,
        mean_score=_round_score(
            sum(score for score, _outcome in scored_observations) / sample_count,
        ),
        observed_positive_rate=_round_score(
            sum(outcome for _score, outcome in scored_observations) / sample_count,
        ),
        expected_calibration_error=_expected_calibration_error(
            scored_observations=scored_observations,
            bin_count=bin_count,
        ),
    )


def rank_candidate_claim(
    *,
    confidence: float,
    supporting_document_count: int,
    evidence_reference_count: int,
) -> ProposalRanking:
    """Compute a bounded ranking score for one candidate claim."""
    confidence_component = _bounded_score(confidence)
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
    grounded_sentence: bool | None = None,
    both_arguments_present: bool | None = None,
    entailment_supported: bool | None = None,
    relation_specific: bool | None = None,
) -> ProposalRanking:
    """Compute a ranking score for one reviewed document-extraction claim."""
    factual_component = _bounded_score(factual_confidence)
    relevance_component = _bounded_score(goal_relevance)
    priority_component = _bounded_score(priority)
    document_component = min(max(supporting_document_count, 0), 5) / 5
    evidence_component = min(max(evidence_reference_count, 0), 5) / 5
    grounded_component = _optional_binary_component(grounded_sentence)
    both_arguments_component = _optional_binary_component(both_arguments_present)
    entailment_component = _optional_binary_component(entailment_supported)
    relation_specificity_component = _optional_binary_component(relation_specific)
    evidence_quality_component = round(
        (grounded_component * 0.25)
        + (both_arguments_component * 0.25)
        + (entailment_component * 0.35)
        + (relation_specificity_component * 0.15),
        6,
    )
    score = round(
        min(
            1.0,
            (relevance_component * 0.3)
            + (priority_component * 0.25)
            + (factual_component * 0.2)
            + (evidence_quality_component * 0.2)
            + (document_component * 0.025)
            + (evidence_component * 0.025),
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
            "evidence_grounded_component": grounded_component,
            "both_arguments_present_component": both_arguments_component,
            "entailment_component": entailment_component,
            "relation_specificity_component": relation_specificity_component,
            "evidence_quality_component": evidence_quality_component,
        },
    )


def _optional_binary_component(value: bool | None) -> float:
    if value is None:
        return 0.5
    return 1.0 if value else 0.0


def _bounded_score(value: float) -> float:
    return max(0.0, min(value, 1.0))


def _round_score(value: float) -> float:
    return round(value, 6)


def _expected_calibration_error(
    *,
    scored_observations: tuple[tuple[float, float], ...],
    bin_count: int,
) -> float:
    if bin_count < 1:
        msg = "bin_count must be at least 1"
        raise ValueError(msg)
    total_count = len(scored_observations)
    error = 0.0
    for bin_index in range(bin_count):
        bin_items = tuple(
            item
            for item in scored_observations
            if _calibration_bin_index(score=item[0], bin_count=bin_count) == bin_index
        )
        if not bin_items:
            continue
        bin_confidence = sum(score for score, _outcome in bin_items) / len(bin_items)
        bin_accuracy = sum(outcome for _score, outcome in bin_items) / len(bin_items)
        error += (len(bin_items) / total_count) * abs(bin_confidence - bin_accuracy)
    return _round_score(error)


def _calibration_bin_index(*, score: float, bin_count: int) -> int:
    bounded_score = _bounded_score(score)
    if bounded_score == 1.0:
        return bin_count - 1
    return int(bounded_score * bin_count)


def rank_chat_graph_write_candidate(
    *,
    evidence_relevance: float,
    suggestion_final_score: float,
    vector_score: float,
    graph_overlap_score: float,
    relation_prior_score: float,
) -> ProposalRanking:
    """Compute a bounded ranking score for one chat-derived graph-write candidate."""
    evidence_component = _bounded_score(evidence_relevance)
    suggestion_component = _bounded_score(suggestion_final_score)
    vector_component = _bounded_score(vector_score)
    overlap_component = _bounded_score(graph_overlap_score)
    prior_component = _bounded_score(relation_prior_score)
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
    confidence_component = _bounded_score(confidence)
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
    "ReviewRankingCalibrationObservation",
    "ReviewRankingCalibrationSummary",
    "build_review_ranking_calibration_summary",
    "rank_chat_graph_write_candidate",
    "rank_candidate_claim",
    "rank_mechanism_candidate",
    "rank_reviewed_candidate_claim",
]
