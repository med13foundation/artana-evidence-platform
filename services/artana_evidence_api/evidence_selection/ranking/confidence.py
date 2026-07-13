"""Deterministic compatibility confidence for evidence-review queue records."""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ReviewConfidenceCategory = Literal[
    "strong_fit",
    "plausible_fit",
    "context_only",
    "off_objective",
    "needs_human_review",
    "deferred",
]

_CATEGORY_WEIGHTS: dict[ReviewConfidenceCategory, float] = {
    "strong_fit": 0.8,
    "plausible_fit": 0.65,
    "needs_human_review": 0.5,
    "context_only": 0.35,
    "off_objective": 0.2,
    "deferred": 0.0,
}


class DeterministicReviewConfidence(BaseModel):
    """Versioned qualitative projection for a legacy numeric queue field."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        json_schema_extra={"x-artana-numeric-origin": "deterministic_policy"},
    )

    origin: Literal["deterministic_policy"] = "deterministic_policy"
    value: float = Field(ge=0.0, le=1.0)
    category: ReviewConfidenceCategory
    policy_id: Literal["evidence_selection_review_confidence"] = (
        "evidence_selection_review_confidence"
    )
    policy_version: Literal["v1"] = "v1"
    semantics: Literal["deterministic_weight_not_probability"] = (
        "deterministic_weight_not_probability"
    )

    @field_validator("value")
    @classmethod
    def _require_finite_weight(cls, value: float) -> float:
        if not math.isfinite(value):
            msg = "review confidence weight must be finite"
            raise ValueError(msg)
        return value


def deterministic_review_confidence(
    category: ReviewConfidenceCategory,
) -> DeterministicReviewConfidence:
    """Map one categorical relevance finding through a versioned policy."""

    return DeterministicReviewConfidence(
        value=_CATEGORY_WEIGHTS[category],
        category=category,
    )


__all__ = [
    "DeterministicReviewConfidence",
    "ReviewConfidenceCategory",
    "deterministic_review_confidence",
]
