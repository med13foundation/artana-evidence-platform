"""Service-owned extraction contracts for the variant-aware document bridge."""

from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Literal, cast

from artana_evidence_api.agent_contracts import (
    EvidenceBackedAgentContract,
    ModelEvidenceCitation,
)
from artana_evidence_api.runtime.agent_output_schema import SourceMeasurementNumber
from artana_evidence_api.types.common import JSONObject, JSONValue
from artana_evidence_api.types.graph_fact_assessment import (
    FactAssessment,
    assessment_confidence_weight,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator

LLMLiteralValue = str | bool | None
LLMObservationValue = LLMLiteralValue | SourceMeasurementNumber
_SOURCE_NUMBER_PATTERN = re.compile(
    r"(?<![\w.])[-+]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?(?!\d)",
)
_DIMENSIONLESS_UNITS = frozenset({"dimensionless", "ratio", "unitless"})
_UNIT_ALIASES: Mapping[str, tuple[str, ...]] = {
    "percent": ("percent", "%"),
    "percentage": ("percentage", "percent", "%"),
}
_OBSERVATION_METADATA_FIELDS = frozenset(
    {
        "classification",
        "exon_or_intron",
        "genomic_position",
        "hgvs_cdna",
        "hgvs_genomic",
        "hgvs_protein",
        "inheritance",
        "transcript",
        "zygosity",
    },
)


class LLMIdentifierField(BaseModel):
    """A dynamic identifier whose lexical representation must remain a string."""

    key: str = Field(..., min_length=1, max_length=128)
    value: str = Field(..., min_length=1, max_length=512)

    model_config = ConfigDict(strict=True, extra="forbid")


class LLMLiteralField(BaseModel):
    """A nonnumeric literal field for metadata and rejected diagnostics."""

    key: str = Field(..., min_length=1, max_length=128)
    value: LLMLiteralValue

    model_config = ConfigDict(strict=True, extra="forbid")


def _fields_to_json_object(
    fields: list[LLMIdentifierField] | list[LLMLiteralField],
) -> JSONObject:
    """Convert LLM-safe key/value fields back into the service JSON shape."""
    payload: JSONObject = {}
    for field in fields:
        key = field.key.strip()
        if key == "":
            continue
        if key in payload:
            msg = f"Duplicate dynamic field key {key!r} is not allowed."
            raise ValueError(msg)
        payload[key] = cast("JSONValue", field.value)
    return payload


def _matching_measurements(*, text: str, value: float) -> tuple[re.Match[str], ...]:
    expected = Decimal(str(value))
    matches: list[re.Match[str]] = []
    for match in _SOURCE_NUMBER_PATTERN.finditer(text):
        try:
            candidate = Decimal(match.group(0).replace(",", ""))
        except InvalidOperation:
            continue
        if candidate == expected:
            matches.append(match)
    return tuple(matches)


def _measurement_has_literal_unit(
    *,
    text: str,
    match: re.Match[str],
    unit: str,
) -> bool:
    normalized_unit = unit.strip().casefold()
    if normalized_unit == "":
        return False
    if normalized_unit in _DIMENSIONLESS_UNITS:
        return True
    aliases = _UNIT_ALIASES.get(normalized_unit, (unit.strip(),))
    prefix = text[: match.start()]
    suffix = text[match.end() :]
    for alias in aliases:
        escaped_alias = re.escape(alias)
        if re.search(
            rf"(?<![\w/]){escaped_alias}\s*$",
            prefix,
            re.IGNORECASE,
        ):
            return True
        if re.match(
            rf"\s*{escaped_alias}(?![\w/])",
            suffix,
            re.IGNORECASE,
        ):
            return True
    return False


def _text_contains_measurement(
    *,
    text: str,
    value: float,
    unit: str | None = None,
) -> bool:
    matches = _matching_measurements(text=text, value=value)
    if unit is None:
        return bool(matches)
    return any(
        _measurement_has_literal_unit(text=text, match=match, unit=unit)
        for match in matches
    )


def observation_text_requires_source_measurement(value: str) -> bool:
    """Return whether an observation-like string contains a numeric literal."""
    return _SOURCE_NUMBER_PATTERN.search(value) is not None


class ExtractedObservation(BaseModel):
    """Validated observation mapped to an existing dictionary variable."""

    field_name: str = Field(..., min_length=1, max_length=128)
    variable_id: str = Field(..., min_length=1, max_length=64)
    value: JSONValue
    unit: str | None = Field(default=None, max_length=64)
    source_measurement: SourceMeasurementNumber | None = Field(
        default=None,
        description="Validated provenance retained when value is a source number.",
    )
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
    value: LLMObservationValue
    unit: str | None = Field(default=None, max_length=64)
    assessment: FactAssessment

    model_config = ConfigDict(strict=True, extra="forbid")

    def to_extracted_observation(
        self,
        *,
        expected_source_hash: str,
        source_values_by_locator: Mapping[str, JSONValue],
    ) -> ExtractedObservation:
        """Return the internal service observation contract."""
        if isinstance(self.value, SourceMeasurementNumber):
            measurement = self.value
            if measurement.source_hash != expected_source_hash:
                msg = "Numeric observation source_hash does not match request context."
                raise ValueError(msg)
            if measurement.source_locator not in source_values_by_locator:
                msg = "Numeric observation source_locator is absent from request context."
                raise ValueError(msg)
            source_value = source_values_by_locator[measurement.source_locator]
            source_text = source_value if isinstance(source_value, str) else str(source_value)
            if measurement.literal_span not in source_text:
                msg = "Numeric observation literal_span is absent from its source locator."
                raise ValueError(msg)
            if not _text_contains_measurement(
                text=measurement.literal_span,
                value=measurement.value,
                unit=measurement.unit,
            ):
                msg = (
                    "Numeric observation value and unit are absent from its "
                    "literal_span."
                )
                raise ValueError(msg)
            if not _text_contains_measurement(
                text=source_text,
                value=measurement.value,
                unit=measurement.unit,
            ):
                msg = (
                    "Numeric observation value and unit are absent from its "
                    "source locator."
                )
                raise ValueError(msg)
            if measurement.field_name != self.field_name:
                msg = "Numeric observation field_name does not match its envelope."
                raise ValueError(msg)
            if measurement.extraction_method != "literal_copy":
                msg = "Numeric observation extraction_method must be literal_copy."
                raise ValueError(msg)
            if measurement.unit != self.unit:
                msg = "Numeric observation unit does not match its envelope."
                raise ValueError(msg)
            return ExtractedObservation(
                field_name=self.field_name,
                variable_id=self.variable_id,
                value=measurement.value,
                unit=measurement.unit,
                source_measurement=measurement,
                assessment=self.assessment,
            )
        if isinstance(self.value, str) and observation_text_requires_source_measurement(
            self.value,
        ):
            msg = "Numeric observation text requires a source_measurement envelope."
            raise ValueError(msg)
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
    anchors: list[LLMIdentifierField] = Field(default_factory=list)
    metadata: list[LLMLiteralField] = Field(default_factory=list)
    evidence_excerpt: str = Field(..., min_length=1, max_length=1200)
    evidence_locator: str = Field(..., min_length=1, max_length=255)
    assessment: FactAssessment

    model_config = ConfigDict(strict=True, extra="forbid")

    @model_validator(mode="after")
    def reject_numeric_observation_metadata(
        self,
    ) -> LLMExtractedEntityCandidate:
        """Require numeric observation metadata to use the provenance envelope."""
        for field in self.metadata:
            if (
                field.key.strip() in _OBSERVATION_METADATA_FIELDS
                and isinstance(field.value, str)
                and observation_text_requires_source_measurement(field.value)
            ):
                msg = (
                    f"Numeric entity metadata {field.key!r} requires an explicit "
                    "source_measurement observation."
                )
                raise ValueError(msg)
        return self

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
    source_anchors: list[LLMIdentifierField] = Field(default_factory=list)
    target_anchors: list[LLMIdentifierField] = Field(default_factory=list)
    evidence_excerpt: str | None = Field(default=None, max_length=1200)
    evidence_locator: str | None = Field(default=None, max_length=255)
    assessment: FactAssessment

    model_config = ConfigDict(strict=True, extra="forbid")

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
    payload: list[LLMLiteralField] = Field(default_factory=list)
    assessment: FactAssessment | None = Field(default=None)

    model_config = ConfigDict(strict=True, extra="forbid")

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


class LLMExtractionContract(BaseModel):
    """OpenAI structured-output-safe contract for live variant extraction."""

    rationale: str
    evidence: list[ModelEvidenceCitation] = Field(default_factory=list)
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

    model_config = ConfigDict(strict=True, use_enum_values=True, extra="forbid")

    def to_extraction_contract(
        self,
        *,
        expected_source_hash: str,
        source_values_by_locator: Mapping[str, JSONValue],
    ) -> ExtractionContract:
        """Convert the LLM-safe schema into the internal service contract."""
        return ExtractionContract(
            rationale=self.rationale,
            evidence=[citation.to_legacy_evidence_item() for citation in self.evidence],
            decision=self.decision,
            source_type=self.source_type,
            document_id=self.document_id,
            entities=[
                entity.to_extracted_entity_candidate() for entity in self.entities
            ],
            observations=[
                observation.to_extracted_observation(
                    expected_source_hash=expected_source_hash,
                    source_values_by_locator=source_values_by_locator,
                )
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
    "LLMIdentifierField",
    "LLMLiteralField",
    "LLMRejectedFact",
    "RejectedFact",
    "observation_text_requires_source_measurement",
]
