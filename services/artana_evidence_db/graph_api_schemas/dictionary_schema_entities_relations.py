# ruff: noqa: TC001,TC003
"""Entity/relation-focused schemas for dictionary admin routes."""

from __future__ import annotations

from datetime import datetime

from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.kernel_domain_models import (
    DictionaryEntityType,
    DictionaryRelationSynonym,
    DictionaryRelationType,
    EntityResolutionPolicy,
    RelationConstraint,
)
from pydantic import BaseModel, ConfigDict, Field

from .dictionary_schema_common import KernelReviewStatus, _coerce_embedding


class EntityResolutionPolicyResponse(BaseModel):
    """Response payload for an entity resolution policy."""

    model_config = ConfigDict(strict=True)

    entity_type: str
    policy_strategy: str
    required_anchors: list[str]
    auto_merge_threshold: float
    created_by: str
    is_active: bool
    valid_from: datetime | None
    valid_to: datetime | None
    superseded_by: str | None
    source_ref: str | None
    review_status: KernelReviewStatus
    reviewed_by: str | None
    reviewed_at: datetime | None
    revocation_reason: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(
        cls,
        model: EntityResolutionPolicy,
    ) -> EntityResolutionPolicyResponse:
        anchors = (
            model.required_anchors if isinstance(model.required_anchors, list) else []
        )
        return cls(
            entity_type=str(model.entity_type),
            policy_strategy=str(model.policy_strategy),
            required_anchors=[str(a) for a in anchors],
            auto_merge_threshold=float(model.auto_merge_threshold),
            created_by=str(model.created_by),
            is_active=bool(model.is_active),
            valid_from=model.valid_from,
            valid_to=model.valid_to,
            superseded_by=str(model.superseded_by) if model.superseded_by else None,
            source_ref=str(model.source_ref) if model.source_ref else None,
            review_status=KernelReviewStatus(str(model.review_status)),
            reviewed_by=str(model.reviewed_by) if model.reviewed_by else None,
            reviewed_at=model.reviewed_at,
            revocation_reason=(
                str(model.revocation_reason) if model.revocation_reason else None
            ),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class EntityResolutionPolicyListResponse(BaseModel):
    """List response payload for entity resolution policies."""

    model_config = ConfigDict(strict=True)

    policies: list[EntityResolutionPolicyResponse]
    total: int


class RelationConstraintResponse(BaseModel):
    """Response payload for a relation constraint (allowed triple)."""

    model_config = ConfigDict(strict=True)

    id: int
    source_type: str
    relation_type: str
    target_type: str
    is_allowed: bool
    requires_evidence: bool
    profile: str
    created_by: str
    is_active: bool
    valid_from: datetime | None
    valid_to: datetime | None
    superseded_by: str | None
    source_ref: str | None
    review_status: KernelReviewStatus
    reviewed_by: str | None
    reviewed_at: datetime | None
    revocation_reason: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: RelationConstraint) -> RelationConstraintResponse:
        return cls(
            id=int(model.id),
            source_type=str(model.source_type),
            relation_type=str(model.relation_type),
            target_type=str(model.target_type),
            is_allowed=bool(model.is_allowed),
            requires_evidence=bool(model.requires_evidence),
            profile=str(model.profile),
            created_by=str(model.created_by),
            is_active=bool(model.is_active),
            valid_from=model.valid_from,
            valid_to=model.valid_to,
            superseded_by=str(model.superseded_by) if model.superseded_by else None,
            source_ref=str(model.source_ref) if model.source_ref else None,
            review_status=KernelReviewStatus(str(model.review_status)),
            reviewed_by=str(model.reviewed_by) if model.reviewed_by else None,
            reviewed_at=model.reviewed_at,
            revocation_reason=(
                str(model.revocation_reason) if model.revocation_reason else None
            ),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class RelationConstraintListResponse(BaseModel):
    """List response payload for relation constraints."""

    model_config = ConfigDict(strict=True)

    constraints: list[RelationConstraintResponse]
    total: int


class DictionaryEntityTypeCreateRequest(BaseModel):
    """Request payload for creating a dictionary entity type."""

    model_config = ConfigDict(strict=False)

    id: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(..., min_length=1)
    domain_context: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description=(
            "Approved dictionary domain-context id. Discover valid values with "
            "`GET /v1/dictionary/domain-contexts`; fresh installs always include "
            "`general`."
        ),
    )
    external_ontology_ref: str | None = Field(default=None, max_length=255)
    expected_properties: JSONObject = Field(default_factory=dict)
    source_ref: str | None = Field(default=None, max_length=1024)


