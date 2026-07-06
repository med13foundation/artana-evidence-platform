"""Review-only policy for weak but useful relation evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReviewOnlyDecision:
    """Policy decision for a relation candidate's review lane."""

    review_only: bool
    reason_codes: tuple[str, ...]
    trusted_promotion_allowed: bool


_TREND_RE = re.compile(r"\btrend(?:ed)?\s+toward\b|\btrend\s+with\b", re.IGNORECASE)
_POSSIBLE_BIOMARKER_RE = re.compile(
    r"\b(possible|potential|putative)\s+biomarker\b",
    re.IGNORECASE,
)
_MAY_REGULATE_RE = re.compile(r"\bmay\s+regulat(?:e|es|ed|ing|ion)\b", re.IGNORECASE)
_CORRELATED_RE = re.compile(r"\bcorrelat(?:e|es|ed|ing|ion)\s+with\b", re.IGNORECASE)
_WEAK_LANGUAGE_RE = re.compile(
    r"\b(?:may|might|possible|potential|trend|weakly)\b",
    re.IGNORECASE,
)


def classify_review_only_candidate(
    *,
    relation_type: str,
    support_sentence: str,
    value_level: str | None = None,
) -> ReviewOnlyDecision:
    """Classify weak relation evidence that should be review-only."""

    del relation_type
    reasons: list[str] = []
    if _TREND_RE.search(support_sentence) is not None:
        reasons.append("trend_only")
    if _POSSIBLE_BIOMARKER_RE.search(support_sentence) is not None:
        reasons.append("possible_biomarker")
    if _MAY_REGULATE_RE.search(support_sentence) is not None:
        reasons.append("may_regulate")
    if _CORRELATED_RE.search(support_sentence) is not None:
        reasons.append("correlated_only")
    if _WEAK_LANGUAGE_RE.search(support_sentence) is not None or value_level in {
        "low",
        "reject",
    }:
        reasons.insert(0, "hedged_language")
    reason_codes = tuple(dict.fromkeys(reasons))
    review_only = bool(reason_codes)
    return ReviewOnlyDecision(
        review_only=review_only,
        reason_codes=reason_codes,
        trusted_promotion_allowed=not review_only,
    )


__all__ = ["ReviewOnlyDecision", "classify_review_only_candidate"]
