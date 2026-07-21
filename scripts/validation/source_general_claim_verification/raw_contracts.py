"""Strict contracts for the sealed source-only adjudicator artifacts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Decision = Literal["ADJUDICATED", "AMBIGUOUS", "ABSTAIN"]
EventType = Literal[
    "OBSERVATION",
    "ASSOCIATION",
    "COMPARISON",
    "INTERACTION",
    "REGULATION",
    "INTERVENTION_EFFECT",
    "PRODUCTION",
    "QUANTIFICATION",
    "SAFETY_OUTCOME",
    "CLINICAL_OUTCOME",
    "HYPOTHESIS",
]
ParticipantRole = Literal[
    "AGENT",
    "THEME",
    "TARGET",
    "CAUSE",
    "EFFECT",
    "POPULATION",
    "INTERVENTION",
    "COMPARATOR",
    "OUTCOME",
    "CONDITION",
    "VARIANT",
    "GENE_OR_PROTEIN",
    "MEASUREMENT",
    "CONTEXT",
    "SITE",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RawParticipant(StrictModel):
    exact_span: str = Field(min_length=1)
    role: ParticipantRole


class RawComparison(StrictModel):
    status: Literal["PRESENT", "NOT_APPLICABLE"]
    relation: Literal[
        "GREATER",
        "LESS",
        "EQUAL",
        "NO_DIFFERENCE",
        "MIXED",
        "NOT_APPLICABLE",
    ]
    lhs_exact_span: str | None
    rhs_exact_span: str | None


class RawQuantity(StrictModel):
    type: Literal["PERCENTAGE", "COUNT", "DOSE", "YIELD", "FOLD_CHANGE", "OTHER"]
    exact_span: str = Field(min_length=1)


class RawStatisticalObservation(StrictModel):
    type: Literal["P_VALUE", "CONFIDENCE_INTERVAL", "EFFECT_ESTIMATE", "NONE"]
    exact_spans: tuple[str, ...]


class RawModifier(StrictModel):
    type: Literal[
        "POPULATION",
        "CONTEXT",
        "TIMEFRAME",
        "DOSE",
        "LOCATION",
        "MECHANISM",
        "COMPARISON",
        "UNCERTAINTY",
        "OTHER",
    ]
    exact_span: str = Field(min_length=1)


class RawAdjudicationPacket(StrictModel):
    scope_id: str = Field(min_length=1)
    source_label: str = Field(min_length=1)
    decision: Decision
    exact_passage: str = Field(min_length=1)
    passage_start: int = Field(ge=0)
    passage_end: int = Field(gt=0)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    event_type: EventType
    complete_event: str = Field(min_length=1)
    participants: tuple[RawParticipant, ...]
    direction: Literal[
        "INCREASED",
        "DECREASED",
        "EQUAL_OR_SIMILAR",
        "NO_DIFFERENCE",
        "POSITIVE_ASSOCIATION",
        "NEGATIVE_ASSOCIATION",
        "NO_ASSOCIATION",
        "PRODUCED",
        "INTERACTS",
        "ENABLES",
        "OBSERVED",
        "NOT_APPLICABLE",
    ]
    comparison: RawComparison
    polarity: Literal["POSITIVE", "NEGATED", "NULL_RESULT"]
    uncertainty: Literal["ASSERTED", "PROVISIONAL", "UNCERTAIN", "HYPOTHESIS"]
    quantitative_evidence: tuple[RawQuantity, ...]
    statistical_observation: RawStatisticalObservation
    author_interpretation: Literal[
        "SIGNIFICANT",
        "NOT_SIGNIFICANT",
        "NOT_CLAIMED",
    ]
    required_modifiers: tuple[RawModifier, ...]
    completeness: Literal["COMPLETE", "INCOMPLETE", "AMBIGUOUS"]
    acceptable_equivalent_evidence_spans: tuple[str, ...]
    ambiguity_conditions: tuple[str, ...]
    evidence_spans: tuple[str, ...] = Field(min_length=1)
    short_explanation: str = Field(min_length=1)


class RawAdjudicationBatch(StrictModel):
    reviewer_model: Literal["gpt-5.6-sol"]
    reviewer_kind: Literal[
        "codex_subagent_source_only",
        "codex_subagent_source_only_tiebreak",
    ]
    scope_count: int = Field(ge=1, le=31)
    packets: tuple[RawAdjudicationPacket, ...] = Field(min_length=1, max_length=31)


__all__ = ["RawAdjudicationBatch", "RawAdjudicationPacket"]
