"""Shared qualitative assessment model for fact-bearing agent outputs."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class SupportBand(str, Enum):
    """Coarse support strength for a fact or candidate."""

    INSUFFICIENT = "INSUFFICIENT"
    TENTATIVE = "TENTATIVE"
    SUPPORTED = "SUPPORTED"
    STRONG = "STRONG"


class GroundingLevel(str, Enum):
    """How directly the assessment is grounded in source material."""

    SPAN = "SPAN"
    SECTION = "SECTION"
    DOCUMENT = "DOCUMENT"
    GENERATED = "GENERATED"
    GRAPH_INFERENCE = "GRAPH_INFERENCE"


class MappingStatus(str, Enum):
    """Whether the fact endpoints were resolved cleanly."""

    RESOLVED = "RESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class SpeculationLevel(str, Enum):
    """How speculative the supporting language is."""

    DIRECT = "DIRECT"
    HEDGED = "HEDGED"
    HYPOTHETICAL = "HYPOTHETICAL"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FactAssessment(BaseModel):
    """Structured qualitative assessment for one fact or candidate."""

    support_band: SupportBand = Field(
        ...,
        description="Coarse support strength for the fact or candidate.",
    )
    grounding_level: GroundingLevel = Field(
        ...,
        description="How directly the assessment is grounded in source material.",
    )
    mapping_status: MappingStatus = Field(
        ...,
        description="Whether the relevant endpoints were resolved cleanly.",
    )
    speculation_level: SpeculationLevel = Field(
        ...,
        description="How speculative the supporting language is.",
    )
    confidence_rationale: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Short explanation for why this assessment was chosen.",
    )

    model_config = ConfigDict(use_enum_values=True)


_SUPPORT_BAND_RANKS: dict[SupportBand, int] = {
    SupportBand.INSUFFICIENT: 0,
    SupportBand.TENTATIVE: 1,
    SupportBand.SUPPORTED: 2,
    SupportBand.STRONG: 3,
}

_GROUNDING_LEVEL_RANKS: dict[GroundingLevel, int] = {
    GroundingLevel.GRAPH_INFERENCE: 0,
    GroundingLevel.GENERATED: 1,
    GroundingLevel.DOCUMENT: 2,
    GroundingLevel.SECTION: 3,
    GroundingLevel.SPAN: 4,
}

_MAPPING_STATUS_RANKS: dict[MappingStatus, int] = {
    MappingStatus.NOT_APPLICABLE: 0,
    MappingStatus.AMBIGUOUS: 1,
    MappingStatus.RESOLVED: 2,
}

_SPECULATION_LEVEL_RANKS: dict[SpeculationLevel, int] = {
    SpeculationLevel.NOT_APPLICABLE: 0,
    SpeculationLevel.HYPOTHETICAL: 1,
    SpeculationLevel.HEDGED: 2,
    SpeculationLevel.DIRECT: 3,
}

_SUPPORT_BAND_WEIGHTS: dict[SupportBand, float] = {
    SupportBand.INSUFFICIENT: 0.2,
    SupportBand.TENTATIVE: 0.45,
    SupportBand.SUPPORTED: 0.7,
    SupportBand.STRONG: 0.9,
}
_STRONG_CONFIDENCE_THRESHOLD = 0.85
_SUPPORTED_CONFIDENCE_THRESHOLD = 0.7
_TENTATIVE_CONFIDENCE_THRESHOLD = 0.45

_GROUNDING_LEVEL_CAPS: dict[GroundingLevel, float] = {
    GroundingLevel.SPAN: 1.0,
    GroundingLevel.SECTION: 0.85,
    GroundingLevel.DOCUMENT: 0.7,
    GroundingLevel.GENERATED: 0.55,
    GroundingLevel.GRAPH_INFERENCE: 0.85,
}

_MAPPING_STATUS_CAPS: dict[MappingStatus, float] = {
    MappingStatus.RESOLVED: 1.0,
    MappingStatus.AMBIGUOUS: 0.65,
    MappingStatus.NOT_APPLICABLE: 1.0,
}

_SPECULATION_LEVEL_CAPS: dict[SpeculationLevel, float] = {
    SpeculationLevel.DIRECT: 1.0,
    SpeculationLevel.HEDGED: 0.75,
    SpeculationLevel.HYPOTHETICAL: 0.55,
    SpeculationLevel.NOT_APPLICABLE: 1.0,
}


def build_fact_assessment_from_confidence(
    confidence: float,
    *,
    confidence_rationale: str,
    grounding_level: GroundingLevel,
    mapping_status: MappingStatus,
    speculation_level: SpeculationLevel,
) -> FactAssessment:
    """Convert a legacy numeric score into a qualitative assessment preset."""
    if confidence >= _STRONG_CONFIDENCE_THRESHOLD:
        support_band = SupportBand.STRONG
    elif confidence >= _SUPPORTED_CONFIDENCE_THRESHOLD:
        support_band = SupportBand.SUPPORTED
    elif confidence >= _TENTATIVE_CONFIDENCE_THRESHOLD:
        support_band = SupportBand.TENTATIVE
    else:
        support_band = SupportBand.INSUFFICIENT
    return FactAssessment(
        support_band=support_band,
        grounding_level=grounding_level,
        mapping_status=mapping_status,
        speculation_level=speculation_level,
        confidence_rationale=confidence_rationale,
    )


def assessment_confidence_weight(assessment: FactAssessment) -> float:
    """Derive a deterministic numeric weight from a qualitative assessment."""
    support_band = SupportBand(assessment.support_band)
    grounding_level = GroundingLevel(assessment.grounding_level)
    mapping_status = MappingStatus(assessment.mapping_status)
    speculation_level = SpeculationLevel(assessment.speculation_level)
    base_weight = _SUPPORT_BAND_WEIGHTS[support_band]
    capped_weight = min(
        base_weight,
        _GROUNDING_LEVEL_CAPS[grounding_level],
        _MAPPING_STATUS_CAPS[mapping_status],
        _SPECULATION_LEVEL_CAPS[speculation_level],
    )
    return max(0.0, min(capped_weight, 1.0))


def assessment_priority(assessment: FactAssessment) -> tuple[int, int, int, int]:
    """Return a deterministic ordering key for comparison and merging."""
    return (
        _SUPPORT_BAND_RANKS[SupportBand(assessment.support_band)],
        _GROUNDING_LEVEL_RANKS[GroundingLevel(assessment.grounding_level)],
        _MAPPING_STATUS_RANKS[MappingStatus(assessment.mapping_status)],
        _SPECULATION_LEVEL_RANKS[SpeculationLevel(assessment.speculation_level)],
    )


def is_stronger_assessment(candidate: FactAssessment, existing: FactAssessment) -> bool:
    """Return True when the candidate should replace the existing assessment."""
    return assessment_priority(candidate) > assessment_priority(existing)


def assessment_confidence(assessment: FactAssessment) -> float:
    """Backward-compatible alias for the derived confidence helper."""
    return assessment_confidence_weight(assessment)


__all__ = [
    "FactAssessment",
    "GroundingLevel",
    "MappingStatus",
    "SpeculationLevel",
    "SupportBand",
    "assessment_confidence",
    "assessment_priority",
    "assessment_confidence_weight",
    "build_fact_assessment_from_confidence",
    "is_stronger_assessment",
]
