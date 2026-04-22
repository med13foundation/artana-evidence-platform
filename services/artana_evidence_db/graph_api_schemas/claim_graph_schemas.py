# ruff: noqa: TC001,TC003
"""Schemas for claim participants and claim-relations routes."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.kernel_domain_models import (
    KernelClaimParticipant,
    KernelClaimRelation,
)
from pydantic import BaseModel, ConfigDict, Field

from artana_evidence_db.fact_assessment import (
    FactAssessment,
    assessment_confidence,
)


def _to_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


class ClaimParticipantResponse(BaseModel):
    """Response model for one claim participant row."""

    model_config = ConfigDict(strict=True, extra="forbid")

    id: UUID
    claim_id: UUID
    research_space_id: UUID
    label: str | None
    entity_id: UUID | None
    role: str
    position: int | None
    qualifiers: JSONObject
    created_at: datetime

    @classmethod
    def from_model(cls, model: KernelClaimParticipant) -> ClaimParticipantResponse:
        return cls(
            id=_to_uuid(model.id),
            claim_id=_to_uuid(model.claim_id),
            research_space_id=_to_uuid(model.research_space_id),
            label=model.label,
            entity_id=(
                _to_uuid(model.entity_id) if model.entity_id is not None else None
            ),
            role=str(model.role),
            position=model.position,
            qualifiers=dict(model.qualifiers),
            created_at=model.created_at,
        )


class ClaimParticipantListResponse(BaseModel):
    """List response for participants on one claim."""

    model_config = ConfigDict(strict=True)

    claim_id: UUID
    participants: list[ClaimParticipantResponse]
    total: int


class ClaimParticipantBackfillRequest(BaseModel):
    """Request payload for participant backfill."""

    model_config = ConfigDict(strict=True)

    dry_run: bool = True
    limit: int = Field(default=500, ge=1, le=5000)
    offset: int = Field(default=0, ge=0)


class ClaimParticipantBackfillResponse(BaseModel):
    """Backfill summary response."""

    model_config = ConfigDict(strict=True)

    operation_run_id: UUID = Field(..., strict=False)
    scanned_claims: int
    created_participants: int
    skipped_existing: int
    unresolved_endpoints: int
    dry_run: bool


class ClaimParticipantCoverageResponse(BaseModel):
    """Coverage summary response for claim participants."""

    model_config = ConfigDict(strict=True)

    total_claims: int
    claims_with_any_participants: int
    claims_with_subject: int
    claims_with_object: int
    unresolved_subject_endpoints: int
    unresolved_object_endpoints: int
    unresolved_endpoint_rate: float


class ClaimRelationCreateRequest(BaseModel):
    """Request payload for creating a claim relation edge."""

    model_config = ConfigDict(strict=True)

    source_claim_id: UUID = Field(..., strict=False)
    target_claim_id: UUID = Field(..., strict=False)
    relation_type: str = Field(..., min_length=1, max_length=32)
    agent_run_id: str | None = Field(default=None, min_length=1, max_length=255)
    source_document_id: UUID | None = Field(default=None, strict=False)
    source_document_ref: str | None = Field(default=None, max_length=512)
    assessment: FactAssessment
    review_status: str = Field(default="PROPOSED", min_length=1, max_length=32)
    evidence_summary: str | None = Field(default=None, max_length=8000)
    metadata: JSONObject = Field(default_factory=dict)

    @property
    def derived_confidence(self) -> float:
        return assessment_confidence(self.assessment)


class ClaimRelationReviewUpdateRequest(BaseModel):
    """Request payload for claim relation review-status updates."""

    model_config = ConfigDict(strict=True)

    review_status: str = Field(..., min_length=1, max_length=32)


class ClaimRelationResponse(BaseModel):
    """Response model for one claim-relation edge."""

    model_config = ConfigDict(strict=True)

    id: UUID
    research_space_id: UUID
    source_claim_id: UUID
    target_claim_id: UUID
    relation_type: str
    agent_run_id: str | None
    source_document_id: UUID | None = None
    source_document_ref: str | None = None
    confidence: float
    review_status: str
    evidence_summary: str | None
    metadata: JSONObject
    created_at: datetime

    @classmethod
    def from_model(cls, model: KernelClaimRelation) -> ClaimRelationResponse:
        return cls(
            id=_to_uuid(model.id),
            research_space_id=_to_uuid(model.research_space_id),
            source_claim_id=_to_uuid(model.source_claim_id),
            target_claim_id=_to_uuid(model.target_claim_id),
            relation_type=str(model.relation_type),
            agent_run_id=model.agent_run_id,
            source_document_id=(
                _to_uuid(model.source_document_id)
                if model.source_document_id is not None
                else None
            ),
            source_document_ref=model.source_document_ref,
            confidence=float(model.confidence),
            review_status=str(model.review_status),
            evidence_summary=model.evidence_summary,
            metadata=dict(model.metadata_payload),
            created_at=model.created_at,
        )


class ClaimRelationListResponse(BaseModel):
    """List response for claim relation edges."""

    model_config = ConfigDict(strict=True)

    claim_relations: list[ClaimRelationResponse]
    total: int
    offset: int
    limit: int


__all__ = [
    "ClaimParticipantBackfillRequest",
    "ClaimParticipantBackfillResponse",
    "ClaimParticipantCoverageResponse",
    "ClaimParticipantListResponse",
    "ClaimParticipantResponse",
    "ClaimRelationCreateRequest",
    "ClaimRelationListResponse",
    "ClaimRelationResponse",
    "ClaimRelationReviewUpdateRequest",
]
