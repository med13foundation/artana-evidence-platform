"""Service-local relation-claim domain entities."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from artana_evidence_db.common_types import JSONObject
from pydantic import BaseModel, ConfigDict, Field

RelationClaimValidationState = Literal[
    "ALLOWED",
    "FORBIDDEN",
    "UNDEFINED",
    "INVALID_COMPONENTS",
    "ENDPOINT_UNRESOLVED",
    "SELF_LOOP",
]
RelationClaimPersistability = Literal["PERSISTABLE", "NON_PERSISTABLE"]
RelationClaimStatus = Literal[
    "OPEN", "NEEDS_MAPPING", "REVIEW_REQUIRED", "REJECTED", "RESOLVED"
]
RelationClaimPolarity = Literal["SUPPORT", "REFUTE", "UNCERTAIN", "HYPOTHESIS"]
RelationClaimAssertionClass = Literal["SOURCE_BACKED", "CURATED", "COMPUTATIONAL"]


class KernelRelationClaim(BaseModel):
    """One extracted relation candidate captured for curation."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    research_space_id: UUID
    source_document_id: UUID | None = None
    source_document_ref: str | None = Field(default=None, max_length=512)
    source_ref: str | None = Field(default=None, max_length=1024)
    agent_run_id: str | None = Field(default=None, max_length=255)
    source_type: str = Field(..., min_length=1, max_length=64)
    relation_type: str = Field(..., min_length=1, max_length=64)
    target_type: str = Field(..., min_length=1, max_length=64)
    source_label: str | None = Field(default=None, max_length=512)
    target_label: str | None = Field(default=None, max_length=512)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    validation_state: RelationClaimValidationState
    validation_reason: str | None = None
    persistability: RelationClaimPersistability
    assertion_class: RelationClaimAssertionClass = "SOURCE_BACKED"
    claim_status: RelationClaimStatus = "OPEN"
    polarity: RelationClaimPolarity = "UNCERTAIN"
    claim_text: str | None = None
    claim_section: str | None = Field(default=None, max_length=64)
    linked_relation_id: UUID | None = None
    metadata_payload: JSONObject = Field(default_factory=dict)
    triaged_by: UUID | None = None
    triaged_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class KernelRelationConflictSummary(BaseModel):
    """Conflict summary for one canonical relation with mixed claim polarity."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    relation_id: UUID
    support_count: int = Field(default=0, ge=0)
    refute_count: int = Field(default=0, ge=0)
    support_claim_ids: tuple[UUID, ...] = ()
    refute_claim_ids: tuple[UUID, ...] = ()
    support_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    refute_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    relation_type: str | None = None
    source_label: str | None = None
    target_label: str | None = None


__all__ = [
    "KernelRelationConflictSummary",
    "KernelRelationClaim",
    "RelationClaimPersistability",
    "RelationClaimPolarity",
    "RelationClaimStatus",
    "RelationClaimValidationState",
]
