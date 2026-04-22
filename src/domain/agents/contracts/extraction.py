"""
Extraction output contract for Tier-3 structured fact mapping.

The Extraction Agent maps content to existing dictionary definitions and
returns validated entities, observations, relations, plus rejected candidates.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from src.domain.agents.contracts.assessment_compat import (
    confidence_from_extraction_contract,
)
from src.domain.agents.contracts.base import EvidenceBackedAgentContract
from src.domain.agents.contracts.fact_assessment import (
    FactAssessment,
    assessment_confidence_weight,
)
from src.type_definitions.common import JSONObject, JSONValue  # noqa: TC001


class ExtractedObservation(BaseModel):
    """Validated observation mapped to an existing dictionary variable."""

    field_name: str = Field(..., min_length=1, max_length=128)
    variable_id: str = Field(..., min_length=1, max_length=64)
    value: JSONValue
    unit: str | None = Field(default=None, max_length=64)
    assessment: FactAssessment

    @property
    def confidence(self) -> float:
        """Backward-compatible derived confidence for internal consumers."""
        return assessment_confidence_weight(self.assessment)


class ExtractedEntityCandidate(BaseModel):
    """Entity candidate extracted as a first-class structured output."""

    entity_type: str = Field(..., min_length=1, max_length=64)
    label: str = Field(..., min_length=1, max_length=255)
    anchors: JSONObject = Field(
        ...,
        description="Entity resolution anchors preserved verbatim when supported.",
    )
    metadata: JSONObject = Field(
        ...,
        description="Typed source-backed metadata for staged entity persistence.",
    )
    evidence_excerpt: str = Field(
        ...,
        min_length=1,
        max_length=1200,
        description="Supporting text span or structured source excerpt.",
    )
    evidence_locator: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Locator for the supporting evidence span or field path.",
    )
    assessment: FactAssessment

    @property
    def confidence(self) -> float:
        """Backward-compatible derived confidence for internal consumers."""
        return assessment_confidence_weight(self.assessment)


class ExtractedRelation(BaseModel):
    """Validated relation triple mapped to dictionary relation constraints."""

    source_type: str = Field(..., min_length=1, max_length=64)
    relation_type: str = Field(..., min_length=1, max_length=64)
    target_type: str = Field(..., min_length=1, max_length=64)
    polarity: Literal["SUPPORT", "REFUTE", "UNCERTAIN", "HYPOTHESIS"] = Field(
        default="UNCERTAIN",
    )
    claim_text: str | None = Field(default=None, max_length=2000)
    claim_section: str | None = Field(default=None, max_length=64)
    source_label: str | None = Field(default=None, max_length=255)
    target_label: str | None = Field(default=None, max_length=255)
    source_anchors: JSONObject = Field(
        default_factory=dict,
        description="Structured endpoint anchors for the source entity when known.",
    )
    target_anchors: JSONObject = Field(
        default_factory=dict,
        description="Structured endpoint anchors for the target entity when known.",
    )
    evidence_excerpt: str | None = Field(
        default=None,
        max_length=1200,
        description="Relation-level supporting text span excerpt from the source.",
    )
    evidence_locator: str | None = Field(
        default=None,
        max_length=255,
        description="Locator for the evidence span (sentence id, section, etc.).",
    )
    assessment: FactAssessment

    @property
    def confidence(self) -> float:
        """Backward-compatible derived confidence for internal consumers."""
        return assessment_confidence_weight(self.assessment)


class RejectedFact(BaseModel):
    """Candidate fact rejected during tool-assisted extraction validation."""

    fact_type: Literal["observation", "relation"]
    reason: str = Field(..., min_length=1, max_length=255)
    payload: JSONObject = Field(default_factory=dict)
    assessment: FactAssessment | None = Field(
        default=None,
        description="Original qualitative assessment when available.",
    )


class ExtractionContract(EvidenceBackedAgentContract):
    """Contract for Extraction Agent outputs."""

    confidence_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Derived backend run-level confidence for automated routing decisions",
    )
    decision: Literal["generated", "fallback", "escalate"] = Field(
        ...,
        description="Outcome of the extraction run",
    )
    source_type: str = Field(..., min_length=1, max_length=64)
    document_id: str = Field(..., min_length=1, max_length=64)
    entities: list[ExtractedEntityCandidate] = Field(default_factory=list)
    observations: list[ExtractedObservation] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)
    rejected_facts: list[RejectedFact] = Field(default_factory=list)
    pipeline_payloads: list[JSONObject] = Field(
        default_factory=list,
        description="Payloads suitable for kernel ingestion",
    )
    shadow_mode: bool = Field(
        default=True,
        description="Whether side effects should be suppressed",
    )
    agent_run_id: str | None = Field(
        default=None,
        description="Orchestration run identifier when available",
    )

    @model_validator(mode="after")
    def _normalize_confidence_score(self) -> ExtractionContract:
        derived_confidence = confidence_from_extraction_contract(self)
        self.confidence_score = derived_confidence
        return self


__all__ = [
    "ExtractedEntityCandidate",
    "ExtractedObservation",
    "ExtractedRelation",
    "ExtractionContract",
    "RejectedFact",
]
