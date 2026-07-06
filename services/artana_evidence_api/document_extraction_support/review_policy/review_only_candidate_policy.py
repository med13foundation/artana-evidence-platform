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


_TREND_RE = re.compile(
    r"\btrend(?:ed|s|ing)?\s+(?:toward|with)\b",
    re.IGNORECASE,
)
_POSSIBLE_BIOMARKER_RE = re.compile(
    r"\b(possible|potential|putative)\s+biomarker\b",
    re.IGNORECASE,
)
_MAY_REGULATE_RE = re.compile(r"\bmay\s+regulat(?:e|es|ed|ing|ion)\b", re.IGNORECASE)
_MAY_LINK_RE = re.compile(
    r"\bmay\s+(?:be\s+)?(?:link(?:ed)?|associat(?:ed|e))\s+(?:to|with)\b",
    re.IGNORECASE,
)
_CORRELATED_RE = re.compile(r"\bcorrelat(?:e|es|ed|ing|ion)\s+with\b", re.IGNORECASE)
_WEAK_LANGUAGE_RE = re.compile(
    r"\b(?:may|might|possible|potential|trend|weakly)\b",
    re.IGNORECASE,
)
_BARE_AND_CLAIM_BOUNDARY_PATTERN = (
    r"\band\s+(?="
    r"[A-Z0-9][A-Za-z0-9*.-]*"
    r"(?:\s+[A-Za-z0-9*.-]+){0,5}\s+"
    r"(?:"
    r"activat(?:e|es|ed|ing|ion)|associat(?:e|es|ed|ing|ion)|"
    r"biomarker|confers?|correlat(?:e|es|ed|ing|ion)|"
    r"express(?:es|ed|ing|ion)?|inhibit(?:s|ed|ing)?|is|may|might|"
    r"predic(?:t|ts|ted|ting)|regulat(?:e|es|ed|ing|ion)|"
    r"sensitiz(?:e|es|ed|ing)|target(?:s|ed|ing)?|"
    r"trend(?:ed|s|ing)?|was|were"
    r")\b"
    r")"
)


def classify_review_only_candidate(
    *,
    relation_type: str,
    support_sentence: str,
    value_level: str | None = None,
    subject_label: str | None = None,
    object_label: str | None = None,
) -> ReviewOnlyDecision:
    """Classify weak relation evidence that should be review-only."""

    del relation_type
    cue_text = _candidate_claim_text(
        support_sentence=support_sentence,
        subject_label=subject_label,
        object_label=object_label,
    )
    reasons: list[str] = []
    if _TREND_RE.search(cue_text) is not None:
        reasons.append("trend_only")
    if _POSSIBLE_BIOMARKER_RE.search(cue_text) is not None:
        reasons.append("possible_biomarker")
    if _MAY_REGULATE_RE.search(cue_text) is not None:
        reasons.append("may_regulate")
    if _MAY_LINK_RE.search(cue_text) is not None:
        reasons.append("may_link")
    if _CORRELATED_RE.search(cue_text) is not None:
        reasons.append("correlated_only")
    if (
        reasons
        or _WEAK_LANGUAGE_RE.search(cue_text) is not None
        or value_level in {"low", "reject"}
    ):
        reasons.insert(0, "hedged_language")
    reason_codes = tuple(dict.fromkeys(reasons))
    review_only = bool(reason_codes)
    return ReviewOnlyDecision(
        review_only=review_only,
        reason_codes=reason_codes,
        trusted_promotion_allowed=not review_only,
    )


def _candidate_claim_text(
    *,
    support_sentence: str,
    subject_label: str | None,
    object_label: str | None,
) -> str:
    if subject_label is None or object_label is None:
        return support_sentence
    subject_pattern = _label_pattern(subject_label)
    object_pattern = _label_pattern(object_label)
    if subject_pattern == "" or object_pattern == "":
        return support_sentence
    clauses = [
        clause
        for clause in _split_candidate_clauses(support_sentence)
        if re.search(subject_pattern, clause, flags=re.IGNORECASE) is not None
        and re.search(object_pattern, clause, flags=re.IGNORECASE) is not None
    ]
    return " ".join(clauses) if clauses else support_sentence


def _label_pattern(label: str) -> str:
    normalized = " ".join(label.strip().split())
    if normalized == "":
        return ""
    return r"\b" + r"\s+".join(re.escape(token) for token in normalized.split()) + r"\b"


def _split_candidate_clauses(sentence: str) -> tuple[str, ...]:
    return tuple(
        clause.strip(" ,")
        for clause in re.split(
            r"(?:"
            r"[.;:]|"
            r",\s*(?:and|while|whereas|but)\b|"
            r"\b(?:while|whereas|but)\b|"
            rf"{_BARE_AND_CLAIM_BOUNDARY_PATTERN}"
            r")",
            sentence,
            flags=re.IGNORECASE,
        )
        if clause.strip(" ,")
    )


__all__ = ["ReviewOnlyDecision", "classify_review_only_candidate"]
