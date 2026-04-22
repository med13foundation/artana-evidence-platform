"""
Evidence API schemas for Artana Resource Library.

Pydantic models for evidence-related API requests and responses.
"""

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from .common import PhenotypeSummary, PublicationSummary, VariantLinkSummary


class EvidenceLevel(str, Enum):
    """Evidence confidence level classification."""

    DEFINITIVE = "definitive"
    STRONG = "strong"
    MODERATE = "moderate"
    SUPPORTING = "supporting"
    WEAK = "weak"
    DISPROVEN = "disproven"


class EvidenceType(str, Enum):
    """Type of evidence supporting the association."""

    CLINICAL_REPORT = "clinical_report"
    FUNCTIONAL_STUDY = "functional_study"
    ANIMAL_MODEL = "animal_model"
    BIOCHEMICAL = "biochemical"
    COMPUTATIONAL = "computational"
    LITERATURE_REVIEW = "literature_review"
    EXPERT_OPINION = "expert_opinion"


class EvidenceCreate(BaseModel):
    """
    Schema for creating new evidence records.

    Links variants to phenotypes with supporting evidence.
    """

    model_config = ConfigDict(strict=True)

    # Required relationships
    variant_id: str = Field(..., description="Associated variant identifier")
    phenotype_id: str = Field(..., description="Associated phenotype HPO ID")

    # Evidence content
    description: str = Field(..., description="Evidence description")
    summary: str | None = Field(None, description="Brief summary")

    # Classification
    evidence_level: EvidenceLevel = Field(
        default=EvidenceLevel.SUPPORTING,
        description="Evidence level",
    )
    evidence_type: EvidenceType = Field(
        default=EvidenceType.LITERATURE_REVIEW,
        description="Evidence type",
    )

    # Optional publication
    publication_id: str | None = Field(
        None,
        description="Associated publication identifier",
    )

    # Confidence and scoring
    confidence_score: float = Field(
        default=0.5,
        ge=0,
        le=1,
        description="Confidence score (0-1)",
    )
    quality_score: int | None = Field(
        None,
        ge=1,
        le=10,
        description="Quality score (1-10)",
    )

    # Study details
    sample_size: int | None = Field(None, ge=1, description="Sample size")
    study_type: str | None = Field(None, max_length=100, description="Study type")
    statistical_significance: str | None = Field(
        None,
        max_length=50,
        description="Statistical significance",
    )

    # Review information
    reviewed: bool = Field(
        default=False,
        description="Whether evidence has been reviewed",
    )
    review_date: date | None = Field(None, description="Review date")
    reviewer_notes: str | None = Field(None, description="Reviewer notes")


class EvidenceUpdate(BaseModel):
    """
    Schema for updating existing evidence records.

    All fields are optional for partial updates.
    """

    model_config = ConfigDict(strict=True)

    # Updatable content
    description: str | None = None
    summary: str | None = None

    # Classification
    evidence_level: EvidenceLevel | None = None
    evidence_type: EvidenceType | None = None

    # Publication
    publication_id: str | None = None

    # Confidence and scoring
    confidence_score: float | None = Field(None, ge=0, le=1)
    quality_score: int | None = Field(None, ge=1, le=10)

    # Study details
    sample_size: int | None = Field(None, ge=1)
    study_type: str | None = Field(None, max_length=100)
    statistical_significance: str | None = Field(None, max_length=50)

    # Review information
    reviewed: bool | None = None
    review_date: date | None = None
    reviewer_notes: str | None = None


class EvidenceResponse(BaseModel):
    """
    Complete evidence response schema for API endpoints.

    Includes all evidence data plus computed fields and relationships.
    """

    model_config = ConfigDict(strict=True, from_attributes=True)

    # Primary identifiers
    id: int = Field(..., description="Database primary key")

    # Relationships
    variant_id: str = Field(..., description="Associated variant identifier")
    phenotype_id: str = Field(..., description="Associated phenotype HPO ID")
    publication_id: str | None = Field(
        None,
        description="Associated publication identifier",
    )

    # Evidence content
    description: str = Field(..., description="Evidence description")
    summary: str | None = Field(None, description="Brief summary")

    # Classification
    evidence_level: EvidenceLevel = Field(..., description="Evidence level")
    evidence_type: EvidenceType = Field(..., description="Evidence type")

    # Confidence and scoring
    confidence_score: float = Field(..., description="Confidence score (0-1)")
    quality_score: int | None = Field(
        None,
        ge=1,
        le=10,
        description="Quality score (1-10)",
    )

    # Study details
    sample_size: int | None = Field(None, description="Sample size")
    study_type: str | None = Field(None, description="Study type")
    statistical_significance: str | None = Field(
        None,
        description="Statistical significance",
    )

    # Review information
    reviewed: bool = Field(..., description="Whether evidence has been reviewed")
    review_date: date | None = Field(None, description="Review date")
    reviewer_notes: str | None = Field(None, description="Reviewer notes")

    # Metadata
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    # Optional relationships (included based on query parameters)
    variant: VariantLinkSummary | None = Field(None, description="Variant details")
    phenotype: PhenotypeSummary | None = Field(None, description="Phenotype details")
    publication: PublicationSummary | None = Field(
        None,
        description="Publication details",
    )


# Lightweight DTO for embedding evidence summaries in other responses
class EvidenceSummaryResponse(BaseModel):
    """
    Minimal evidence summary used in nested collections.

    Matches the legacy `EvidenceSummary` structure but provides a typed DTO.
    """

    id: int | None = Field(None, description="Evidence identifier")
    evidence_level: str = Field(..., description="Evidence confidence level label")
    evidence_type: str = Field(..., description="Evidence type label")
    description: str = Field(..., description="Evidence description")
    reviewed: bool = Field(..., description="Whether evidence has been reviewed")


# Type aliases for API documentation
EvidenceList = list[EvidenceResponse]
