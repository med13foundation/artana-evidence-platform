"""Contracts for patient-context query runs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from artana_evidence_api.study_outcomes import StudyOutcomeResponse
from artana_evidence_api.trial_matching import TrialMatchResponse
from artana_evidence_api.types.common import JSONObject
from pydantic import BaseModel, ConfigDict, Field, field_validator

PatientQueryRunStatus = Literal["completed"]


class PatientLocation(BaseModel):
    """Patient location context used for request-time trial matching."""

    model_config = ConfigDict(strict=True)

    country: str | None = Field(default=None, min_length=1, max_length=64)
    city: str | None = Field(default=None, min_length=1, max_length=128)
    within_miles: int | None = Field(default=None, ge=1, le=500)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @field_validator("country", "city")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None


class PatientContext(BaseModel):
    """Per-query patient context used to tailor evidence output."""

    model_config = ConfigDict(strict=True)

    age: int | None = Field(default=None, ge=0, le=130)
    performance_status: str | None = Field(default=None, min_length=1, max_length=64)
    diagnosis: str = Field(default="", max_length=256)
    stage_or_grade: str | None = Field(default=None, min_length=1, max_length=64)
    molecular_markers: dict[str, str] = Field(default_factory=dict)
    prior_treatments: list[str] = Field(default_factory=list, max_length=25)
    location: PatientLocation | None = None

    @field_validator("performance_status", "stage_or_grade")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None

    @field_validator("diagnosis")
    @classmethod
    def _normalize_diagnosis(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("molecular_markers")
    @classmethod
    def _normalize_molecular_markers(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for raw_key, raw_value in value.items():
            key = _clean_context_text(raw_key)
            marker_value = _clean_context_text(raw_value)
            if key and marker_value:
                normalized[key] = marker_value
        return normalized

    @field_validator("prior_treatments")
    @classmethod
    def _normalize_prior_treatments(cls, value: list[str]) -> list[str]:
        return list(
            dict.fromkeys(
                treatment
                for raw_treatment in value
                if (treatment := _clean_context_text(raw_treatment))
            ),
        )


class PatientQueryRunRequest(BaseModel):
    """Request payload for a patient-context evidence query."""

    model_config = ConfigDict(strict=True)

    query: str = Field(..., min_length=1, max_length=128)
    patient_context: PatientContext
    max_claims: int = Field(default=20, ge=1, le=100)
    max_outcomes: int = Field(default=20, ge=1, le=100)
    max_trials: int = Field(default=20, ge=1, le=100)

    @field_validator("query")
    @classmethod
    def _normalize_query(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            msg = "query must not be empty"
            raise ValueError(msg)
        return normalized


class PatientRelevantClaimResponse(BaseModel):
    """One promoted claim ranked against patient context."""

    model_config = ConfigDict(strict=True)

    proposal_id: str
    title: str
    summary: str
    source_key: str
    evidence_grade: str | None
    confidence: float
    ranking_score: float
    relevance_score: float = Field(ge=0, le=1)
    matched_terms: list[str] = Field(default_factory=list)
    payload: JSONObject
    metadata: JSONObject
    evidence_bundle: list[JSONObject]


class PatientQueryRunResponse(BaseModel):
    """Completed patient-context query response."""

    model_config = ConfigDict(strict=True)

    id: UUID
    space_id: UUID
    status: PatientQueryRunStatus
    query: str
    patient_context: PatientContext
    claim_matches: list[PatientRelevantClaimResponse] = Field(default_factory=list)
    study_outcomes: list[StudyOutcomeResponse] = Field(default_factory=list)
    trial_matches: list[TrialMatchResponse] = Field(default_factory=list)
    generated_at: datetime


def _clean_context_text(value: str) -> str:
    return " ".join(value.replace("_", " ").split())


__all__ = [
    "PatientContext",
    "PatientLocation",
    "PatientQueryRunRequest",
    "PatientQueryRunResponse",
    "PatientQueryRunStatus",
    "PatientRelevantClaimResponse",
]
