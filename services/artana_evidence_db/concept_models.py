"""Service-local concept-governance domain entities."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from artana_evidence_db.common_types import JSONObject
from pydantic import BaseModel, ConfigDict, Field

ConceptReviewStatus = Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"]
ConceptPolicyMode = Literal["PRECISION", "BALANCED", "DISCOVERY"]
ConceptDecisionType = Literal[
    "CREATE",
    "MAP",
    "MERGE",
    "SPLIT",
    "LINK",
    "PROMOTE",
    "DEMOTE",
]
ConceptDecisionStatus = Literal[
    "PROPOSED",
    "NEEDS_REVIEW",
    "APPROVED",
    "REJECTED",
    "APPLIED",
]
ConceptHarnessOutcome = Literal["PASS", "FAIL", "NEEDS_REVIEW"]


class ConceptSet(BaseModel):
    """Research-space scoped concept set."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: str = Field(..., min_length=1)
    research_space_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1, max_length=128)
    slug: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    domain_context: str = Field(..., min_length=1, max_length=64)
    created_by: str = Field(default="seed", min_length=1, max_length=128)
    source_ref: str | None = Field(default=None, max_length=1024)
    review_status: ConceptReviewStatus = "ACTIVE"
    reviewed_by: str | None = Field(default=None, max_length=128)
    reviewed_at: datetime | None = None
    revocation_reason: str | None = None
    is_active: bool = True
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    superseded_by: str | None = None
    created_at: datetime
    updated_at: datetime


class ConceptMember(BaseModel):
    """Concept member in one set (canonical or provisional)."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: str = Field(..., min_length=1)
    concept_set_id: str = Field(..., min_length=1)
    research_space_id: str = Field(..., min_length=1)
    domain_context: str = Field(..., min_length=1, max_length=64)
    dictionary_dimension: str | None = Field(default=None, max_length=32)
    dictionary_entry_id: str | None = Field(default=None, max_length=128)
    canonical_label: str = Field(..., min_length=1, max_length=255)
    normalized_label: str = Field(..., min_length=1, max_length=255)
    sense_key: str = Field(default="", max_length=128)
    is_provisional: bool = False
    metadata_payload: JSONObject = Field(default_factory=dict)
    created_by: str = Field(default="seed", min_length=1, max_length=128)
    source_ref: str | None = Field(default=None, max_length=1024)
    review_status: ConceptReviewStatus = "ACTIVE"
    reviewed_by: str | None = Field(default=None, max_length=128)
    reviewed_at: datetime | None = None
    revocation_reason: str | None = None
    is_active: bool = True
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    superseded_by: str | None = None
    created_at: datetime
    updated_at: datetime


class ConceptAlias(BaseModel):
    """Scoped alias for one concept member."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: int
    concept_member_id: str = Field(..., min_length=1)
    research_space_id: str = Field(..., min_length=1)
    domain_context: str = Field(..., min_length=1, max_length=64)
    alias_label: str = Field(..., min_length=1, max_length=255)
    alias_normalized: str = Field(..., min_length=1, max_length=255)
    source: str | None = Field(default=None, max_length=64)
    created_by: str = Field(default="seed", min_length=1, max_length=128)
    source_ref: str | None = Field(default=None, max_length=1024)
    review_status: ConceptReviewStatus = "ACTIVE"
    reviewed_by: str | None = Field(default=None, max_length=128)
    reviewed_at: datetime | None = None
    revocation_reason: str | None = None
    is_active: bool = True
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    superseded_by: int | None = None
    created_at: datetime
    updated_at: datetime


