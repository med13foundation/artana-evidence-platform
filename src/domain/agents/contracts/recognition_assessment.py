"""Recognition-specific qualitative assessment model for entity recognition."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class RecognitionBand(str, Enum):
    """Coarse support strength for a recognized entity or observation."""

    INSUFFICIENT = "INSUFFICIENT"
    TENTATIVE = "TENTATIVE"
    SUPPORTED = "SUPPORTED"
    STRONG = "STRONG"


class BoundaryQuality(str, Enum):
    """How clearly the source text boundaries support the candidate."""

    UNCLEAR = "UNCLEAR"
    PARTIAL = "PARTIAL"
    CLEAR = "CLEAR"


class NormalizationStatus(str, Enum):
    """How well the candidate maps to a normalized dictionary concept."""

    UNRESOLVED = "UNRESOLVED"
    PARTIAL = "PARTIAL"
    RESOLVED = "RESOLVED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class AmbiguityStatus(str, Enum):
    """How much ambiguity remains in the recognition decision."""

    AMBIGUOUS = "AMBIGUOUS"
    SOME_AMBIGUITY = "SOME_AMBIGUITY"
    CLEAR = "CLEAR"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class RecognitionAssessment(BaseModel):
    """Structured qualitative assessment for one recognized item."""

    recognition_band: RecognitionBand = Field(
        ...,
        description="Coarse support strength for the recognized item.",
    )
    boundary_quality: BoundaryQuality = Field(
        ...,
        description="How clearly the source boundaries support the item.",
    )
    normalization_status: NormalizationStatus = Field(
        ...,
        description="How well the item normalizes to a canonical concept.",
    )
    ambiguity_status: AmbiguityStatus = Field(
        ...,
        description="How much ambiguity remains in the recognition decision.",
    )
    confidence_rationale: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Short explanation for why this assessment was chosen.",
    )

    model_config = ConfigDict(use_enum_values=True)


_RECOGNITION_BAND_WEIGHTS: dict[RecognitionBand, float] = {
    RecognitionBand.INSUFFICIENT: 0.2,
    RecognitionBand.TENTATIVE: 0.45,
    RecognitionBand.SUPPORTED: 0.7,
    RecognitionBand.STRONG: 0.9,
}
_STRONG_CONFIDENCE_THRESHOLD = 0.85
_SUPPORTED_CONFIDENCE_THRESHOLD = 0.7
_TENTATIVE_CONFIDENCE_THRESHOLD = 0.45

_BOUNDARY_QUALITY_CAPS: dict[BoundaryQuality, float] = {
    BoundaryQuality.UNCLEAR: 0.5,
    BoundaryQuality.PARTIAL: 0.8,
    BoundaryQuality.CLEAR: 1.0,
}

_NORMALIZATION_STATUS_CAPS: dict[NormalizationStatus, float] = {
    NormalizationStatus.UNRESOLVED: 0.55,
    NormalizationStatus.PARTIAL: 0.75,
    NormalizationStatus.RESOLVED: 1.0,
    NormalizationStatus.NOT_APPLICABLE: 1.0,
}

_AMBIGUITY_STATUS_CAPS: dict[AmbiguityStatus, float] = {
    AmbiguityStatus.AMBIGUOUS: 0.55,
    AmbiguityStatus.SOME_AMBIGUITY: 0.75,
    AmbiguityStatus.CLEAR: 1.0,
    AmbiguityStatus.NOT_APPLICABLE: 1.0,
}


def build_recognition_assessment_from_confidence(
    confidence: float,
    *,
    confidence_rationale: str | None = None,
) -> RecognitionAssessment:
    """Convert a legacy numeric score into a qualitative recognition preset."""
    if confidence >= _STRONG_CONFIDENCE_THRESHOLD:
        recognition_band = RecognitionBand.STRONG
        boundary_quality = BoundaryQuality.CLEAR
        normalization_status = NormalizationStatus.RESOLVED
        ambiguity_status = AmbiguityStatus.CLEAR
    elif confidence >= _SUPPORTED_CONFIDENCE_THRESHOLD:
        recognition_band = RecognitionBand.SUPPORTED
        boundary_quality = BoundaryQuality.CLEAR
        normalization_status = NormalizationStatus.RESOLVED
        ambiguity_status = AmbiguityStatus.CLEAR
    elif confidence >= _TENTATIVE_CONFIDENCE_THRESHOLD:
        recognition_band = RecognitionBand.TENTATIVE
        boundary_quality = BoundaryQuality.PARTIAL
        normalization_status = NormalizationStatus.PARTIAL
        ambiguity_status = AmbiguityStatus.SOME_AMBIGUITY
    else:
        recognition_band = RecognitionBand.INSUFFICIENT
        boundary_quality = BoundaryQuality.UNCLEAR
        normalization_status = NormalizationStatus.UNRESOLVED
        ambiguity_status = AmbiguityStatus.AMBIGUOUS
    return RecognitionAssessment(
        recognition_band=recognition_band,
        boundary_quality=boundary_quality,
        normalization_status=normalization_status,
        ambiguity_status=ambiguity_status,
        confidence_rationale=(
            confidence_rationale
            or "Legacy numeric confidence converted to qualitative recognition."
        ),
    )


def recognition_assessment_confidence(assessment: RecognitionAssessment) -> float:
    """Derive a deterministic numeric weight from a recognition assessment."""
    band = RecognitionBand(assessment.recognition_band)
    boundary_quality = BoundaryQuality(assessment.boundary_quality)
    normalization_status = NormalizationStatus(assessment.normalization_status)
    ambiguity_status = AmbiguityStatus(assessment.ambiguity_status)
    base_weight = _RECOGNITION_BAND_WEIGHTS[band]
    capped_weight = min(
        base_weight,
        _BOUNDARY_QUALITY_CAPS[boundary_quality],
        _NORMALIZATION_STATUS_CAPS[normalization_status],
        _AMBIGUITY_STATUS_CAPS[ambiguity_status],
    )
    return max(0.0, min(capped_weight, 1.0))


__all__ = [
    "AmbiguityStatus",
    "BoundaryQuality",
    "NormalizationStatus",
    "RecognitionAssessment",
    "RecognitionBand",
    "build_recognition_assessment_from_confidence",
    "recognition_assessment_confidence",
]
