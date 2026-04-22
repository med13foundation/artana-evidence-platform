"""
Kernel dictionary domain entities (Layer 1 rules).

These are domain-level models used by application services and repositories.
They mirror the kernel dictionary tables but do not depend on SQLAlchemy.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from artana_evidence_db.common_types import JSONObject, JSONValue
from pydantic import BaseModel, ConfigDict, Field


class VariableSynonym(BaseModel):
    """Domain representation of a variable synonym row."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: int
    variable_id: str = Field(..., min_length=1, max_length=64)
    synonym: str = Field(..., min_length=1, max_length=255)
    source: str | None = Field(None, max_length=64)
    created_by: str = Field(default="seed", min_length=1, max_length=128)
    is_active: bool = True
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    superseded_by: str | None = Field(default=None, max_length=64)
    source_ref: str | None = Field(default=None, max_length=1024)
    review_status: Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"] = "ACTIVE"
    reviewed_by: str | None = Field(default=None, max_length=128)
    reviewed_at: datetime | None = None
    revocation_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class VariableDefinition(BaseModel):
    """Domain representation of a kernel variable definition."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: str = Field(..., min_length=1, max_length=64)
    canonical_name: str = Field(..., min_length=1, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=255)
    data_type: str = Field(..., min_length=1, max_length=32)
    preferred_unit: str | None = Field(None, max_length=64)
    constraints: JSONObject = Field(default_factory=dict)
    domain_context: str = Field(default="general", min_length=1, max_length=64)
    sensitivity: str = Field(default="INTERNAL", min_length=1, max_length=32)
    description: str | None = None
    description_embedding: list[float] | None = None
    embedded_at: datetime | None = None
    embedding_model: str | None = Field(default=None, max_length=64)
    created_by: str = Field(default="seed", min_length=1, max_length=128)
    is_active: bool = True
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    superseded_by: str | None = Field(default=None, max_length=64)
    source_ref: str | None = Field(default=None, max_length=1024)
    review_status: Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"] = "ACTIVE"
    reviewed_by: str | None = Field(default=None, max_length=128)
    reviewed_at: datetime | None = None
    revocation_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class DictionaryDataType(BaseModel):
    """Domain representation of first-class dictionary data types."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: str = Field(..., min_length=1, max_length=32)
    display_name: str = Field(..., min_length=1, max_length=64)
    python_type_hint: str = Field(..., min_length=1, max_length=64)
    description: str | None = None
    constraint_schema: JSONObject = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class DictionaryDomainContext(BaseModel):
    """Domain representation of dictionary domain contexts."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    is_active: bool = True
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    superseded_by: str | None = Field(default=None, max_length=64)
    created_at: datetime
    updated_at: datetime


class DictionarySensitivityLevel(BaseModel):
    """Domain representation of dictionary sensitivity levels."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: str = Field(..., min_length=1, max_length=32)
    display_name: str = Field(..., min_length=1, max_length=64)
    description: str | None = None
    is_active: bool = True
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    superseded_by: str | None = Field(default=None, max_length=64)
    created_at: datetime
    updated_at: datetime


