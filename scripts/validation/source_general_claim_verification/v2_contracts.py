"""Corrected offset-bound contracts for one atomic exposed-source event."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceSpan(StrictModel):
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_length(self) -> EvidenceSpan:
        if self.end - self.start != len(self.text):
            raise ValueError("evidence offsets must equal text length")
        return self


class Participant(StrictModel):
    evidence: EvidenceSpan
    role: Literal[
        "PRIMARY_SUBJECT",
        "PRIMARY_OBJECT",
        "INTERVENTION",
        "COMPARATOR",
        "POPULATION",
        "OUTCOME",
        "VARIANT",
        "GENE_OR_PROTEIN",
        "CONDITION",
        "SECONDARY_PARTICIPANT",
        "CONTEXT",
        "SITE",
    ]


class Comparison(StrictModel):
    relation: Literal[
        "GREATER_THAN",
        "LESS_THAN",
        "EQUAL_OR_SIMILAR",
        "NO_DIFFERENCE",
        "DIFFERENT_FROM",
        "NOT_APPLICABLE",
    ]
    evidence: EvidenceSpan | None
    left: EvidenceSpan | None
    right: EvidenceSpan | None


class QuantitativeEvidence(StrictModel):
    kind: Literal["COUNT", "PERCENTAGE", "DOSE", "YIELD", "FOLD_CHANGE", "OTHER"]
    evidence: EvidenceSpan


class StatisticalEvidence(StrictModel):
    kind: Literal["P_VALUE", "CONFIDENCE_INTERVAL", "EFFECT_ESTIMATE"]
    evidence: EvidenceSpan


class Modifier(StrictModel):
    axis: Literal[
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
    evidence: EvidenceSpan


class AtomicClaim(StrictModel):
    event_type: Literal[
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
    event_evidence: EvidenceSpan
    participants: tuple[Participant, ...] = Field(min_length=1)
    direction: Literal[
        "INCREASED",
        "DECREASED",
        "UNCHANGED",
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
    direction_evidence: EvidenceSpan
    comparison: Comparison
    polarity: Literal["AFFIRMED", "NEGATED", "NULL_RESULT"]
    polarity_evidence: EvidenceSpan
    uncertainty: Literal["ASSERTED", "PROVISIONAL", "UNCERTAIN", "HYPOTHESIS"]
    uncertainty_evidence: EvidenceSpan
    quantitative_evidence: tuple[QuantitativeEvidence, ...]
    statistical_evidence: tuple[StatisticalEvidence, ...]
    author_interpretation: Literal[
        "SIGNIFICANT",
        "NOT_SIGNIFICANT",
        "NOT_CLAIMED",
    ]
    author_interpretation_evidence: EvidenceSpan | None
    required_modifiers: tuple[Modifier, ...]
    completeness: Literal["COMPLETE"]
    acceptable_equivalent_evidence: tuple[EvidenceSpan, ...]
    explanation: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_explicit_author_interpretation(self) -> AtomicClaim:
        explicit = self.author_interpretation in {
            "SIGNIFICANT",
            "NOT_SIGNIFICANT",
        }
        if explicit != (self.author_interpretation_evidence is not None):
            raise ValueError("author interpretation requires explicit evidence")
        return self


class AdjudicationPacket(StrictModel):
    scope_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["ADJUDICATED", "AMBIGUOUS", "ABSTAIN"]
    ambiguity_reason: Literal[
        "NONE",
        "BUNDLED_EVENTS",
        "FRAGMENT_MISSING_CONTEXT",
        "OVERLAPPING_SCOPE",
        "ROLE_UNRESOLVED",
        "EVENT_BOUNDARY_UNRESOLVED",
        "OTHER",
    ]
    scope_evidence: EvidenceSpan
    claim: AtomicClaim | None
    explanation: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_decision_shape(self) -> AdjudicationPacket:
        if self.decision == "ADJUDICATED":
            if self.claim is None or self.ambiguity_reason != "NONE":
                raise ValueError("adjudicated packets require one unambiguous claim")
        elif self.claim is not None or self.ambiguity_reason == "NONE":
            raise ValueError("excluded packets require a categorical ambiguity reason")
        return self


class AdjudicationBatch(StrictModel):
    schema_version: Literal["source_general_claim_verification.adjudication.v2"]
    reviewer_model: Literal["gpt-5.6-sol"]
    reviewer_role: Literal["FIRST", "SECOND", "TIEBREAKER"]
    packets: tuple[AdjudicationPacket, ...] = Field(min_length=1, max_length=31)


JSONValue = Annotated[object, Field()]


__all__ = [
    "AdjudicationBatch",
    "AdjudicationPacket",
    "AtomicClaim",
    "EvidenceSpan",
]
