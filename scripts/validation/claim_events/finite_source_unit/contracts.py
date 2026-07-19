"""Closed agent-output contracts for the finite source-unit diagnostic."""

from __future__ import annotations

from enum import StrEnum

from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimInventoryItem,  # noqa: TC002 - Pydantic resolves this model at runtime.
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SourceUnitDecision(StrEnum):
    """Agent decision about one deterministically supplied source location."""

    EXPLICIT_EVENT = "EXPLICIT_EVENT"
    NO_EVENT = "NO_EVENT"
    ABSTAIN = "ABSTAIN"


class SourceUnitEligibilityCategory(StrEnum):
    """Shared scientific-eligibility category returned by both agents."""

    FINDING = "FINDING"
    HYPOTHESIS = "HYPOTHESIS"
    NULL_RESULT = "NULL_RESULT"
    PROCEDURE = "PROCEDURE"
    MEASUREMENT_ONLY = "MEASUREMENT_ONLY"
    NO_EVENT = "NO_EVENT"
    ABSTAIN = "ABSTAIN"

    @property
    def scientific(self) -> bool:
        """Return whether the category describes relation-eligible science."""

        return self in {
            SourceUnitEligibilityCategory.FINDING,
            SourceUnitEligibilityCategory.HYPOTHESIS,
            SourceUnitEligibilityCategory.NULL_RESULT,
        }


class EntailmentDecision(StrEnum):
    """Independent source-only judgment for one bound event candidate."""

    ENTAILED = "ENTAILED"
    CONTRADICTED = "CONTRADICTED"
    INSUFFICIENT = "INSUFFICIENT"
    ABSTAIN = "ABSTAIN"


class SourceUnitCoverageDecision(StrEnum):
    """Independent inventory-coverage finding for one finite source unit."""

    CANDIDATES_COMPLETE = "CANDIDATES_COMPLETE"
    NO_EVENT_CONFIRMED = "NO_EVENT_CONFIRMED"
    MISSING_EVENT = "MISSING_EVENT"
    ABSTAIN = "ABSTAIN"


class EventStructureDecision(StrEnum):
    """Whether one candidate preserves the complete source event structure."""

    COMPLETE = "COMPLETE"
    LOSSY = "LOSSY"
    INVALID = "INVALID"
    ABSTAIN = "ABSTAIN"


class DirectionEncodingDecision(StrEnum):
    """Whether material effect direction is machine-readable in the event type."""

    STRUCTURED = "STRUCTURED"
    SOURCE_ONLY = "SOURCE_ONLY"
    CONFLICT = "CONFLICT"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    ABSTAIN = "ABSTAIN"


class SemanticValidityDecision(StrEnum):
    """Categorical validity of one event or argument semantic assignment."""

    VALID = "VALID"
    INVALID = "INVALID"
    ABSTAIN = "ABSTAIN"


class ProjectionEligibilityDecision(StrEnum):
    """Categorical trust routing after entailment and structure review."""

    ELIGIBLE = "ELIGIBLE"
    REVIEW_ONLY = "REVIEW_ONLY"
    REJECT = "REJECT"
    ABSTAIN = "ABSTAIN"


class SourceUnitExtractionOutput(BaseModel):
    """Scientific extraction result bound to a unit outside model output."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    eligibility_category: SourceUnitEligibilityCategory = Field(..., strict=False)
    decision: SourceUnitDecision = Field(..., strict=False)
    events: tuple[ClaimInventoryItem, ...] = Field(default=(), max_length=16)
    reasoning: str = Field(..., min_length=1, max_length=4000)

    @field_validator("events", mode="before")
    @classmethod
    def freeze_events(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def require_decision_payload_consistency(self) -> SourceUnitExtractionOutput:
        expected_decision = (
            SourceUnitDecision.EXPLICIT_EVENT
            if self.eligibility_category.scientific
            else (
                SourceUnitDecision.ABSTAIN
                if self.eligibility_category is SourceUnitEligibilityCategory.ABSTAIN
                else SourceUnitDecision.NO_EVENT
            )
        )
        if self.decision is not expected_decision:
            raise ValueError(
                "extraction decision must match the eligibility category",
            )
        if self.decision is SourceUnitDecision.EXPLICIT_EVENT and not self.events:
            raise ValueError("EXPLICIT_EVENT requires at least one event")
        if self.decision is not SourceUnitDecision.EXPLICIT_EVENT and self.events:
            raise ValueError("NO_EVENT and ABSTAIN cannot contain events")
        return self


class CandidateArgumentSemanticVerification(BaseModel):
    """Ordered biomedical type and event-role review for one argument."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    type_decision: SemanticValidityDecision = Field(..., strict=False)
    event_role_decision: SemanticValidityDecision = Field(..., strict=False)
    reasoning: str = Field(..., min_length=1, max_length=2000)