class DictionaryEntityType(BaseModel):
    """Domain representation of first-class entity types."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(..., min_length=1)
    domain_context: str = Field(..., min_length=1, max_length=64)
    external_ontology_ref: str | None = Field(default=None, max_length=255)
    expected_properties: JSONObject = Field(default_factory=dict)
    description_embedding: list[float] | None = None
    embedded_at: datetime | None = None
    embedding_model: str | None = Field(default=None, max_length=64)
    created_by: str = Field(default="seed", min_length=1, max_length=128)
    is_active: bool = True
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    superseded_by: str | None = Field(default=None, max_length=64)
    source_ref: str | None = Field(default=None, max_length=1024)
    review_status: Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"] = "ACTIVE"
    reviewed_by: str | None = Field(default=None, max_length=128)
    reviewed_at: datetime | None = None
    revocation_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class DictionaryRelationType(BaseModel):
    """Domain representation of first-class relation types."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(..., min_length=1)
    domain_context: str = Field(..., min_length=1, max_length=64)
    is_directional: bool = True
    inverse_label: str | None = Field(default=None, max_length=128)
    description_embedding: list[float] | None = None
    embedded_at: datetime | None = None
    embedding_model: str | None = Field(default=None, max_length=64)
    created_by: str = Field(default="seed", min_length=1, max_length=128)
    is_active: bool = True
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    superseded_by: str | None = Field(default=None, max_length=64)
    source_ref: str | None = Field(default=None, max_length=1024)
    review_status: Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"] = "ACTIVE"
    reviewed_by: str | None = Field(default=None, max_length=128)
    reviewed_at: datetime | None = None
    revocation_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class DictionaryRelationSynonym(BaseModel):
    """Domain representation of a relation-type synonym row."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: int
    relation_type: str = Field(..., min_length=1, max_length=64)
    synonym: str = Field(..., min_length=1, max_length=64)
    source: str | None = Field(default=None, max_length=64)
    created_by: str = Field(default="seed", min_length=1, max_length=128)
    is_active: bool = True
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    superseded_by: str | None = Field(default=None, max_length=64)
    source_ref: str | None = Field(default=None, max_length=1024)
    review_status: Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"] = "ACTIVE"
    reviewed_by: str | None = Field(default=None, max_length=128)
    reviewed_at: datetime | None = None
    revocation_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class DictionarySearchResult(BaseModel):
    """Unified dictionary search result across all semantic dimensions."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    dimension: Literal["variables", "entity_types", "relation_types", "constraints"]
    entry_id: str = Field(..., min_length=1, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    domain_context: str | None = Field(default=None, max_length=64)
    match_method: Literal["exact", "synonym", "fuzzy", "vector"]
    similarity_score: float = Field(ge=0.0, le=1.0)
    metadata: JSONObject = Field(default_factory=dict)


class DictionaryChangelog(BaseModel):
    """Domain representation of a dictionary changelog entry."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: int
    table_name: str = Field(..., min_length=1, max_length=64)
    record_id: str = Field(..., min_length=1, max_length=128)
    action: str = Field(..., min_length=1, max_length=32)
    before_snapshot: JSONObject | None = None
    after_snapshot: JSONObject | None = None
    changed_by: str | None = Field(default=None, max_length=128)
    source_ref: str | None = Field(default=None, max_length=1024)
    created_at: datetime
    updated_at: datetime


class ValueSet(BaseModel):
    """Domain representation of a value set for a CODED variable."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: str = Field(..., min_length=1, max_length=64)
    variable_id: str = Field(..., min_length=1, max_length=64)
    variable_data_type: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    external_ref: str | None = Field(default=None, max_length=255)
    is_extensible: bool = False
    created_by: str = Field(default="seed", min_length=1, max_length=128)
    source_ref: str | None = Field(default=None, max_length=1024)
    review_status: Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"] = "ACTIVE"
    reviewed_by: str | None = Field(default=None, max_length=128)
    reviewed_at: datetime | None = None
    revocation_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class ValueSetItem(BaseModel):
    """Domain representation of a value set item (canonical code)."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: int
    value_set_id: str = Field(..., min_length=1, max_length=64)
    code: str = Field(..., min_length=1, max_length=128)
    display_label: str = Field(..., min_length=1, max_length=255)
    synonyms: list[str] = Field(default_factory=list)
    external_ref: str | None = Field(default=None, max_length=255)
    sort_order: int = 0
    is_active: bool = True
    created_by: str = Field(default="seed", min_length=1, max_length=128)
    source_ref: str | None = Field(default=None, max_length=1024)
    review_status: Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"] = "ACTIVE"
    reviewed_by: str | None = Field(default=None, max_length=128)
    reviewed_at: datetime | None = None
    revocation_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class TransformRegistry(BaseModel):
    """Domain representation of a safe unit/format transformation."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: str = Field(..., min_length=1, max_length=64)
    input_unit: str = Field(..., min_length=1, max_length=64)
    output_unit: str = Field(..., min_length=1, max_length=64)
    category: Literal["UNIT_CONVERSION", "NORMALIZATION", "DERIVATION"] = (
        "UNIT_CONVERSION"
    )
    input_data_type: str | None = Field(default=None, max_length=32)
    output_data_type: str | None = Field(default=None, max_length=32)
    implementation_ref: str = Field(..., min_length=1, max_length=255)
    is_deterministic: bool = True
    is_production_allowed: bool = False
    test_input: JSONValue | None = None
    expected_output: JSONValue | None = None
    description: str | None = None
    status: str = Field(..., min_length=1, max_length=32)
    created_by: str = Field(default="seed", min_length=1, max_length=128)
    is_active: bool = True
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    superseded_by: str | None = Field(default=None, max_length=64)
    source_ref: str | None = Field(default=None, max_length=1024)
    review_status: Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"] = "ACTIVE"
    reviewed_by: str | None = Field(default=None, max_length=128)
    reviewed_at: datetime | None = None
    revocation_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class TransformVerificationResult(BaseModel):
    """Result of executing a transform against its verification fixture."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    transform_id: str = Field(..., min_length=1, max_length=64)
    passed: bool
    message: str = Field(..., min_length=1)
    actual_output: JSONValue | None = None
    expected_output: JSONValue | None = None
    checked_at: datetime


class EntityResolutionPolicy(BaseModel):
    """Domain representation of an entity deduplication policy."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    entity_type: str = Field(..., min_length=1, max_length=64)
    policy_strategy: str = Field(..., min_length=1, max_length=32)
    required_anchors: list[str] = Field(default_factory=list)
    auto_merge_threshold: float = Field(default=1.0, ge=0.0)
    created_by: str = Field(default="seed", min_length=1, max_length=128)
    is_active: bool = True
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    superseded_by: str | None = Field(default=None, max_length=64)
    source_ref: str | None = Field(default=None, max_length=1024)
    review_status: Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"] = "ACTIVE"
    reviewed_by: str | None = Field(default=None, max_length=128)
    reviewed_at: datetime | None = None
    revocation_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class RelationConstraint(BaseModel):
    """Domain representation of an allowed triple."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: int
    source_type: str = Field(..., min_length=1, max_length=64)
    relation_type: str = Field(..., min_length=1, max_length=64)
    target_type: str = Field(..., min_length=1, max_length=64)
    is_allowed: bool
    requires_evidence: bool
    profile: str = Field(default="ALLOWED", max_length=32)
    required_roles: list[str] = Field(default_factory=list)
    domain_context: str | None = Field(default=None, max_length=64)
    qualifier_constraints: dict[str, object] = Field(default_factory=dict)
    min_evidence_tier: str | None = Field(default=None, max_length=32)
    created_by: str = Field(default="seed", min_length=1, max_length=128)
    is_active: bool = True
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    superseded_by: str | None = Field(default=None, max_length=64)
    source_ref: str | None = Field(default=None, max_length=1024)
    review_status: Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"] = "ACTIVE"
    reviewed_by: str | None = Field(default=None, max_length=128)
    reviewed_at: datetime | None = None
    revocation_reason: str | None = None
    created_at: datetime
    updated_at: datetime


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
    "CHANGES_REQUESTED",
    "APPROVED",
    "REJECTED",
    "MERGED",
]


class DictionaryProposal(BaseModel):
    """Domain representation of a governed dictionary change proposal."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: str = Field(..., min_length=1, max_length=36)
    proposal_type: DictionaryProposalType
    status: DictionaryProposalStatus
    entity_type: str | None = Field(default=None, max_length=64)
    source_type: str | None = Field(default=None, max_length=64)
    relation_type: str | None = Field(default=None, max_length=64)
    target_type: str | None = Field(default=None, max_length=64)
    value_set_id: str | None = Field(default=None, max_length=64)
    variable_id: str | None = Field(default=None, max_length=64)
    canonical_name: str | None = Field(default=None, max_length=128)
    data_type: str | None = Field(default=None, max_length=32)
    preferred_unit: str | None = Field(default=None, max_length=64)
    constraints: JSONObject = Field(default_factory=dict)
    sensitivity: str | None = Field(default=None, max_length=32)
    code: str | None = Field(default=None, max_length=128)
    synonym: str | None = Field(default=None, max_length=64)
    source: str | None = Field(default=None, max_length=64)
    display_name: str | None = Field(default=None, max_length=128)
    description: str | None = None
    name: str | None = Field(default=None, max_length=128)
    display_label: str | None = Field(default=None, max_length=255)
    domain_context: str | None = Field(default=None, max_length=64)
    external_ontology_ref: str | None = Field(default=None, max_length=255)
    external_ref: str | None = Field(default=None, max_length=255)
    expected_properties: JSONObject = Field(default_factory=dict)
    synonyms: list[str] = Field(default_factory=list)
    is_directional: bool | None = None
    inverse_label: str | None = Field(default=None, max_length=128)
    is_extensible: bool | None = None
    sort_order: int | None = None
    is_active_value: bool | None = None
    is_allowed: bool | None = None
    requires_evidence: bool | None = None
    profile: str | None = Field(default=None, max_length=32)
    rationale: str = Field(..., min_length=1)
    evidence_payload: JSONObject = Field(default_factory=dict)
    proposed_by: str = Field(..., min_length=1, max_length=128)
    reviewed_by: str | None = Field(default=None, max_length=128)
    reviewed_at: datetime | None = None
    decision_reason: str | None = None
    merge_target_type: str | None = Field(default=None, max_length=64)
    merge_target_id: str | None = Field(default=None, max_length=128)
    applied_domain_context_id: str | None = Field(default=None, max_length=64)
    applied_entity_type_id: str | None = Field(default=None, max_length=64)
    applied_variable_id: str | None = Field(default=None, max_length=64)
    applied_relation_type_id: str | None = Field(default=None, max_length=64)
    applied_relation_synonym_id: int | None = None
    applied_value_set_id: str | None = Field(default=None, max_length=64)
    applied_value_set_item_id: int | None = None
    applied_constraint_id: int | None = None
    source_ref: str | None = Field(default=None, max_length=1024)
    created_at: datetime
    updated_at: datetime


__all__ = [
    "DictionaryChangelog",
    "DictionaryDataType",
    "DictionaryDomainContext",
    "DictionaryEntityType",
    "DictionaryProposal",
    "DictionaryProposalStatus",
    "DictionaryProposalType",
    "DictionaryRelationSynonym",
    "DictionaryRelationType",
    "DictionarySearchResult",
    "DictionarySensitivityLevel",
    "EntityResolutionPolicy",
    "RelationConstraint",
    "TransformRegistry",
    "TransformVerificationResult",
    "ValueSet",
    "ValueSetItem",
    "VariableDefinition",
    "VariableSynonym",
]
