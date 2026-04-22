"""
Statement of Understanding API schemas for Artana Resource Library.

Pydantic models for statement-related API requests and responses.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from .evidence import EvidenceLevel
from .mechanism import ProteinDomainPayload


class StatementStatus(str, Enum):
    """Lifecycle status for Statements of Understanding."""

    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    WELL_SUPPORTED = "well_supported"


class StatementCreate(BaseModel):
    """Schema for creating new statements of understanding."""

    model_config = ConfigDict(strict=True)

    title: str = Field(..., min_length=1, max_length=200)
    summary: str = Field(..., min_length=1, max_length=4000)
    evidence_tier: EvidenceLevel = Field(
        default=EvidenceLevel.SUPPORTING,
        description="Evidence tier for this statement",
    )
    confidence_score: float = Field(
        default=0.5,
        ge=0,
        le=1,
        description="Confidence score between 0.0 and 1.0",
    )
    status: StatementStatus = Field(
        default=StatementStatus.DRAFT,
        description="Maturity status for this statement",
    )
    source: str = Field(default="manual_curation", max_length=100)
    protein_domains: list[ProteinDomainPayload] = Field(default_factory=list)
    phenotype_ids: list[int] = Field(default_factory=list)


class StatementUpdate(BaseModel):
    """Schema for updating existing statements."""

    model_config = ConfigDict(strict=True)

    title: str | None = Field(None, min_length=1, max_length=200)
    summary: str | None = Field(None, max_length=4000)
    evidence_tier: EvidenceLevel | None = None
    confidence_score: float | None = Field(None, ge=0, le=1)
    status: StatementStatus | None = None
    source: str | None = Field(None, max_length=100)
    protein_domains: list[ProteinDomainPayload] | None = None
    phenotype_ids: list[int] | None = None
    promoted_mechanism_id: int | None = None


class StatementResponse(BaseModel):
    """Statement response schema for API endpoints."""

    model_config = ConfigDict(strict=True, from_attributes=True)

    id: int = Field(..., description="Database primary key")
    title: str
    summary: str
    evidence_tier: EvidenceLevel
    confidence_score: float
    status: StatementStatus
    source: str
    protein_domains: list[ProteinDomainPayload]
    phenotype_ids: list[int]
    phenotype_count: int
    promoted_mechanism_id: int | None = None
    created_at: datetime
    updated_at: datetime


StatementList = list[StatementResponse]

__all__ = [
    "StatementCreate",
    "StatementUpdate",
    "StatementResponse",
    "StatementList",
    "StatementStatus",
]