class DictionaryEntityTypeResponse(BaseModel):
    """Response payload for a dictionary entity type."""

    model_config = ConfigDict(strict=True)

    id: str
    display_name: str
    description: str
    domain_context: str
    external_ontology_ref: str | None
    expected_properties: JSONObject
    description_embedding: list[float] | None
    embedded_at: datetime | None
    embedding_model: str | None
    created_by: str
    is_active: bool
    valid_from: datetime | None
    valid_to: datetime | None
    superseded_by: str | None
    source_ref: str | None
    review_status: KernelReviewStatus
    reviewed_by: str | None
    reviewed_at: datetime | None
    revocation_reason: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: DictionaryEntityType) -> DictionaryEntityTypeResponse:
        return cls(
            id=str(model.id),
            display_name=str(model.display_name),
            description=str(model.description),
            domain_context=str(model.domain_context),
            external_ontology_ref=(
                str(model.external_ontology_ref)
                if model.external_ontology_ref
                else None
            ),
            expected_properties=(
                dict(model.expected_properties) if model.expected_properties else {}
            ),
            description_embedding=_coerce_embedding(model.description_embedding),
            embedded_at=model.embedded_at,
            embedding_model=(
                str(model.embedding_model) if model.embedding_model else None
            ),
            created_by=str(model.created_by),
            is_active=bool(model.is_active),
            valid_from=model.valid_from,
            valid_to=model.valid_to,
            superseded_by=str(model.superseded_by) if model.superseded_by else None,
            source_ref=str(model.source_ref) if model.source_ref else None,
            review_status=KernelReviewStatus(str(model.review_status)),
            reviewed_by=str(model.reviewed_by) if model.reviewed_by else None,
            reviewed_at=model.reviewed_at,
            revocation_reason=(
                str(model.revocation_reason) if model.revocation_reason else None
            ),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class DictionaryEntityTypeListResponse(BaseModel):
    """List response payload for dictionary entity types."""

    model_config = ConfigDict(strict=True)

    entity_types: list[DictionaryEntityTypeResponse]
    total: int


class DictionaryRelationTypeCreateRequest(BaseModel):
    """Request payload for creating a dictionary relation type."""

    model_config = ConfigDict(strict=False)

    id: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(..., min_length=1)
    domain_context: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description=(
            "Approved dictionary domain-context id. Discover valid values with "
            "`GET /v1/dictionary/domain-contexts`."
        ),
    )
    is_directional: bool = True
    inverse_label: str | None = Field(default=None, max_length=128)
    source_ref: str | None = Field(default=None, max_length=1024)