class ConceptLink(BaseModel):
    """Typed link between two concept members."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: str = Field(..., min_length=1)
    research_space_id: str = Field(..., min_length=1)
    source_member_id: str = Field(..., min_length=1)
    target_member_id: str = Field(..., min_length=1)
    link_type: str = Field(..., min_length=1, max_length=64)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata_payload: JSONObject = Field(default_factory=dict)
    created_by: str = Field(default="seed", min_length=1, max_length=128)
    source_ref: str | None = Field(default=None, max_length=1024)
    review_status: ConceptReviewStatus = "ACTIVE"
    reviewed_by: str | None = Field(default=None, max_length=128)
    reviewed_at: datetime | None = None
    revocation_reason: str | None = None
    is_active: bool = True
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    superseded_by: str | None = None
    created_at: datetime
    updated_at: datetime


class ConceptPolicy(BaseModel):
    """Concept ranking/promotion policy for one research space."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: str = Field(..., min_length=1)
    research_space_id: str = Field(..., min_length=1)
    profile_name: str = Field(default="default", min_length=1, max_length=64)
    mode: ConceptPolicyMode = "BALANCED"
    minimum_edge_confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    minimum_distinct_documents: int = Field(default=1, ge=1)
    allow_generic_relations: bool = True
    max_edges_per_document: int | None = Field(default=None, ge=1)
    policy_payload: JSONObject = Field(default_factory=dict)
    created_by: str = Field(default="seed", min_length=1, max_length=128)
    source_ref: str | None = Field(default=None, max_length=1024)
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class ConceptDecision(BaseModel):
    """Decision ledger row for concept governance actions."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: str = Field(..., min_length=1)
    research_space_id: str = Field(..., min_length=1)
    concept_set_id: str | None = None
    concept_member_id: str | None = None
    concept_link_id: str | None = None
    decision_type: ConceptDecisionType
    decision_status: ConceptDecisionStatus
    proposed_by: str = Field(..., min_length=1, max_length=128)
    decided_by: str | None = Field(default=None, max_length=128)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    rationale: str | None = None
    evidence_payload: JSONObject = Field(default_factory=dict)
    decision_payload: JSONObject = Field(default_factory=dict)
    harness_outcome: ConceptHarnessOutcome | None = None
    decided_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ConceptHarnessCheck(BaseModel):
    """Single deterministic or AI harness check."""

    model_config = ConfigDict(frozen=True)

    check_id: str = Field(..., min_length=1, max_length=128)
    passed: bool
    detail: str | None = None


class ConceptHarnessResult(BaseModel):
    """Recorded outcome from one harness execution."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: str = Field(..., min_length=1)
    research_space_id: str = Field(..., min_length=1)
    decision_id: str | None = None
    harness_name: str = Field(..., min_length=1, max_length=64)
    harness_version: str | None = Field(default=None, max_length=32)
    run_id: str | None = Field(default=None, max_length=255)
    outcome: ConceptHarnessOutcome
    checks_payload: JSONObject = Field(default_factory=dict)
    errors_payload: list[str] = Field(default_factory=list)
    metadata_payload: JSONObject = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ConceptDecisionProposal(BaseModel):
    """Input payload evaluated by concept decision harness."""

    model_config = ConfigDict(frozen=True)

    research_space_id: str = Field(..., min_length=1)
    decision_type: ConceptDecisionType
    proposed_by: str = Field(..., min_length=1, max_length=128)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    rationale: str | None = None
    decision_payload: JSONObject = Field(default_factory=dict)


class ConceptHarnessVerdict(BaseModel):
    """Normalized harness verdict consumed by service layer."""

    model_config = ConfigDict(frozen=True)

    outcome: ConceptHarnessOutcome
    rationale: str | None = None
    checks: list[ConceptHarnessCheck] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: JSONObject = Field(default_factory=dict)


__all__ = [
    "ConceptAlias",
    "ConceptDecision",
    "ConceptDecisionProposal",
    "ConceptDecisionStatus",
    "ConceptDecisionType",
    "ConceptHarnessCheck",
    "ConceptHarnessOutcome",
    "ConceptHarnessResult",
    "ConceptHarnessVerdict",
    "ConceptLink",
    "ConceptMember",
    "ConceptPolicy",
    "ConceptPolicyMode",
    "ConceptReviewStatus",
    "ConceptSet",
]