class CandidateVerification(BaseModel):
    """One categorical verification paired to its candidate by input order."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    decision: EntailmentDecision = Field(..., strict=False)
    structure_decision: EventStructureDecision = Field(..., strict=False)
    direction_encoding: DirectionEncodingDecision = Field(..., strict=False)
    event_type_decision: SemanticValidityDecision = Field(..., strict=False)
    argument_semantic_decisions: tuple[CandidateArgumentSemanticVerification, ...] = (
        Field(
            ...,
            min_length=2,
            max_length=32,
        )
    )
    projection_eligibility: ProjectionEligibilityDecision = Field(..., strict=False)
    evidence_spans: tuple[str, ...] = Field(default=(), max_length=16)
    reasoning: str = Field(..., min_length=1, max_length=4000)
    falsification_condition: str = Field(..., min_length=1, max_length=4000)

    @field_validator("evidence_spans", mode="before")
    @classmethod
    def freeze_evidence_spans(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("argument_semantic_decisions", mode="before")
    @classmethod
    def freeze_argument_semantic_decisions(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("evidence_spans")
    @classmethod
    def require_nonempty_unique_spans(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if any(not span.strip() for span in value):
            raise ValueError("verification evidence spans must be nonempty")
        if len(set(value)) != len(value):
            raise ValueError("verification evidence spans must be unique")
        return value

    @model_validator(mode="after")
    def require_evidence_for_decisive_findings(self) -> CandidateVerification:
        if (
            self.decision
            in {
                EntailmentDecision.ENTAILED,
                EntailmentDecision.CONTRADICTED,
            }
            and not self.evidence_spans
        ):
            raise ValueError("decisive verification requires exact evidence spans")
        invalid_semantics = (
            self.event_type_decision is SemanticValidityDecision.INVALID
            or any(
                item.type_decision is SemanticValidityDecision.INVALID
                or item.event_role_decision is SemanticValidityDecision.INVALID
                for item in self.argument_semantic_decisions
            )
        )
        unresolved_semantics = (
            self.event_type_decision is SemanticValidityDecision.ABSTAIN
            or any(
                item.type_decision is SemanticValidityDecision.ABSTAIN
                or item.event_role_decision is SemanticValidityDecision.ABSTAIN
                for item in self.argument_semantic_decisions
            )
        )
        invalid_trust_signal = (
            self.structure_decision is EventStructureDecision.INVALID
            or self.direction_encoding is DirectionEncodingDecision.CONFLICT
            or invalid_semantics
        )
        if (
            invalid_trust_signal
            and self.projection_eligibility is not ProjectionEligibilityDecision.REJECT
        ):
            raise ValueError("invalid trust signals require REJECT")
        if self.projection_eligibility is ProjectionEligibilityDecision.ELIGIBLE:
            if not self.trusted_projection_eligible:
                raise ValueError(
                    "ELIGIBLE requires entailed, complete, typed structured evidence",
                )
        elif self.projection_eligibility is ProjectionEligibilityDecision.REVIEW_ONLY:
            review_reason = (
                self.decision is EntailmentDecision.ENTAILED
                and not invalid_trust_signal
                and (
                    self.structure_decision
                    in {EventStructureDecision.LOSSY, EventStructureDecision.ABSTAIN}
                    or self.direction_encoding
                    in {
                        DirectionEncodingDecision.SOURCE_ONLY,
                        DirectionEncodingDecision.ABSTAIN,
                    }
                    or unresolved_semantics
                )
            )
            if not review_reason:
                raise ValueError("REVIEW_ONLY requires a non-invalid trust blocker")
        elif self.projection_eligibility is ProjectionEligibilityDecision.REJECT:
            rejection_reason = (
                self.decision
                in {
                    EntailmentDecision.CONTRADICTED,
                    EntailmentDecision.INSUFFICIENT,
                }
                or self.structure_decision is EventStructureDecision.INVALID
                or self.direction_encoding is DirectionEncodingDecision.CONFLICT
                or invalid_semantics
            )
            if not rejection_reason:
                raise ValueError("REJECT requires contradiction or invalid structure")
        elif not (
            self.decision is EntailmentDecision.ABSTAIN
            or self.structure_decision is EventStructureDecision.ABSTAIN
            or self.direction_encoding is DirectionEncodingDecision.ABSTAIN
            or unresolved_semantics
        ):
            raise ValueError("ABSTAIN requires an unresolved categorical judgment")
        return self

    @property
    def trusted_projection_eligible(self) -> bool:
        """Return deterministic eligibility from categorical agent findings."""

        return (
            self.decision is EntailmentDecision.ENTAILED
            and self.structure_decision is EventStructureDecision.COMPLETE
            and self.direction_encoding
            in {
                DirectionEncodingDecision.STRUCTURED,
                DirectionEncodingDecision.NOT_APPLICABLE,
            }
            and self.event_type_decision is SemanticValidityDecision.VALID
            and all(
                item.type_decision is SemanticValidityDecision.VALID
                and item.event_role_decision is SemanticValidityDecision.VALID
                for item in self.argument_semantic_decisions
            )
        )


class SourceUnitVerificationOutput(BaseModel):
    """Ordered scientific verification results without transport identity."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    eligibility_category: SourceUnitEligibilityCategory = Field(..., strict=False)
    coverage_decision: SourceUnitCoverageDecision = Field(..., strict=False)
    coverage_reasoning: str = Field(..., min_length=1, max_length=4000)
    decisions: tuple[CandidateVerification, ...] = Field(default=(), max_length=16)

    @field_validator("decisions", mode="before")
    @classmethod
    def freeze_decisions(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def bind_coverage_to_entailed_candidates(self) -> SourceUnitVerificationOutput:
        entailed_count = sum(
            decision.decision is EntailmentDecision.ENTAILED
            for decision in self.decisions
        )
        if (
            self.coverage_decision is SourceUnitCoverageDecision.CANDIDATES_COMPLETE
            and entailed_count == 0
        ):
            raise ValueError("CANDIDATES_COMPLETE requires an ENTAILED candidate")
        if (
            self.coverage_decision is SourceUnitCoverageDecision.NO_EVENT_CONFIRMED
            and entailed_count > 0
        ):
            raise ValueError("NO_EVENT_CONFIRMED cannot contain ENTAILED candidates")
        if (
            self.eligibility_category is SourceUnitEligibilityCategory.ABSTAIN
            and entailed_count > 0
        ):
            raise ValueError("ABSTAIN cannot contain ENTAILED candidates")
        if self.eligibility_category.scientific:
            allowed_coverage = {
                SourceUnitCoverageDecision.CANDIDATES_COMPLETE,
                SourceUnitCoverageDecision.MISSING_EVENT,
            }
        elif self.eligibility_category is SourceUnitEligibilityCategory.ABSTAIN:
            allowed_coverage = {SourceUnitCoverageDecision.ABSTAIN}
        else:
            allowed_coverage = {SourceUnitCoverageDecision.NO_EVENT_CONFIRMED}
        if self.coverage_decision not in allowed_coverage:
            raise ValueError(
                "verification coverage must match the eligibility category",
            )
        return self


__all__ = [
    "CandidateArgumentSemanticVerification",
    "CandidateVerification",
    "DirectionEncodingDecision",
    "EntailmentDecision",
    "EventStructureDecision",
    "ProjectionEligibilityDecision",
    "SemanticValidityDecision",
    "SourceUnitCoverageDecision",
    "SourceUnitDecision",
    "SourceUnitEligibilityCategory",
    "SourceUnitExtractionOutput",
    "SourceUnitVerificationOutput",
]
