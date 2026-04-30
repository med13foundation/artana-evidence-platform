"""Decision-confidence contract models for the graph service boundary."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .graph_fact_assessment import FactAssessment

DecisionValidationState = Literal[
    "VALID",
    "VALID_WITH_GRAPH_REPAIR",
    "REVIEW_REQUIRED",
    "INVALID",
]
DecisionEvidenceState = Literal[
    "ACCEPTED_DIRECT_EVIDENCE",
    "DIRECT_EVIDENCE_PRESENT",
    "EVIDENCE_LOCATOR_ONLY",
    "GENERATED_SUMMARY_ONLY",
    "REQUIRED_EVIDENCE_MISSING",
]
DecisionDuplicateConflictState = Literal[
    "CLEAR",
    "DUPLICATE_EXISTING",
    "POSSIBLE_DUPLICATE",
    "CONFLICTING_CLAIM",
]
DecisionSourceReliability = Literal[
    "CURATED",
    "TRUSTED_EXTERNAL",
    "USER_UPLOADED",
    "UNKNOWN",
    "AI_GENERATED_ONLY",
]
DecisionRiskTier = Literal["low", "medium", "high"]


class DecisionConfidenceAssessment(BaseModel):
    """Qualitative inputs the graph DB uses to score governed AI decisions."""

    model_config = ConfigDict(strict=False, extra="forbid")

    fact_assessment: FactAssessment
    validation_state: DecisionValidationState = "VALID"
    evidence_state: DecisionEvidenceState = "DIRECT_EVIDENCE_PRESENT"
    duplicate_conflict_state: DecisionDuplicateConflictState = "CLEAR"
    source_reliability: DecisionSourceReliability = "UNKNOWN"
    risk_tier: DecisionRiskTier = "low"
    rationale: str | None = Field(default=None, max_length=4000)


class DecisionConfidenceResult(BaseModel):
    """DB-computed policy confidence result."""

    model_config = ConfigDict(strict=True)

    confidence_model_version: str
    computed_confidence: float = Field(ge=0.0, le=1.0)
    cap_values: dict[str, float]
    blocking_reasons: list[str]
    human_review_reasons: list[str]

__all__ = [
    "DecisionConfidenceAssessment",
    "DecisionConfidenceResult",
    "DecisionDuplicateConflictState",
    "DecisionEvidenceState",
    "DecisionRiskTier",
    "DecisionSourceReliability",
    "DecisionValidationState",
]
