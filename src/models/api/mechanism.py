"""
Mechanism API schemas for Artana Resource Library.

Pydantic models for mechanism-related API requests and responses.
"""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .evidence import EvidenceLevel


class ProteinDomainCoordinate(BaseModel):
    """Serializable 3D coordinate for a protein domain."""

    model_config = ConfigDict(strict=True)

    x: float
    y: float
    z: float
    confidence: float | None = None


class ProteinDomainPayload(BaseModel):
    """Serializable protein domain payload."""

    model_config = ConfigDict(strict=True)

    name: str = Field(..., min_length=1, max_length=200)
    source_id: str | None = Field(None, max_length=50)
    start_residue: int = Field(..., ge=1)
    end_residue: int = Field(..., ge=1)
    domain_type: Literal[
        "structural",
        "functional",
        "binding_site",
        "disordered",
    ] = "structural"
    description: str | None = Field(None, max_length=500)
    coordinates: list[ProteinDomainCoordinate] | None = None


class MechanismLifecycleState(str, Enum):
    """Lifecycle state for canonical mechanisms."""

    DRAFT = "draft"
    REVIEWED = "reviewed"
    CANONICAL = "canonical"
    DEPRECATED = "deprecated"


class MechanismCreate(BaseModel):
    """Schema for creating new mechanisms."""

    model_config = ConfigDict(strict=True)

    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=2000)
    evidence_tier: EvidenceLevel = Field(
        ...,
        description="Evidence tier for this mechanism",
    )
    confidence_score: float = Field(
        default=0.5,
        ge=0,
        le=1,
        description="Confidence score between 0.0 and 1.0",
    )
    source: str = Field(default="manual_curation", max_length=100)
    lifecycle_state: MechanismLifecycleState = Field(
        default=MechanismLifecycleState.DRAFT,
        description="Lifecycle state for this mechanism",
    )
    protein_domains: list[ProteinDomainPayload] = Field(default_factory=list)
    phenotype_ids: list[int] = Field(..., min_length=1)


class MechanismUpdate(BaseModel):
    """Schema for updating existing mechanisms."""

    model_config = ConfigDict(strict=True)

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    evidence_tier: EvidenceLevel | None = None
    confidence_score: float | None = Field(None, ge=0, le=1)
    source: str | None = Field(None, max_length=100)
    lifecycle_state: MechanismLifecycleState | None = None
    protein_domains: list[ProteinDomainPayload] | None = None
    phenotype_ids: list[int] | None = None


class MechanismResponse(BaseModel):
    """Mechanism response schema for API endpoints."""

    model_config = ConfigDict(strict=True, from_attributes=True)

    id: int = Field(..., description="Database primary key")
    name: str
    description: str | None = None
    evidence_tier: EvidenceLevel
    confidence_score: float
    source: str
    lifecycle_state: MechanismLifecycleState
    protein_domains: list[ProteinDomainPayload]
    phenotype_ids: list[int]
    phenotype_count: int
    created_at: datetime
    updated_at: datetime


MechanismList = list[MechanismResponse]

__all__ = [
    "MechanismCreate",
    "MechanismUpdate",
    "MechanismResponse",
    "MechanismList",
    "ProteinDomainPayload",
    "ProteinDomainCoordinate",
    "MechanismLifecycleState",
]
