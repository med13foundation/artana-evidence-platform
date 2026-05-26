"""Typed contracts for request-time trial matching."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_DEFAULT_STATUSES = ("RECRUITING", "NOT_YET_RECRUITING")


class TrialMatchingQuery(BaseModel):
    """Patient context used to query and rank live ClinicalTrials.gov matches."""

    model_config = ConfigDict(frozen=True)

    condition: str = Field(..., min_length=1, max_length=256)
    age: int | None = Field(default=None, ge=0, le=130)
    country: str | None = Field(default=None, min_length=1, max_length=64)
    within_miles: int | None = Field(default=None, ge=1, le=500)
    reference_city: str | None = Field(default=None, min_length=1, max_length=128)
    reference_latitude: float | None = Field(default=None, ge=-90, le=90)
    reference_longitude: float | None = Field(default=None, ge=-180, le=180)
    statuses: tuple[str, ...] = Field(default=_DEFAULT_STATUSES, min_length=1)
    molecular_markers: tuple[str, ...] = Field(default_factory=tuple)
    prior_treatments: tuple[str, ...] = Field(default_factory=tuple)
    max_results: int = Field(default=20, ge=1, le=100)

    @field_validator("condition", "country", "reference_city", mode="before")
    @classmethod
    def _normalize_optional_text(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            normalized = " ".join(value.split())
            return normalized or None
        return value

    @field_validator("statuses", mode="before")
    @classmethod
    def _normalize_statuses(cls, value: object) -> object:
        if isinstance(value, str):
            raw_values = value.replace(",", "|").split("|")
        elif isinstance(value, list | tuple):
            raw_values = [str(item) for item in value]
        else:
            raw_values = []
        normalized = tuple(
            dict.fromkeys(
                " ".join(item.split()).upper()
                for item in raw_values
                if " ".join(item.split())
            ),
        )
        return normalized or _DEFAULT_STATUSES

    @field_validator("molecular_markers", "prior_treatments", mode="before")
    @classmethod
    def _normalize_context_terms(cls, value: object) -> object:
        if value is None:
            return ()
        if isinstance(value, str):
            raw_values = value.split(",")
        elif isinstance(value, list | tuple):
            raw_values = [str(item) for item in value]
        else:
            raw_values = []
        return tuple(
            dict.fromkeys(
                _normalize_context_term(item)
                for item in raw_values
                if _normalize_context_term(item)
            ),
        )

    @model_validator(mode="after")
    def _validate_geo_pair(self) -> TrialMatchingQuery:
        has_latitude = self.reference_latitude is not None
        has_longitude = self.reference_longitude is not None
        if has_latitude is has_longitude:
            return self
        msg = "reference_latitude and reference_longitude must be provided together"
        raise ValueError(msg)


class TrialMatchLocation(BaseModel):
    """Public location/contact fields for one matching trial site."""

    facility: str
    status: str
    city: str
    state: str
    zip: str
    country: str
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class TrialMatchResponse(BaseModel):
    """One live ClinicalTrials.gov match ranked against patient context."""

    nct_id: str
    title: str
    status: str
    phase: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    intervention_names: list[str] = Field(default_factory=list)
    eligibility_summary: str
    minimum_age: str | None = None
    maximum_age: str | None = None
    sex: str | None = None
    locations: list[TrialMatchLocation] = Field(default_factory=list)
    primary_investigator: str | None = None
    contact_email: str | None = None
    relevance_score: float = Field(ge=0, le=1)
    relevance_reasons: list[str] = Field(default_factory=list)
    matched_terms: list[str] = Field(default_factory=list)
    source_url: str


class TrialMatchingResponse(BaseModel):
    """Response for request-time live ClinicalTrials.gov trial matching."""

    space_id: UUID
    source: Literal["clinical_trials"] = "clinical_trials"
    query: TrialMatchingQuery
    trial_matches: list[TrialMatchResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    generated_at: datetime


def _normalize_context_term(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.replace("_", " ").split())


__all__ = [
    "TrialMatchLocation",
    "TrialMatchResponse",
    "TrialMatchingQuery",
    "TrialMatchingResponse",
]