class DictionaryRelationTypeResponse(BaseModel):
    """Response payload for a dictionary relation type."""

    model_config = ConfigDict(strict=True)

    id: str
    display_name: str
    description: str
    domain_context: str
    is_directional: bool
    inverse_label: str | None
    description_embedding: list[float] | None
    embedded_at: datetime | None
    embedding_model: str | None
    created_by: str
    is_active: bool
    valid_from: datetime | None
    valid_to: datetime | None
    superseded_by: str | None
    source_ref: str | None
    review_status: KernelReviewStatus
    reviewed_by: str | None
    reviewed_at: datetime | None
    revocation_reason: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(
        cls,
        model: DictionaryRelationType,
    ) -> DictionaryRelationTypeResponse:
        return cls(
            id=str(model.id),
            display_name=str(model.display_name),
            description=str(model.description),
            domain_context=str(model.domain_context),
            is_directional=bool(model.is_directional),
            inverse_label=str(model.inverse_label) if model.inverse_label else None,
            description_embedding=_coerce_embedding(model.description_embedding),
            embedded_at=model.embedded_at,
            embedding_model=(
                str(model.embedding_model) if model.embedding_model else None
            ),
            created_by=str(model.created_by),
            is_active=bool(model.is_active),
            valid_from=model.valid_from,
            valid_to=model.valid_to,
            superseded_by=str(model.superseded_by) if model.superseded_by else None,
            source_ref=str(model.source_ref) if model.source_ref else None,
            review_status=KernelReviewStatus(str(model.review_status)),
            reviewed_by=str(model.reviewed_by) if model.reviewed_by else None,
            reviewed_at=model.reviewed_at,
            revocation_reason=(
                str(model.revocation_reason) if model.revocation_reason else None
            ),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class DictionaryRelationTypeListResponse(BaseModel):
    """List response payload for dictionary relation types."""

    model_config = ConfigDict(strict=True)

    relation_types: list[DictionaryRelationTypeResponse]
    total: int


class DictionaryRelationSynonymCreateRequest(BaseModel):
    """Request payload for creating a relation-type synonym."""

    model_config = ConfigDict(strict=False)

    relation_type_id: str = Field(..., min_length=1, max_length=64)
    synonym: str = Field(..., min_length=1, max_length=64)
    source: str | None = Field(default=None, max_length=64)
    source_ref: str | None = Field(default=None, max_length=1024)


class DictionaryRelationSynonymResponse(BaseModel):
    """Response payload for a relation-type synonym."""

    model_config = ConfigDict(strict=True)

    id: int
    relation_type: str
    synonym: str
    source: str | None
    created_by: str
    is_active: bool
    valid_from: datetime | None
    valid_to: datetime | None
    superseded_by: str | None
    source_ref: str | None
    review_status: KernelReviewStatus
    reviewed_by: str | None
    reviewed_at: datetime | None
    revocation_reason: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(
        cls,
        model: DictionaryRelationSynonym,
    ) -> DictionaryRelationSynonymResponse:
        return cls(
            id=int(model.id),
            relation_type=str(model.relation_type),
            synonym=str(model.synonym),
            source=str(model.source) if model.source else None,
            created_by=str(model.created_by),
            is_active=bool(model.is_active),
            valid_from=model.valid_from,
            valid_to=model.valid_to,
            superseded_by=str(model.superseded_by) if model.superseded_by else None,
            source_ref=str(model.source_ref) if model.source_ref else None,
            review_status=KernelReviewStatus(str(model.review_status)),
            reviewed_by=str(model.reviewed_by) if model.reviewed_by else None,
            reviewed_at=model.reviewed_at,
            revocation_reason=(
                str(model.revocation_reason) if model.revocation_reason else None
            ),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class DictionaryRelationSynonymListResponse(BaseModel):
    """List response payload for relation-type synonyms."""

    model_config = ConfigDict(strict=True)

    relation_synonyms: list[DictionaryRelationSynonymResponse]
    total: int


__all__ = [
    "DictionaryEntityTypeCreateRequest",
    "DictionaryEntityTypeListResponse",
    "DictionaryEntityTypeResponse",
    "DictionaryRelationSynonymCreateRequest",
    "DictionaryRelationSynonymListResponse",
    "DictionaryRelationSynonymResponse",
    "DictionaryRelationTypeCreateRequest",
    "DictionaryRelationTypeListResponse",
    "DictionaryRelationTypeResponse",
    "EntityResolutionPolicyListResponse",
    "EntityResolutionPolicyResponse",
    "RelationConstraintListResponse",
    "RelationConstraintResponse",
]
