# ruff: noqa: TC001,TC003
"""Value-set schemas for dictionary admin routes."""

from __future__ import annotations

from datetime import datetime

from artana_evidence_db.kernel_domain_models import ValueSet, ValueSetItem
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .dictionary_schema_common import KernelReviewStatus


class ValueSetCreateRequest(BaseModel):
    """Request payload for creating a dictionary value set."""

    model_config = ConfigDict(strict=False)

    id: str = Field(..., min_length=1, max_length=64)
    variable_id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    external_ref: str | None = Field(default=None, max_length=255)
    is_extensible: bool = False
    source_ref: str | None = Field(default=None, max_length=1024)


class ValueSetResponse(BaseModel):
    """Response payload for a dictionary value set."""

    model_config = ConfigDict(strict=True)

    id: str
    variable_id: str
    variable_data_type: str
    name: str
    description: str | None
    external_ref: str | None
    is_extensible: bool
    created_by: str
    source_ref: str | None
    review_status: KernelReviewStatus
    reviewed_by: str | None
    reviewed_at: datetime | None
    revocation_reason: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: ValueSet) -> ValueSetResponse:
        return cls(
            id=str(model.id),
            variable_id=str(model.variable_id),
            variable_data_type=str(model.variable_data_type),
            name=str(model.name),
            description=str(model.description) if model.description else None,
            external_ref=str(model.external_ref) if model.external_ref else None,
            is_extensible=bool(model.is_extensible),
            created_by=str(model.created_by),
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


class ValueSetListResponse(BaseModel):
    """List response payload for dictionary value sets."""

    model_config = ConfigDict(strict=True)

    value_sets: list[ValueSetResponse]
    total: int


class ValueSetItemCreateRequest(BaseModel):
    """Request payload for creating a value set item."""

    model_config = ConfigDict(strict=False)

    code: str = Field(..., min_length=1, max_length=128)
    display_label: str = Field(..., min_length=1, max_length=255)
    synonyms: list[str] = Field(default_factory=list)
    external_ref: str | None = Field(default=None, max_length=255)
    sort_order: int = 0
    is_active: bool = True
    source_ref: str | None = Field(default=None, max_length=1024)


class ValueSetItemResponse(BaseModel):
    """Response payload for a dictionary value set item."""

    model_config = ConfigDict(strict=True)

    id: int
    value_set_id: str
    code: str
    display_label: str
    synonyms: list[str]
    external_ref: str | None
    sort_order: int
    is_active: bool
    created_by: str
    source_ref: str | None
    review_status: KernelReviewStatus
    reviewed_by: str | None
    reviewed_at: datetime | None
    revocation_reason: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: ValueSetItem) -> ValueSetItemResponse:
        return cls(
            id=int(model.id),
            value_set_id=str(model.value_set_id),
            code=str(model.code),
            display_label=str(model.display_label),
            synonyms=list(model.synonyms) if isinstance(model.synonyms, list) else [],
            external_ref=str(model.external_ref) if model.external_ref else None,
            sort_order=int(model.sort_order),
            is_active=bool(model.is_active),
            created_by=str(model.created_by),
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


class ValueSetItemListResponse(BaseModel):
    """List response payload for dictionary value set items."""

    model_config = ConfigDict(strict=True)

    items: list[ValueSetItemResponse]
    total: int


class ValueSetItemActiveRequest(BaseModel):
    """Request payload for activating/deactivating a value set item."""

    model_config = ConfigDict(strict=False)

    is_active: bool
    revocation_reason: str | None = Field(
        default=None,
        description="Required when is_active is false",
    )

    @model_validator(mode="after")
    def validate_reason(self) -> ValueSetItemActiveRequest:
        """Enforce reason semantics for deactivation updates."""
        if not self.is_active:
            if self.revocation_reason is None or not self.revocation_reason.strip():
                msg = "revocation_reason is required when deactivating a value set item"
                raise ValueError(msg)
        elif self.revocation_reason is not None:
            msg = "revocation_reason is only valid when deactivating a value set item"
            raise ValueError(msg)
        return self


__all__ = [
    "ValueSetCreateRequest",
    "ValueSetItemActiveRequest",
    "ValueSetItemCreateRequest",
    "ValueSetItemListResponse",
    "ValueSetItemResponse",
    "ValueSetListResponse",
    "ValueSetResponse",
]
