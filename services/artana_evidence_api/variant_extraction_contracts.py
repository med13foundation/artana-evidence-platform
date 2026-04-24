"""Service-owned extraction contracts for the variant-aware document bridge."""

from __future__ import annotations

from typing import Literal, cast

from artana_evidence_api.agent_contracts import EvidenceBackedAgentContract
from artana_evidence_api.types.common import JSONObject, JSONValue
from artana_evidence_api.types.graph_fact_assessment import (
    FactAssessment,
    assessment_confidence_weight,
)
from pydantic import BaseModel, Field, model_validator

LLMScalarValue = str | int | float | bool | None


class LLMKeyValueField(BaseModel):
    """OpenAI structured-output-safe representation of a dynamic JSON field."""

    key: str = Field(..., min_length=1, max_length=128)
    value: LLMScalarValue


def _fields_to_json_object(fields: list[LLMKeyValueField]) -> JSONObject:
    """Convert LLM-safe key/value fields back into the service JSON shape."""
    payload: JSONObject = {}
    for field in fields:
        key = field.key.strip()
        if key == "":
            continue
        payload[key] = cast("JSONValue", field.value)
    return payload


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


class LLMExtractedObservation(BaseModel):
    """LLM-safe observation schema without arbitrary JSON object fields."""

    field_name: str = Field(..., min_length=1, max_length=128)
    variable_id: str = Field(..., min_length=1, max_length=64)
    value: LLMScalarValue
    unit: str | None = Field(default=None, max_length=64)
    assessment: FactAssessment

    def to_extracted_observation(self) -> ExtractedObservation:
        """Return the internal service observation contract."""
        return ExtractedObservation(
            field_name=self.field_name,
            variable_id=self.variable_id,
            value=cast("JSONValue", self.value),
            unit=self.unit,
            assessment=self.assessment,
        )


class LLMExtractedEntityCandidate(BaseModel):
    """LLM-safe entity candidate using key/value arrays for dynamic fields."""

    entity_type: str = Field(..., min_length=1, max_length=64)
    label: str = Field(..., min_length=1, max_length=255)
    anchors: list[LLMKeyValueField] = Field(default_factory=list)
    metadata: list[LLMKeyValueField] = Field(default_factory=list)
    evidence_excerpt: str = Field(..., min_length=1, max_length=1200)
    evidence_locator: str = Field(..., min_length=1, max_length=255)
    assessment: FactAssessment

    def to_extracted_entity_candidate(self) -> ExtractedEntityCandidate:
        """Return the internal service entity candidate contract."""
        return ExtractedEntityCandidate(
            entity_type=self.entity_type,
            label=self.label,
            anchors=_fields_to_json_object(self.anchors),
            metadata=_fields_to_json_object(self.metadata),
            evidence_excerpt=self.evidence_excerpt,
            evidence_locator=self.evidence_locator,
            assessment=self.assessment,
        )


class LLMExtractedRelation(BaseModel):
    """LLM-safe relation triple using key/value arrays for endpoint anchors."""

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
    source_anchors: list[LLMKeyValueField] = Field(default_factory=list)
    target_anchors: list[LLMKeyValueField] = Field(default_factory=list)
    evidence_excerpt: str | None = Field(default=None, max_length=1200)
    evidence_locator: str | None = Field(default=None, max_length=255)
    assessment: FactAssessment

    def to_extracted_relation(self) -> ExtractedRelation:
        """Return the internal service relation contract."""
        return ExtractedRelation(
            source_type=self.source_type,
            relation_type=self.relation_type,
            target_type=self.target_type,
            polarity=self.polarity,
            claim_text=self.claim_text,
            claim_section=self.claim_section,
            source_label=self.source_label,
            target_label=self.target_label,
            source_anchors=_fields_to_json_object(self.source_anchors),
            target_anchors=_fields_to_json_object(self.target_anchors),
            evidence_excerpt=self.evidence_excerpt,
            evidence_locator=self.evidence_locator,
            assessment=self.assessment,
        )


