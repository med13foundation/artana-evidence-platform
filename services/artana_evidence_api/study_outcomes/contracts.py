"""Contracts for clinical-trial study outcomes extracted from documents."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from artana_evidence_api.types.common import JSONObject
from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True, slots=True)
class StudyOutcomeDraft:
    """Structured quantitative outcome staged before persistence."""

    intervention: str
    comparator: str | None
    outcome_metric: str
    value: float
    unit: str
    confidence_interval_low: float | None
    confidence_interval_high: float | None
    population: str
    n: int | None
    source_pmid: str
    source_quote: str
    metadata: JSONObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StudyOutcomeRecord:
    """Persisted quantitative trial outcome linked to a harness document."""

    id: str
    space_id: str
    document_id: str
    run_id: str | None
    intervention: str
    comparator: str | None
    outcome_metric: str
    value: float
    unit: str
    confidence_interval_low: float | None
    confidence_interval_high: float | None
    population: str
    n: int | None
    source_pmid: str
    source_quote: str
    metadata: JSONObject
    outcome_fingerprint: str
    created_at: datetime
    updated_at: datetime


class StudyOutcomeResponse(BaseModel):
    """Public response model for one quantitative trial outcome."""

    model_config = ConfigDict(strict=True)

    id: str
    space_id: str
    document_id: str
    run_id: str | None
    intervention: str
    comparator: str | None
    outcome_metric: str
    value: float
    unit: str
    confidence_interval_low: float | None
    confidence_interval_high: float | None
    population: str
    n: int | None
    source_pmid: str
    source_quote: str
    metadata: JSONObject
    created_at: str
    updated_at: str

    @classmethod
    def from_record(cls, record: StudyOutcomeRecord) -> StudyOutcomeResponse:
        return cls(
            id=record.id,
            space_id=record.space_id,
            document_id=record.document_id,
            run_id=record.run_id,
            intervention=record.intervention,
            comparator=record.comparator,
            outcome_metric=record.outcome_metric,
            value=record.value,
            unit=record.unit,
            confidence_interval_low=record.confidence_interval_low,
            confidence_interval_high=record.confidence_interval_high,
            population=record.population,
            n=record.n,
            source_pmid=record.source_pmid,
            source_quote=record.source_quote,
            metadata=record.metadata,
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
        )


class StudyOutcomeListResponse(BaseModel):
    """List response for public study-outcome queries."""

    model_config = ConfigDict(strict=True)

    study_outcomes: list[StudyOutcomeResponse]
    total: int = Field(..., ge=0)
    offset: int = Field(..., ge=0)
    limit: int = Field(..., ge=1)


__all__ = [
    "StudyOutcomeDraft",
    "StudyOutcomeListResponse",
    "StudyOutcomeRecord",
    "StudyOutcomeResponse",
]
