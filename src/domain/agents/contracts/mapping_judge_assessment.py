"""Qualitative assessment model for mapping-judge decisions."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class MappingSupportBand(str, Enum):
    """Coarse support strength for a mapping decision."""

    INSUFFICIENT = "INSUFFICIENT"
    TENTATIVE = "TENTATIVE"
    SUPPORTED = "SUPPORTED"
    STRONG = "STRONG"


class MappingResolutionStatus(str, Enum):
    """Whether the judge considers the candidate set resolved."""

    RESOLVED = "RESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    NO_MATCH = "NO_MATCH"


class CandidateSeparation(str, Enum):
    """How clearly the winning mapping separates from alternatives."""

    CLEAR = "CLEAR"
    MODERATE = "MODERATE"
    TIGHT = "TIGHT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class MappingJudgeAssessment(BaseModel):
    """Structured qualitative assessment for one mapping-judge decision."""

    resolution_status: MappingResolutionStatus = Field(
        ...,
        description="Whether the candidate set is resolved, ambiguous, or rejected.",
    )
    support_band: MappingSupportBand = Field(
        ...,
        description="Coarse support strength for the mapping decision.",
    )
    candidate_separation: CandidateSeparation = Field(
        ...,
        description="How clearly the best candidate beats the alternatives.",
    )
    confidence_rationale: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Short explanation for why this assessment was chosen.",
    )

    model_config = ConfigDict(use_enum_values=True)


_SUPPORT_BAND_WEIGHTS: dict[MappingSupportBand, float] = {
    MappingSupportBand.INSUFFICIENT: 0.2,
    MappingSupportBand.TENTATIVE: 0.45,
    MappingSupportBand.SUPPORTED: 0.7,
    MappingSupportBand.STRONG: 0.9,
}
_STRONG_CONFIDENCE_THRESHOLD = 0.85
_SUPPORTED_CONFIDENCE_THRESHOLD = 0.7
_TENTATIVE_CONFIDENCE_THRESHOLD = 0.45

_RESOLUTION_CAPS: dict[MappingResolutionStatus, float] = {
    MappingResolutionStatus.RESOLVED: 1.0,
    MappingResolutionStatus.AMBIGUOUS: 0.65,
    MappingResolutionStatus.NO_MATCH: 0.0,
}

_SEPARATION_CAPS: dict[CandidateSeparation, float] = {
    CandidateSeparation.CLEAR: 1.0,
    CandidateSeparation.MODERATE: 0.85,
    CandidateSeparation.TIGHT: 0.65,
    CandidateSeparation.NOT_APPLICABLE: 1.0,
}

_SUPPORT_BAND_RANKS: dict[MappingSupportBand, int] = {
    MappingSupportBand.INSUFFICIENT: 0,
    MappingSupportBand.TENTATIVE: 1,
    MappingSupportBand.SUPPORTED: 2,
    MappingSupportBand.STRONG: 3,
}

_RESOLUTION_RANKS: dict[MappingResolutionStatus, int] = {
    MappingResolutionStatus.NO_MATCH: 0,
    MappingResolutionStatus.AMBIGUOUS: 1,
    MappingResolutionStatus.RESOLVED: 2,
}

_SEPARATION_RANKS: dict[CandidateSeparation, int] = {
    CandidateSeparation.NOT_APPLICABLE: 0,
    CandidateSeparation.TIGHT: 1,
    CandidateSeparation.MODERATE: 2,
    CandidateSeparation.CLEAR: 3,
}


def build_mapping_judge_assessment_from_confidence(
    confidence: float,
    *,
    confidence_rationale: str,
    resolution_status: MappingResolutionStatus,
    candidate_separation: CandidateSeparation,
) -> MappingJudgeAssessment:
    """Convert a numeric score into a qualitative mapping assessment."""
    if confidence >= _STRONG_CONFIDENCE_THRESHOLD:
        support_band = MappingSupportBand.STRONG
    elif confidence >= _SUPPORTED_CONFIDENCE_THRESHOLD:
        support_band = MappingSupportBand.SUPPORTED
    elif confidence >= _TENTATIVE_CONFIDENCE_THRESHOLD:
        support_band = MappingSupportBand.TENTATIVE
    else:
        support_band = MappingSupportBand.INSUFFICIENT
    return MappingJudgeAssessment(
        support_band=support_band,
        resolution_status=resolution_status,
        candidate_separation=candidate_separation,
        confidence_rationale=confidence_rationale,
    )


def mapping_judge_assessment_confidence(assessment: MappingJudgeAssessment) -> float:
    """Derive a deterministic numeric weight from a qualitative assessment."""
    support_band = MappingSupportBand(assessment.support_band)
    resolution_status = MappingResolutionStatus(assessment.resolution_status)
    candidate_separation = CandidateSeparation(assessment.candidate_separation)
    base_weight = _SUPPORT_BAND_WEIGHTS[support_band]
    capped_weight = min(
        base_weight,
        _RESOLUTION_CAPS[resolution_status],
        _SEPARATION_CAPS[candidate_separation],
    )
    return max(0.0, min(capped_weight, 1.0))


def mapping_judge_assessment_priority(
    assessment: MappingJudgeAssessment,
) -> tuple[int, int, int]:
    """Return an ordering key for comparison and tie-breaking."""
    return (
        _SUPPORT_BAND_RANKS[MappingSupportBand(assessment.support_band)],
        _RESOLUTION_RANKS[MappingResolutionStatus(assessment.resolution_status)],
        _SEPARATION_RANKS[CandidateSeparation(assessment.candidate_separation)],
    )


__all__ = [
    "CandidateSeparation",
    "MappingJudgeAssessment",
    "MappingResolutionStatus",
    "MappingSupportBand",
    "build_mapping_judge_assessment_from_confidence",
    "mapping_judge_assessment_confidence",
    "mapping_judge_assessment_priority",
]
