"""
Entity recognition output contract for Tier-3 extraction workflows.

This contract captures what the recognizer inferred from a source document and
what semantic-layer mutations were proposed or applied.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from src.domain.agents.contracts.assessment_compat import (
    confidence_from_entity_recognition_contract,
)
from src.domain.agents.contracts.base import EvidenceBackedAgentContract
from src.domain.agents.contracts.recognition_assessment import (
    RecognitionAssessment,
    build_recognition_assessment_from_confidence,
    recognition_assessment_confidence,
)
from src.type_definitions.common import JSONObject, JSONValue  # noqa: TC001


class RecognizedEntityCandidate(BaseModel):
    """Entity candidate recognized from a source document."""

    entity_type: str = Field(..., min_length=1, max_length=64)
    display_label: str = Field(..., min_length=1, max_length=255)
    identifiers: JSONObject = Field(default_factory=dict)
    assessment: RecognitionAssessment

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy_confidence(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        if "assessment" in value or "confidence" not in value:
            return value
        raw_confidence = value.get("confidence")
        if isinstance(raw_confidence, bool) or not isinstance(
            raw_confidence,
            int | float,
        ):
            return value
        payload = dict(value)
        payload.pop("confidence", None)
        payload["assessment"] = build_recognition_assessment_from_confidence(
            float(raw_confidence),
        )
        return payload

    @property
    def confidence(self) -> float:
        """Derived confidence used by existing downstream ranking code."""
        return recognition_assessment_confidence(self.assessment)


class RecognizedObservationCandidate(BaseModel):
    """Observation candidate recognized from a source document field."""

    field_name: str = Field(..., min_length=1, max_length=128)
    variable_id: str | None = Field(default=None, max_length=64)
    value: JSONValue
    unit: str | None = Field(default=None, max_length=64)
    assessment: RecognitionAssessment

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy_confidence(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        if "assessment" in value or "confidence" not in value:
            return value
        raw_confidence = value.get("confidence")
        if isinstance(raw_confidence, bool) or not isinstance(
            raw_confidence,
            int | float,
        ):
            return value
        payload = dict(value)
        payload.pop("confidence", None)
        payload["assessment"] = build_recognition_assessment_from_confidence(
            float(raw_confidence),
        )
        return payload

    @property
    def confidence(self) -> float:
        """Derived confidence used by existing downstream ranking code."""
        return recognition_assessment_confidence(self.assessment)


class EntityRecognitionContract(EvidenceBackedAgentContract):
    """
    Contract for Entity Recognition Agent outputs.

    `decision` follows the same governance pattern used by query generation.
    """

    confidence_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Derived backend confidence for routing and audit compatibility.",
    )
    decision: Literal["generated", "fallback", "escalate"] = Field(
        ...,
        description="Outcome of the entity-recognition run",
    )
    source_type: str = Field(..., min_length=1, max_length=64)
    document_id: str = Field(..., min_length=1, max_length=64)
    primary_entity_type: str = Field(default="VARIANT", min_length=1, max_length=64)
    field_candidates: list[str] = Field(default_factory=list)
    recognized_entities: list[RecognizedEntityCandidate] = Field(default_factory=list)
    recognized_observations: list[RecognizedObservationCandidate] = Field(
        default_factory=list,
    )
    pipeline_payloads: list[JSONObject] = Field(
        default_factory=list,
        description="Raw payloads that can be forwarded to the kernel ingestion pipeline",
    )
    created_definitions: list[str] = Field(default_factory=list)
    created_synonyms: list[str] = Field(default_factory=list)
    created_entity_types: list[str] = Field(default_factory=list)
    created_relation_types: list[str] = Field(default_factory=list)
    created_relation_constraints: list[str] = Field(default_factory=list)
    shadow_mode: bool = Field(
        default=True,
        description="Whether persistence side effects should be suppressed",
    )
    agent_run_id: str | None = Field(
        default=None,
        description="Orchestration run identifier when available",
    )

    @model_validator(mode="after")
    def _normalize_confidence_score(self) -> EntityRecognitionContract:
        derived_confidence = confidence_from_entity_recognition_contract(self)
        self.confidence_score = derived_confidence
        return self


__all__ = [
    "EntityRecognitionContract",
    "RecognitionAssessment",
    "RecognizedEntityCandidate",
    "RecognizedObservationCandidate",
]
