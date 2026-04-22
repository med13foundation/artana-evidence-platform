# ruff: noqa: TC001,TC003
"""Pydantic schemas for admin dictionary transform endpoints."""

from __future__ import annotations

from datetime import datetime

from artana_evidence_db.common_types import JSONValue
from artana_evidence_db.graph_api_schemas.dictionary_schemas import (
    KernelReviewStatus,
)
from artana_evidence_db.kernel_domain_models import (
    TransformRegistry,
    TransformVerificationResult,
)
from pydantic import BaseModel, ConfigDict


class TransformRegistryResponse(BaseModel):
    """Response payload for a transform registry record."""

    model_config = ConfigDict(strict=True)

    id: str
    input_unit: str
    output_unit: str
    category: str
    input_data_type: str | None
    output_data_type: str | None
    implementation_ref: str
    is_deterministic: bool
    is_production_allowed: bool
    test_input: JSONValue | None
    expected_output: JSONValue | None
    description: str | None
    status: str
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
    def from_model(cls, model: TransformRegistry) -> TransformRegistryResponse:
        return cls(
            id=str(model.id),
            input_unit=str(model.input_unit),
            output_unit=str(model.output_unit),
            category=str(model.category),
            input_data_type=(
                str(model.input_data_type)
                if model.input_data_type is not None
                else None
            ),
            output_data_type=(
                str(model.output_data_type)
                if model.output_data_type is not None
                else None
            ),
            implementation_ref=str(model.implementation_ref),
            is_deterministic=bool(model.is_deterministic),
            is_production_allowed=bool(model.is_production_allowed),
            test_input=model.test_input,
            expected_output=model.expected_output,
            description=(
                str(model.description) if model.description is not None else None
            ),
            status=str(model.status),
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


class TransformRegistryListResponse(BaseModel):
    """List response payload for transform registry records."""

    model_config = ConfigDict(strict=True)

    transforms: list[TransformRegistryResponse]
    total: int


class TransformVerificationResponse(BaseModel):
    """Verification result for one transform fixture run."""

    model_config = ConfigDict(strict=True)

    transform_id: str
    passed: bool
    message: str
    actual_output: JSONValue | None
    expected_output: JSONValue | None
    checked_at: datetime

    @classmethod
    def from_model(
        cls,
        model: TransformVerificationResult,
    ) -> TransformVerificationResponse:
        return cls(
            transform_id=str(model.transform_id),
            passed=bool(model.passed),
            message=str(model.message),
            actual_output=model.actual_output,
            expected_output=model.expected_output,
            checked_at=model.checked_at,
        )


__all__ = [
    "TransformRegistryListResponse",
    "TransformRegistryResponse",
    "TransformVerificationResponse",
]
