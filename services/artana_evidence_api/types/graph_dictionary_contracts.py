"""Dictionary API contract models for the graph service boundary."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .common import JSONObject


class DictionaryEntityTypeResponse(BaseModel):
    """Typed dictionary entity-type response."""

    model_config = ConfigDict(strict=True)

    id: str
    display_name: str
    description: str
    domain_context: str
    external_ontology_ref: str | None = None
    expected_properties: JSONObject = Field(default_factory=dict)
    description_embedding: list[float] | None = None
    embedded_at: datetime | None = None
    embedding_model: str | None = None
    created_by: str
    is_active: bool
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    superseded_by: str | None = None
    source_ref: str | None = None
    review_status: str
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    revocation_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class DictionaryEntityTypeListResponse(BaseModel):
    """List response for typed dictionary entity types."""

    model_config = ConfigDict(strict=True)

    entity_types: list[DictionaryEntityTypeResponse]
    total: int


class DictionaryRelationTypeResponse(BaseModel):
    """Typed dictionary relation-type response."""

    model_config = ConfigDict(strict=True)

    id: str
    display_name: str
    description: str
    domain_context: str
    is_directional: bool
    inverse_label: str | None = None
    description_embedding: list[float] | None = None
    embedded_at: datetime | None = None
    embedding_model: str | None = None
    created_by: str
    is_active: bool
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    superseded_by: str | None = None
    source_ref: str | None = None
    review_status: str
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    revocation_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class DictionaryRelationTypeListResponse(BaseModel):
    """List response for typed dictionary relation types."""

    model_config = ConfigDict(strict=True)

    relation_types: list[DictionaryRelationTypeResponse]
    total: int


class DictionaryRelationSynonymResponse(BaseModel):
    """Typed dictionary relation-synonym response."""

    model_config = ConfigDict(strict=True)

    id: int
    relation_type: str
    synonym: str
    source: str | None = None
    created_by: str
    is_active: bool
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    superseded_by: str | None = None
    source_ref: str | None = None
    review_status: str
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    revocation_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class DictionaryRelationSynonymListResponse(BaseModel):
    """List response for typed dictionary relation synonyms."""

    model_config = ConfigDict(strict=True)

    relation_synonyms: list[DictionaryRelationSynonymResponse]
    total: int


class DictionarySearchResultResponse(BaseModel):
    """Typed dictionary search hit."""

    model_config = ConfigDict(strict=True)

    dimension: str
    entry_id: str
    display_name: str
    description: str | None = None
    domain_context: str | None = None
    match_method: str
    similarity_score: float
    metadata: JSONObject = Field(default_factory=dict)


class DictionarySearchListResponse(BaseModel):
    """List response for typed dictionary search hits."""

    model_config = ConfigDict(strict=True)

    results: list[DictionarySearchResultResponse]
    total: int


DictionaryProposalType = Literal[
    "DOMAIN_CONTEXT",
    "ENTITY_TYPE",
    "VARIABLE",
    "RELATION_TYPE",
    "RELATION_CONSTRAINT",
    "RELATION_SYNONYM",
    "VALUE_SET",
    "VALUE_SET_ITEM",
]
DictionaryProposalStatus = Literal[
    "SUBMITTED",
    "DUPLICATE",
    "CHANGES_REQUESTED",
    "APPROVED",
    "REJECTED",
    "MERGED",
]


class DictionaryProposalResponse(BaseModel):
    """Typed governed dictionary-proposal response."""

    model_config = ConfigDict(strict=True)

    id: str
    proposal_type: DictionaryProposalType
    status: DictionaryProposalStatus
    entity_type: str | None = None
    source_type: str | None = None
    relation_type: str | None = None
    target_type: str | None = None
    value_set_id: str | None = None
    variable_id: str | None = None
    canonical_name: str | None = None
    data_type: str | None = None
    preferred_unit: str | None = None
    constraints: JSONObject = Field(default_factory=dict)
    sensitivity: str | None = None
    code: str | None = None
    synonym: str | None = None
    source: str | None = None
    display_name: str | None = None
    name: str | None = None
    display_label: str | None = None
    description: str | None = None
    domain_context: str | None = None
    external_ontology_ref: str | None = None
    external_ref: str | None = None
    expected_properties: JSONObject = Field(default_factory=dict)
    synonyms: list[str] = Field(default_factory=list)
    is_directional: bool | None = None
    inverse_label: str | None = None
    is_extensible: bool | None = None
    sort_order: int | None = None
    is_active_value: bool | None = None
    is_allowed: bool | None = None
    requires_evidence: bool | None = None
    profile: str | None = None
    rationale: str
    evidence_payload: JSONObject = Field(default_factory=dict)
    proposed_by: str
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    decision_reason: str | None = None
    merge_target_type: str | None = None
    merge_target_id: str | None = None
    applied_domain_context_id: str | None = None
    applied_entity_type_id: str | None = None
    applied_variable_id: str | None = None
    applied_relation_type_id: str | None = None
    applied_constraint_id: int | None = None
    applied_relation_synonym_id: int | None = None
    applied_value_set_id: str | None = None
    applied_value_set_item_id: int | None = None
    source_ref: str | None = None
    created_at: datetime
    updated_at: datetime


class DictionaryEntityTypeProposalCreateRequest(BaseModel):
    """Governed entity-type proposal request."""

    model_config = ConfigDict(strict=False, extra="forbid")

    id: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(..., min_length=1)
    domain_context: str = Field(..., min_length=1, max_length=64)
    rationale: str = Field(..., min_length=1)
    evidence_payload: JSONObject = Field(default_factory=dict)
    external_ontology_ref: str | None = Field(default=None, max_length=255)
    expected_properties: JSONObject = Field(default_factory=dict)
    source_ref: str | None = Field(default=None, max_length=1024)


class DictionaryRelationTypeProposalCreateRequest(BaseModel):
    """Governed relation-type proposal request."""

    model_config = ConfigDict(strict=False, extra="forbid")

    id: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(..., min_length=1)
    domain_context: str = Field(..., min_length=1, max_length=64)
    rationale: str = Field(..., min_length=1)
    evidence_payload: JSONObject = Field(default_factory=dict)
    is_directional: bool = True
    inverse_label: str | None = Field(default=None, max_length=128)
    source_ref: str | None = Field(default=None, max_length=1024)


class DictionaryRelationConstraintProposalCreateRequest(BaseModel):
    """Governed relation-constraint proposal request."""

    model_config = ConfigDict(strict=False, extra="forbid")

    source_type: str = Field(..., min_length=1, max_length=64)
    relation_type: str = Field(..., min_length=1, max_length=64)
    target_type: str = Field(..., min_length=1, max_length=64)
    rationale: str = Field(..., min_length=1)
    evidence_payload: JSONObject = Field(default_factory=dict)
    is_allowed: bool = True
    requires_evidence: bool = True
    profile: Literal["EXPECTED", "ALLOWED", "REVIEW_ONLY", "FORBIDDEN"] = "ALLOWED"
    source_ref: str | None = Field(default=None, max_length=1024)

__all__ = [
    "DictionaryEntityTypeListResponse",
    "DictionaryEntityTypeProposalCreateRequest",
    "DictionaryEntityTypeResponse",
    "DictionaryProposalResponse",
    "DictionaryProposalStatus",
    "DictionaryProposalType",
    "DictionaryRelationConstraintProposalCreateRequest",
    "DictionaryRelationSynonymListResponse",
    "DictionaryRelationSynonymResponse",
    "DictionaryRelationTypeListResponse",
    "DictionaryRelationTypeProposalCreateRequest",
    "DictionaryRelationTypeResponse",
    "DictionarySearchListResponse",
    "DictionarySearchResultResponse",
]
