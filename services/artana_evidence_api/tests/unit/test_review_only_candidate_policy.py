"""Tests for review-only classification of weak relation evidence."""

from __future__ import annotations

import pytest
from artana_evidence_api.document_extraction_support.review_policy.review_only_candidate_policy import (
    classify_review_only_candidate,
)


@pytest.mark.parametrize(
    ("support_sentence", "expected_reason"),
    [
        (
            "AKT activation showed a trend toward association with reduced survival.",
            "trend_only",
        ),
        (
            "HRD score was described as a possible biomarker for platinum sensitivity.",
            "possible_biomarker",
        ),
        (
            "IL6 may regulate inflammatory signaling in stressed epithelial cells.",
            "may_regulate",
        ),
        (
            "MET amplification was correlated with resistance in a small cohort.",
            "correlated_only",
        ),
    ],
)
def test_hedged_relation_claims_are_review_only(
    support_sentence: str,
    expected_reason: str,
) -> None:
    decision = classify_review_only_candidate(
        relation_type="ASSOCIATED_WITH",
        support_sentence=support_sentence,
        value_level="low",
    )

    assert decision.review_only is True
    assert expected_reason in decision.reason_codes
    assert "hedged_language" in decision.reason_codes
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
