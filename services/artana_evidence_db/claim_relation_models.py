"""Service-local claim-relation domain entities."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from artana_evidence_db.common_types import JSONObject
from pydantic import BaseModel, ConfigDict, Field, model_validator

ClaimRelationType = Literal[
    "SUPPORTS",
    "CONTRADICTS",
    "REFINES",
    "CAUSES",
    "UPSTREAM_OF",
    "DOWNSTREAM_OF",
    "SAME_AS",
    "GENERALIZES",
    "INSTANCE_OF",
]
ClaimRelationReviewStatus = Literal["PROPOSED", "ACCEPTED", "REJECTED"]


class KernelClaimRelation(BaseModel):
    """One directed relation between two relation claims."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    research_space_id: UUID
    source_claim_id: UUID
    target_claim_id: UUID
    relation_type: ClaimRelationType
    agent_run_id: str | None = Field(default=None, max_length=255)
    source_document_id: UUID | None = None
    source_document_ref: str | None = Field(default=None, max_length=512)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    review_status: ClaimRelationReviewStatus = "PROPOSED"
    evidence_summary: str | None = None
    metadata_payload: JSONObject = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def validate_no_self_loop(self) -> KernelClaimRelation:
        """Disallow self-loop claim relations in the domain layer."""
        if self.source_claim_id != self.target_claim_id:
            return self
        msg = "Claim relation source_claim_id and target_claim_id must be different"
        raise ValueError(msg)


__all__ = [
    "ClaimRelationReviewStatus",
    "ClaimRelationType",
    "KernelClaimRelation",
]
