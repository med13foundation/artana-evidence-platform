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


class SourceUnitExtractionOutput(BaseModel):
    """Categorical extraction result for exactly one frozen source unit."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    unit_id: str = Field(..., min_length=1, max_length=300)
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
                if self.eligibility_category
                is SourceUnitEligibilityCategory.ABSTAIN
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


class CandidateVerification(BaseModel):
    """One categorical verification bound to a stable candidate identity."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    candidate_id: str = Field(..., min_length=1, max_length=300)
    decision: EntailmentDecision = Field(..., strict=False)
    evidence_spans: tuple[str, ...] = Field(default=(), max_length=16)
    reasoning: str = Field(..., min_length=1, max_length=4000)
    falsification_condition: str = Field(..., min_length=1, max_length=4000)

    @field_validator("evidence_spans", mode="before")
    @classmethod
    def freeze_evidence_spans(cls, value: object) -> object:
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
        if self.decision in {
            EntailmentDecision.ENTAILED,
            EntailmentDecision.CONTRADICTED,
        } and not self.evidence_spans:
            raise ValueError("decisive verification requires exact evidence spans")
        return self


class SourceUnitVerificationOutput(BaseModel):
    """Independent verification results for every supplied candidate."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    unit_id: str = Field(..., min_length=1, max_length=300)
    eligibility_category: SourceUnitEligibilityCategory = Field(..., strict=False)
    coverage_decision: SourceUnitCoverageDecision = Field(..., strict=False)
    coverage_reasoning: str = Field(..., min_length=1, max_length=4000)
    covered_candidate_ids: tuple[str, ...] = Field(default=(), max_length=16)
    decisions: tuple[CandidateVerification, ...] = Field(default=(), max_length=16)

    @field_validator("covered_candidate_ids", mode="before")
    @classmethod
    def freeze_covered_candidate_ids(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("covered_candidate_ids")
    @classmethod
    def require_unique_covered_candidate_ids(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if any(not candidate_id.strip() for candidate_id in value):
            raise ValueError("covered candidate IDs must be nonempty")
        if len(set(value)) != len(value):
            raise ValueError("covered candidate IDs must be unique")
        return value

    @field_validator("decisions", mode="before")
    @classmethod
    def freeze_decisions(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("decisions")
    @classmethod
    def require_unique_candidate_ids(
        cls,
        value: tuple[CandidateVerification, ...],
    ) -> tuple[CandidateVerification, ...]:
        ids = tuple(decision.candidate_id for decision in value)
        if len(set(ids)) != len(ids):
            raise ValueError("verification candidate IDs must be unique")
        return value

    @model_validator(mode="after")
    def bind_coverage_to_entailed_candidates(self) -> SourceUnitVerificationOutput:
        entailed_ids = {
            decision.candidate_id
            for decision in self.decisions
            if decision.decision is EntailmentDecision.ENTAILED
        }
        if set(self.covered_candidate_ids) != entailed_ids:
            raise ValueError("covered candidate IDs must equal ENTAILED candidates")
        if (
            self.coverage_decision is SourceUnitCoverageDecision.CANDIDATES_COMPLETE
            and not entailed_ids
        ):
            raise ValueError("CANDIDATES_COMPLETE requires an ENTAILED candidate")
        if (
            self.coverage_decision is SourceUnitCoverageDecision.NO_EVENT_CONFIRMED
            and entailed_ids
        ):
            raise ValueError("NO_EVENT_CONFIRMED cannot contain ENTAILED candidates")
        if (
            self.eligibility_category is SourceUnitEligibilityCategory.ABSTAIN
            and entailed_ids
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
    "CandidateVerification",
    "EntailmentDecision",
    "SourceUnitCoverageDecision",
    "SourceUnitDecision",
    "SourceUnitEligibilityCategory",
    "SourceUnitExtractionOutput",
    "SourceUnitVerificationOutput",
]
