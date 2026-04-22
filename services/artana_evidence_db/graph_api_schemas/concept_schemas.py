# ruff: noqa: TC001,TC003
"""Typed schemas for Concept Manager admin routes."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.kernel_domain_models import (
    ConceptAlias,
    ConceptDecision,
    ConceptLink,
    ConceptMember,
    ConceptPolicy,
    ConceptSet,
)
from pydantic import BaseModel, ConfigDict, Field


class ConceptSetCreateRequest(BaseModel):
    """Request payload for creating a concept set."""

    model_config = ConfigDict(strict=False)

    research_space_id: UUID
    name: str = Field(..., min_length=1, max_length=128)
    slug: str = Field(..., min_length=1, max_length=128)
    domain_context: str = Field(..., min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=4000)
    source_ref: str | None = Field(default=None, max_length=1024)


class ConceptSetResponse(BaseModel):
    """Serialized concept set response."""

    model_config = ConfigDict(strict=True)

    id: str
    research_space_id: str
    name: str
    slug: str
    domain_context: str
    description: str | None
    review_status: Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"]
    is_active: bool
    created_by: str
    source_ref: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: ConceptSet) -> ConceptSetResponse:
        return cls.model_validate(model.model_dump())


class ConceptSetListResponse(BaseModel):
    """List response for concept sets."""

    model_config = ConfigDict(strict=True)

    concept_sets: list[ConceptSetResponse]
    total: int = Field(..., ge=0)


class ConceptMemberCreateRequest(BaseModel):
    """Request payload for creating one concept member."""

    model_config = ConfigDict(strict=False)

    concept_set_id: UUID
    research_space_id: UUID
    domain_context: str = Field(..., min_length=1, max_length=64)
    canonical_label: str = Field(..., min_length=1, max_length=255)
    normalized_label: str = Field(..., min_length=1, max_length=255)
    sense_key: str = Field(default="", max_length=128)
    dictionary_dimension: str | None = Field(default=None, max_length=32)
    dictionary_entry_id: str | None = Field(default=None, max_length=128)
    is_provisional: bool = False
    metadata_payload: JSONObject = Field(default_factory=dict)
    source_ref: str | None = Field(default=None, max_length=1024)


class ConceptMemberResponse(BaseModel):
    """Serialized concept member response."""

    model_config = ConfigDict(strict=True)

    id: str
    concept_set_id: str
    research_space_id: str
    domain_context: str
    canonical_label: str
    normalized_label: str
    sense_key: str
    dictionary_dimension: str | None
    dictionary_entry_id: str | None
    is_provisional: bool
    metadata_payload: JSONObject
    review_status: Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"]
    is_active: bool
    created_by: str
    source_ref: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: ConceptMember) -> ConceptMemberResponse:
        return cls.model_validate(model.model_dump())


class ConceptMemberListResponse(BaseModel):
    """List response for concept members."""

    model_config = ConfigDict(strict=True)

    concept_members: list[ConceptMemberResponse]
    total: int = Field(..., ge=0)


class ConceptAliasCreateRequest(BaseModel):
    """Request payload for creating one concept alias."""

    model_config = ConfigDict(strict=False)

    concept_member_id: UUID
    research_space_id: UUID
    domain_context: str = Field(..., min_length=1, max_length=64)
    alias_label: str = Field(..., min_length=1, max_length=255)
    alias_normalized: str = Field(..., min_length=1, max_length=255)
    source: str | None = Field(default=None, max_length=64)
    source_ref: str | None = Field(default=None, max_length=1024)


class ConceptAliasResponse(BaseModel):
    """Serialized concept alias response."""

    model_config = ConfigDict(strict=True)

    id: int
    concept_member_id: str
    research_space_id: str
    domain_context: str
    alias_label: str
    alias_normalized: str
    source: str | None
    review_status: Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"]
    is_active: bool
    created_by: str
    source_ref: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: ConceptAlias) -> ConceptAliasResponse:
        return cls.model_validate(model.model_dump())


class ConceptAliasListResponse(BaseModel):
    """List response for concept aliases."""

    model_config = ConfigDict(strict=True)

    concept_aliases: list[ConceptAliasResponse]
    total: int = Field(..., ge=0)


class ConceptPolicyUpsertRequest(BaseModel):
    """Request payload for upserting active concept policy."""

    model_config = ConfigDict(strict=False)

    research_space_id: UUID
    mode: Literal["PRECISION", "BALANCED", "DISCOVERY"]
    minimum_edge_confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    minimum_distinct_documents: int = Field(default=1, ge=1)
    allow_generic_relations: bool = True
    max_edges_per_document: int | None = Field(default=None, ge=1)
    policy_payload: JSONObject = Field(default_factory=dict)
    source_ref: str | None = Field(default=None, max_length=1024)


class ConceptPolicyResponse(BaseModel):
    """Serialized concept policy response."""

    model_config = ConfigDict(strict=True)

    id: str
    research_space_id: str
    profile_name: str
    mode: Literal["PRECISION", "BALANCED", "DISCOVERY"]
    minimum_edge_confidence: float
    minimum_distinct_documents: int
    allow_generic_relations: bool
    max_edges_per_document: int | None
    policy_payload: JSONObject
    is_active: bool
    created_by: str
    source_ref: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: ConceptPolicy) -> ConceptPolicyResponse:
        return cls.model_validate(model.model_dump())


class ConceptDecisionProposeRequest(BaseModel):
    """Request payload for proposing a concept decision."""

    model_config = ConfigDict(strict=False)

    research_space_id: UUID
    decision_type: Literal[
        "CREATE",
        "MAP",
        "MERGE",
        "SPLIT",
        "LINK",
        "PROMOTE",
        "DEMOTE",
    ]
    decision_payload: JSONObject = Field(default_factory=dict)
    evidence_payload: JSONObject = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    rationale: str | None = Field(default=None, max_length=4000)
    concept_set_id: UUID | None = None
    concept_member_id: UUID | None = None
    concept_link_id: UUID | None = None


class ConceptDecisionStatusRequest(BaseModel):
    """Request payload for manual decision status update."""

    model_config = ConfigDict(strict=True)

    decision_status: Literal[
        "PROPOSED",
        "NEEDS_REVIEW",
        "APPROVED",
        "REJECTED",
        "APPLIED",
    ]


class ConceptDecisionResponse(BaseModel):
    """Serialized concept decision response."""

    model_config = ConfigDict(strict=True)

    id: str
    research_space_id: str
    concept_set_id: str | None
    concept_member_id: str | None
    concept_link_id: str | None
    decision_type: Literal[
        "CREATE",
        "MAP",
        "MERGE",
        "SPLIT",
        "LINK",
        "PROMOTE",
        "DEMOTE",
    ]
    decision_status: Literal[
        "PROPOSED",
        "NEEDS_REVIEW",
        "APPROVED",
        "REJECTED",
        "APPLIED",
    ]
    proposed_by: str
    decided_by: str | None
    confidence: float | None
    rationale: str | None
    evidence_payload: JSONObject
    decision_payload: JSONObject
    harness_outcome: Literal["PASS", "FAIL", "NEEDS_REVIEW"] | None
    decided_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: ConceptDecision) -> ConceptDecisionResponse:
        return cls.model_validate(model.model_dump())


class ConceptDecisionListResponse(BaseModel):
    """List response for concept decisions."""

    model_config = ConfigDict(strict=True)

    concept_decisions: list[ConceptDecisionResponse]
    total: int = Field(..., ge=0)


class ConceptLinkResponse(BaseModel):
    """Serialized concept link response."""

    model_config = ConfigDict(strict=True)

    id: str
    research_space_id: str
    source_member_id: str
    target_member_id: str
    link_type: str
    confidence: float
    metadata_payload: JSONObject
    review_status: Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"]
    is_active: bool
    created_by: str
    source_ref: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: ConceptLink) -> ConceptLinkResponse:
        return cls.model_validate(model.model_dump())
