"""Tests for review-only classification of weak relation evidence."""

from __future__ import annotations

import pytest
from artana_evidence_api.document_extraction_support.review_policy.review_only_candidate_policy import (
    classify_review_only_candidate,
)


@pytest.mark.parametrize(
    ("support_sentence", "expected_reasons"),
    [
        (
            "AKT activation showed a trend toward association with reduced survival.",
            {"hedged_language", "trend_only"},
        ),
        (
            "AKT activation showed a trend toward reduced survival.",
            {"hedged_language", "trend_only"},
        ),
        (
            "EGFR expression trended with erlotinib response.",
            {"hedged_language", "trend_only"},
        ),
        (
            "HRD score was described as a possible biomarker for platinum sensitivity.",
            {"hedged_language", "possible_biomarker"},
        ),
        (
            "IL6 may regulate inflammatory signaling in stressed epithelial cells.",
            {"hedged_language", "may_regulate"},
        ),
        (
            "MED13 may be linked to congenital heart disease.",
            {"hedged_language", "may_link"},
        ),
        (
            "MET amplification was correlated with resistance in a small cohort.",
            {"hedged_language", "correlated_only"},
        ),
        (
            "MET amplification correlated with resistance.",
            {"hedged_language", "correlated_only"},
        ),
    ],
)
def test_hedged_relation_claims_are_review_only(
    support_sentence: str,
    expected_reasons: set[str],
) -> None:
    decision = classify_review_only_candidate(
        relation_type="ASSOCIATED_WITH",
        support_sentence=support_sentence,
        value_level="low",
    )

    assert decision.review_only is True
    assert set(decision.reason_codes) == expected_reasons
    assert decision.trusted_promotion_allowed is False


def test_direct_relation_claims_remain_trusted_candidate_by_policy() -> None:
    decision = classify_review_only_candidate(
        relation_type="SENSITIZES_TO",
        support_sentence="BRCA1 loss sensitizes tumors to cisplatin.",
        value_level="high",
    )

    assert decision.review_only is False
    assert decision.reason_codes == ()
    assert decision.trusted_promotion_allowed is True


def test_weak_cues_are_scoped_to_candidate_arguments() -> None:
    sentence = (
        "BRCA1 activates EGFR, while MED13 may be linked to congenital heart "
        "disease."
    )

    strong_decision = classify_review_only_candidate(
        relation_type="ACTIVATES",
        support_sentence=sentence,
        subject_label="BRCA1",
        object_label="EGFR",
    )
    weak_decision = classify_review_only_candidate(
        relation_type="ASSOCIATED_WITH",
        support_sentence=sentence,
        subject_label="MED13",
        object_label="congenital heart disease",
    )

    assert strong_decision.review_only is False
    assert strong_decision.reason_codes == ()
    assert weak_decision.review_only is True
    assert set(weak_decision.reason_codes) == {"hedged_language", "may_link"}
