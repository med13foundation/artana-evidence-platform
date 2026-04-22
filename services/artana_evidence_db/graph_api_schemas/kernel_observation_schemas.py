# ruff: noqa: TC001,TC003
"""Observation schemas for kernel graph routes."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from artana_evidence_db.common_types import JSONValue
from artana_evidence_db.graph_api_schemas.kernel_schema_common import (
    _to_required_utc_datetime,
    _to_utc_datetime,
    _to_uuid,
)
from artana_evidence_db.kernel_domain_models import KernelObservation
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal


class KernelObservationCreateRequest(BaseModel):
    """Request model for recording a kernel observation."""

    model_config = ConfigDict(strict=False)

    subject_id: UUID
    variable_id: str = Field(..., min_length=1, max_length=64)
    value: JSONValue
    unit: str | None = Field(None, max_length=64)
    observed_at: datetime | None = None
    provenance_id: UUID | None = None
    observation_origin: Literal["MANUAL", "IMPORTED", "AI_AUTHORED"] = "MANUAL"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class KernelObservationResponse(BaseModel):
    """Response model for a kernel observation."""

    model_config = ConfigDict(strict=True)

    id: UUID
    research_space_id: UUID
    subject_id: UUID
    variable_id: str
    value_numeric: float | None
    value_text: str | None
    value_date: datetime | None
    value_coded: str | None
    value_boolean: bool | None
    value_json: JSONValue | None
    unit: str | None
    observed_at: datetime | None
    provenance_id: UUID | None
    confidence: float
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: KernelObservation) -> KernelObservationResponse:
        value_numeric_raw = model.value_numeric
        value_numeric = (
            float(value_numeric_raw) if value_numeric_raw is not None else None
        )

        provenance_id_raw = model.provenance_id
        provenance_id = (
            _to_uuid(provenance_id_raw) if provenance_id_raw is not None else None
        )

        return cls(
            id=_to_uuid(model.id),
            research_space_id=_to_uuid(model.research_space_id),
            subject_id=_to_uuid(model.subject_id),
            variable_id=str(model.variable_id),
            value_numeric=value_numeric,
            value_text=model.value_text,
            value_date=_to_utc_datetime(model.value_date),
            value_coded=model.value_coded,
            value_boolean=model.value_boolean,
            value_json=model.value_json,
            unit=model.unit,
            observed_at=_to_utc_datetime(model.observed_at),
            provenance_id=provenance_id,
            confidence=float(model.confidence),
            created_at=_to_required_utc_datetime(
                model.created_at,
                field_name="observation.created_at",
            ),
            updated_at=_to_required_utc_datetime(
                model.updated_at,
                field_name="observation.updated_at",
            ),
        )


class KernelObservationListResponse(BaseModel):
    """List response for observations within a research space."""

    model_config = ConfigDict(strict=True)

    observations: list[KernelObservationResponse]
    total: int
    offset: int
    limit: int
