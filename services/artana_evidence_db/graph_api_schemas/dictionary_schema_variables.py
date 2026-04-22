# ruff: noqa: TC001,TC003
"""Variable-focused schemas for dictionary admin routes."""

from __future__ import annotations

from datetime import datetime

from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.kernel_domain_models import VariableDefinition
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .dictionary_schema_common import (
    KernelDataType,
    KernelReviewStatus,
    KernelSensitivity,
    _coerce_embedding,
)


class VariableDefinitionCreateRequest(BaseModel):
    """Request payload for creating a dictionary variable."""

    model_config = ConfigDict(strict=False)

    id: str = Field(..., min_length=1, max_length=64, description="Variable ID")
    canonical_name: str = Field(..., min_length=1, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=255)
    data_type: KernelDataType
    domain_context: str = Field(default="general", min_length=1, max_length=64)
    sensitivity: KernelSensitivity = KernelSensitivity.INTERNAL
    preferred_unit: str | None = Field(None, max_length=64)
    constraints: JSONObject = Field(default_factory=dict)
    description: str | None = None
    source_ref: str | None = Field(
        default=None,
        max_length=1024,
        description="Optional source reference for provenance tracking",
    )


class VariableDefinitionResponse(BaseModel):
    """Response payload for a dictionary variable."""

    model_config = ConfigDict(strict=True)

    id: str
    canonical_name: str
    display_name: str
    data_type: KernelDataType
    preferred_unit: str | None
    constraints: JSONObject
    domain_context: str
    sensitivity: KernelSensitivity
    description: str | None
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
    def from_model(cls, model: VariableDefinition) -> VariableDefinitionResponse:
        return cls(
            id=str(model.id),
            canonical_name=str(model.canonical_name),
            display_name=str(model.display_name),
            data_type=KernelDataType(str(model.data_type)),
            preferred_unit=str(model.preferred_unit) if model.preferred_unit else None,
            constraints=dict(model.constraints) if model.constraints else {},
            domain_context=str(model.domain_context),
            sensitivity=KernelSensitivity(str(model.sensitivity)),
            description=str(model.description) if model.description else None,
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


class VariableDefinitionListResponse(BaseModel):
    """List response payload for dictionary variables."""

    model_config = ConfigDict(strict=True)

    variables: list[VariableDefinitionResponse]
    total: int


class VariableDefinitionReviewStatusRequest(BaseModel):
    """Request payload for dictionary variable review-status updates."""

    model_config = ConfigDict(strict=False)

    review_status: KernelReviewStatus
    revocation_reason: str | None = Field(
        default=None,
        description="Required when review_status is REVOKED",
    )

    @model_validator(mode="after")
    def validate_reason(self) -> VariableDefinitionReviewStatusRequest:
        """Enforce reason semantics for revocation updates."""
        if self.review_status == KernelReviewStatus.REVOKED:
            if self.revocation_reason is None or not self.revocation_reason.strip():
                msg = "revocation_reason is required when review_status is REVOKED"
                raise ValueError(msg)
        elif self.revocation_reason is not None:
            msg = "revocation_reason is only valid for REVOKED status"
            raise ValueError(msg)
        return self


class VariableDefinitionRevokeRequest(BaseModel):
    """Request payload for explicit variable revocation operations."""

    reason: str = Field(..., min_length=1)


class DictionaryMergeRequest(BaseModel):
    """Request payload for dictionary merge operations."""

    target_id: str = Field(..., min_length=1, max_length=64)
    reason: str = Field(..., min_length=1)


__all__ = [
    "DictionaryMergeRequest",
    "VariableDefinitionCreateRequest",
    "VariableDefinitionListResponse",
    "VariableDefinitionResponse",
    "VariableDefinitionReviewStatusRequest",
    "VariableDefinitionRevokeRequest",
]
