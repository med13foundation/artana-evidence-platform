"""Deterministic confidence scoring for governed AI decisions."""

from __future__ import annotations

from typing import Literal

from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.fact_assessment import (
    FactAssessment,
    assessment_confidence,
)
from pydantic import BaseModel, ConfigDict, Field

CONFIDENCE_MODEL_VERSION = "decision_confidence_v1"

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

_VALIDATION_CAPS: dict[DecisionValidationState, float] = {
    "VALID": 1.0,
    "VALID_WITH_GRAPH_REPAIR": 0.85,
    "REVIEW_REQUIRED": 0.65,
    "INVALID": 0.0,
}
_EVIDENCE_CAPS: dict[DecisionEvidenceState, float] = {
    "ACCEPTED_DIRECT_EVIDENCE": 1.0,
    "DIRECT_EVIDENCE_PRESENT": 0.9,
    "EVIDENCE_LOCATOR_ONLY": 0.7,
    "GENERATED_SUMMARY_ONLY": 0.55,
    "REQUIRED_EVIDENCE_MISSING": 0.0,
}
_DUPLICATE_CONFLICT_CAPS: dict[DecisionDuplicateConflictState, float] = {
    "CLEAR": 1.0,
    "DUPLICATE_EXISTING": 0.8,
    "POSSIBLE_DUPLICATE": 0.65,
    "CONFLICTING_CLAIM": 0.0,
}
_SOURCE_RELIABILITY_CAPS: dict[DecisionSourceReliability, float] = {
    "CURATED": 1.0,
    "TRUSTED_EXTERNAL": 0.9,
    "USER_UPLOADED": 0.8,
    "UNKNOWN": 0.6,
    "AI_GENERATED_ONLY": 0.55,
}
_RISK_CAPS: dict[DecisionRiskTier, float] = {
    "low": 1.0,
    "medium": 0.8,
    "high": 0.5,
}


class DecisionConfidenceAssessment(BaseModel):
    """Qualitative inputs used by the DB to score one governed AI decision."""

    model_config = ConfigDict(strict=False, extra="forbid")

    fact_assessment: FactAssessment
    validation_state: DecisionValidationState = "VALID"
    evidence_state: DecisionEvidenceState = "DIRECT_EVIDENCE_PRESENT"
    duplicate_conflict_state: DecisionDuplicateConflictState = "CLEAR"
    source_reliability: DecisionSourceReliability = "UNKNOWN"
    risk_tier: DecisionRiskTier = "low"
    rationale: str | None = Field(default=None, max_length=4000)


class DecisionConfidenceResult(BaseModel):
    """Deterministic scoring result persisted with AI decisions and events."""

    model_config = ConfigDict(strict=True)

    confidence_model_version: str
    computed_confidence: float = Field(ge=0.0, le=1.0)
    cap_values: dict[str, float]
    blocking_reasons: list[str]
    human_review_reasons: list[str]

    @property
    def blocked(self) -> bool:
        """Return whether hard policy blockers prevent the action."""
        return bool(self.blocking_reasons)

    @property
    def human_review_required(self) -> bool:
        """Return whether the scored decision should wait for human review."""
        return bool(self.human_review_reasons)

    def to_payload(self) -> JSONObject:
        """Serialize the result into a JSON-safe payload."""
        return {
            "confidence_model_version": self.confidence_model_version,
            "computed_confidence": self.computed_confidence,
            "cap_values": dict(self.cap_values),
            "blocking_reasons": list(self.blocking_reasons),
            "human_review_reasons": list(self.human_review_reasons),
        }


def decision_confidence_assessment_payload(
    assessment: DecisionConfidenceAssessment,
) -> JSONObject:
    """Serialize one confidence assessment into a JSON-safe payload."""
    return {
        "fact_assessment": {
            "support_band": str(assessment.fact_assessment.support_band),
            "grounding_level": str(assessment.fact_assessment.grounding_level),
            "mapping_status": str(assessment.fact_assessment.mapping_status),
            "speculation_level": str(assessment.fact_assessment.speculation_level),
            "confidence_rationale": assessment.fact_assessment.confidence_rationale,
        },
        "validation_state": assessment.validation_state,
        "evidence_state": assessment.evidence_state,
        "duplicate_conflict_state": assessment.duplicate_conflict_state,
        "source_reliability": assessment.source_reliability,
        "risk_tier": assessment.risk_tier,
        "rationale": assessment.rationale,
    }


def score_decision_confidence(
    assessment: DecisionConfidenceAssessment,
) -> DecisionConfidenceResult:
    """Compute a deterministic policy confidence from qualitative inputs."""
    fact_weight = assessment_confidence(assessment.fact_assessment)
    validation_cap = _VALIDATION_CAPS[assessment.validation_state]
    evidence_cap = _EVIDENCE_CAPS[assessment.evidence_state]
    duplicate_conflict_cap = _DUPLICATE_CONFLICT_CAPS[
        assessment.duplicate_conflict_state
    ]
    source_reliability_cap = _SOURCE_RELIABILITY_CAPS[assessment.source_reliability]
    risk_cap = _RISK_CAPS[assessment.risk_tier]
    cap_values = {
        "fact_assessment_weight": fact_weight,
        "validation_cap": validation_cap,
        "evidence_cap": evidence_cap,
        "duplicate_conflict_cap": duplicate_conflict_cap,
        "source_reliability_cap": source_reliability_cap,
        "risk_cap": risk_cap,
    }
    blocking_reasons: list[str] = []
    if assessment.validation_state == "INVALID":
        blocking_reasons.append("validation_state_invalid")
    if assessment.evidence_state == "REQUIRED_EVIDENCE_MISSING":
        blocking_reasons.append("required_evidence_missing")
    if assessment.duplicate_conflict_state == "CONFLICTING_CLAIM":
        blocking_reasons.append("conflicting_claim")

    human_review_reasons: list[str] = []
    if assessment.validation_state == "REVIEW_REQUIRED":
        human_review_reasons.append("validation_review_required")
    if assessment.duplicate_conflict_state == "POSSIBLE_DUPLICATE":
        human_review_reasons.append("possible_duplicate")
    if assessment.risk_tier in {"medium", "high"}:
        human_review_reasons.append(f"{assessment.risk_tier}_risk_requires_review")

    computed = min(cap_values.values())
    if blocking_reasons:
        computed = 0.0
    return DecisionConfidenceResult(
        confidence_model_version=CONFIDENCE_MODEL_VERSION,
        computed_confidence=max(0.0, min(computed, 1.0)),
        cap_values=cap_values,
        blocking_reasons=blocking_reasons,
        human_review_reasons=human_review_reasons,
    )


__all__ = [
    "CONFIDENCE_MODEL_VERSION",
    "DecisionConfidenceAssessment",
    "DecisionConfidenceResult",
    "DecisionDuplicateConflictState",
    "DecisionEvidenceState",
    "DecisionRiskTier",
    "DecisionSourceReliability",
    "DecisionValidationState",
    "decision_confidence_assessment_payload",
    "score_decision_confidence",
]