class LLMRejectedFact(BaseModel):
    """LLM-safe rejected-fact schema without arbitrary JSON object fields."""

    fact_type: Literal["observation", "relation"]
    reason: str = Field(..., min_length=1, max_length=255)
    payload: list[LLMKeyValueField] = Field(default_factory=list)
    assessment: FactAssessment | None = Field(default=None)

    def to_rejected_fact(self) -> RejectedFact:
        """Return the internal service rejected fact contract."""
        return RejectedFact(
            fact_type=self.fact_type,
            reason=self.reason,
            payload=_fields_to_json_object(self.payload),
            assessment=self.assessment,
        )


class ExtractionContract(EvidenceBackedAgentContract):
    """Contract for variant-aware extraction outputs owned by the service."""

    confidence_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Derived backend run-level confidence for routing decisions.",
    )
    decision: Literal["generated", "fallback", "escalate"] = Field(
        ...,
        description="Outcome of the extraction run.",
    )
    source_type: str = Field(..., min_length=1, max_length=64)
    document_id: str = Field(..., min_length=1, max_length=64)
    entities: list[ExtractedEntityCandidate] = Field(default_factory=list)
    observations: list[ExtractedObservation] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)
    rejected_facts: list[RejectedFact] = Field(default_factory=list)
    pipeline_payloads: list[JSONObject] = Field(
        default_factory=list,
        description="Payloads suitable for kernel ingestion.",
    )
    shadow_mode: bool = Field(
        default=True,
        description="Whether side effects should be suppressed.",
    )
    agent_run_id: str | None = Field(
        default=None,
        description="Orchestration run identifier when available.",
    )

    @model_validator(mode="after")
    def _normalize_confidence_score(self) -> ExtractionContract:
        entity_scores = [
            entity.confidence for entity in self.entities if entity.confidence > 0.0
        ]
        observation_scores = [
            observation.confidence
            for observation in self.observations
            if observation.confidence > 0.0
        ]
        relation_scores = [
            relation.confidence
            for relation in self.relations
            if relation.confidence > 0.0
        ]
        confidence_scores = [*entity_scores, *observation_scores, *relation_scores]
        self.confidence_score = max(confidence_scores, default=0.0)
        return self


class LLMExtractionContract(EvidenceBackedAgentContract):
    """OpenAI structured-output-safe contract for live variant extraction."""

    confidence_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Derived backend run-level confidence for routing decisions.",
    )
    decision: Literal["generated", "fallback", "escalate"] = Field(
        ...,
        description="Outcome of the extraction run.",
    )
    source_type: str = Field(..., min_length=1, max_length=64)
    document_id: str = Field(..., min_length=1, max_length=64)
    entities: list[LLMExtractedEntityCandidate] = Field(default_factory=list)
    observations: list[LLMExtractedObservation] = Field(default_factory=list)
    relations: list[LLMExtractedRelation] = Field(default_factory=list)
    rejected_facts: list[LLMRejectedFact] = Field(default_factory=list)
    shadow_mode: bool = Field(default=True)
    agent_run_id: str | None = Field(default=None)

    def to_extraction_contract(self) -> ExtractionContract:
        """Convert the LLM-safe schema into the internal service contract."""
        return ExtractionContract(
            rationale=self.rationale,
            evidence=self.evidence,
            confidence_score=self.confidence_score,
            decision=self.decision,
            source_type=self.source_type,
            document_id=self.document_id,
            entities=[
                entity.to_extracted_entity_candidate() for entity in self.entities
            ],
            observations=[
                observation.to_extracted_observation()
                for observation in self.observations
            ],
            relations=[relation.to_extracted_relation() for relation in self.relations],
            rejected_facts=[
                rejected_fact.to_rejected_fact()
                for rejected_fact in self.rejected_facts
            ],
            pipeline_payloads=[],
            shadow_mode=self.shadow_mode,
            agent_run_id=self.agent_run_id,
        )


__all__ = [
    "ExtractedEntityCandidate",
    "ExtractedObservation",
    "ExtractedRelation",
    "ExtractionContract",
    "LLMExtractionContract",
    "LLMExtractedEntityCandidate",
    "LLMExtractedObservation",
    "LLMExtractedRelation",
    "LLMKeyValueField",
    "LLMRejectedFact",
    "RejectedFact",
]
