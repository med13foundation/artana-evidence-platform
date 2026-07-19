"""Closed categorical contracts for lossless scientific-event normalization."""

from __future__ import annotations

from enum import StrEnum

from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimInventoryItem,
    InventoryAssertionScope,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from scripts.validation.claim_events.finite_source_unit.contracts import (
    EntailmentDecision,
    SourceUnitEligibilityCategory,
)
from scripts.validation.claim_events.finite_source_unit.normalization.context_dimensions import (
    ContextDimension,
)


class NormalizationFamily(StrEnum):
    """Public production representation chosen without benchmark gold."""

    DIRECT = "DIRECT"
    NESTED = "NESTED"
    ABSTAIN = "ABSTAIN"


class NormalizationOperation(StrEnum):
    """Categorical relationship between source and normalized events."""

    UNCHANGED = "UNCHANGED"
    REFRAME = "REFRAME"
    SPLIT = "SPLIT"
    MERGE = "MERGE"


class NormalizationAbstentionReason(StrEnum):
    """Closed reason a lossless production representation was not selected."""

    NONE = "NONE"
    SOURCE_AMBIGUOUS = "SOURCE_AMBIGUOUS"
    NO_LOSSLESS_FAMILY = "NO_LOSSLESS_FAMILY"
    UNRESOLVED_CAUSALITY = "UNRESOLVED_CAUSALITY"
    UNRESOLVED_SCOPE = "UNRESOLVED_SCOPE"
    UNRESOLVED_TYPING = "UNRESOLVED_TYPING"


class NormalizedEventMapping(BaseModel):
    """One normalized event mapped to source-extraction positions."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    normalized_event_position: int = Field(..., ge=0)
    source_event_positions: tuple[int, ...] = Field(..., min_length=1, max_length=16)
    operation: NormalizationOperation = Field(..., strict=False)
    reasoning: str = Field(..., min_length=1, max_length=3000)
    falsification_condition: str = Field(..., min_length=1, max_length=3000)

    @field_validator("source_event_positions", mode="before")
    @classmethod
    def freeze_source_positions(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("source_event_positions")
    @classmethod
    def require_unique_source_positions(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if len(set(value)) != len(value):
            raise ValueError("mapping source-event positions must be unique")
        return value


class SourceUnitNormalizationOutput(BaseModel):
    """Agent-authored representation that preserves the original extraction."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    eligibility_category: SourceUnitEligibilityCategory = Field(..., strict=False)
    family: NormalizationFamily = Field(..., strict=False)
    abstention_reason: NormalizationAbstentionReason = Field(..., strict=False)
    events: tuple[ClaimInventoryItem, ...] = Field(default=(), max_length=16)
    mappings: tuple[NormalizedEventMapping, ...] = Field(default=(), max_length=16)
    context_dimensions: tuple[ContextDimension, ...] = Field(default=(), max_length=16)
    reasoning: str = Field(..., min_length=1, max_length=4000)
    falsification_condition: str = Field(..., min_length=1, max_length=4000)

    @field_validator("events", "mappings", "context_dimensions", mode="before")
    @classmethod
    def freeze_sequences(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def require_family_consistency(self) -> SourceUnitNormalizationOutput:
        if self.family is NormalizationFamily.ABSTAIN:
            if self.events or self.mappings or self.context_dimensions:
                raise ValueError(
                    "ABSTAIN cannot contain normalized events, mappings, or context dimensions"
                )
            if self.abstention_reason is NormalizationAbstentionReason.NONE:
                raise ValueError("ABSTAIN requires a categorical reason")
            return self
        if self.abstention_reason is not NormalizationAbstentionReason.NONE:
            raise ValueError(
                "selected normalization family requires NONE abstention reason"
            )
        if not self.events or len(self.mappings) != len(self.events):
            raise ValueError(
                "selected family requires one mapping per normalized event"
            )
        if tuple(
            mapping.normalized_event_position for mapping in self.mappings
        ) != tuple(range(len(self.events))):
            raise ValueError("normalized-event mappings must be ordered and exhaustive")
        nested_markers = tuple(
            event.assertion_scope is InventoryAssertionScope.CONTROLLED_TARGET
            or any(argument.controlled_event_ref for argument in event.arguments)
            for event in self.events
        )
        if self.family is NormalizationFamily.DIRECT and any(nested_markers):
            raise ValueError("DIRECT cannot contain controlled-event structure")
        if self.family is NormalizationFamily.NESTED and not (
            any(
                event.assertion_scope is InventoryAssertionScope.CONTROLLED_TARGET
                for event in self.events
            )
            and any(
                argument.controlled_event_ref
                for event in self.events
                for argument in event.arguments
            )
        ):
            raise ValueError(
                "NESTED requires a controlled target and explicit reference"
            )
        return self


class MaterialAxis(StrEnum):
    """Scientific dimensions that must survive normalization."""

    EVENT_INVENTORY = "EVENT_INVENTORY"
    EVENT_TYPE = "EVENT_TYPE"
    DIRECTION = "DIRECTION"
    POLARITY = "POLARITY"
    PARTICIPANTS = "PARTICIPANTS"
    CAUSAL_ROLES = "CAUSAL_ROLES"
    CONTEXT_SCOPE = "CONTEXT_SCOPE"
    ASSERTION_EPISTEMIC_SCOPE = "ASSERTION_EPISTEMIC_SCOPE"
    CONTROLLED_EVENT_TOPOLOGY = "CONTROLLED_EVENT_TOPOLOGY"
    REFERENT_RESOLUTION = "REFERENT_RESOLUTION"


class MaterialAxisDecision(StrEnum):
    """Categorical comparison between original and normalized meaning."""

    PRESERVED = "PRESERVED"
    COMPATIBLE_REFINEMENT = "COMPATIBLE_REFINEMENT"
    MATERIAL_LOSS = "MATERIAL_LOSS"
    MATERIAL_ADDITION = "MATERIAL_ADDITION"
    CONTRADICTION = "CONTRADICTION"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    ABSTAIN = "ABSTAIN"


class CueAlignmentDecision(StrEnum):
    """Separate surface wording from scientific predicate mismatch."""

    EXACT = "EXACT"
    SURFACE_EQUIVALENT = "SURFACE_EQUIVALENT"
    MATERIAL_MISMATCH = "MATERIAL_MISMATCH"
    ABSTAIN = "ABSTAIN"


class PresenceDecision(StrEnum):
    """Closed presence judgment used by deterministic gates."""

    ABSENT = "ABSENT"
    PRESENT = "PRESENT"
    ABSTAIN = "ABSTAIN"


class FamilyValidityDecision(StrEnum):
    """Whether normalized output uses exactly one declared family."""

    VALID = "VALID"
    INVALID = "INVALID"
    ABSTAIN = "ABSTAIN"


class InventoryCoverageDecision(StrEnum):
    """Whole-inventory preservation judgment."""

    COMPLETE = "COMPLETE"
    MISSING_EVENT = "MISSING_EVENT"
    EXTRA_EVENT = "EXTRA_EVENT"
    MISSING_AND_EXTRA = "MISSING_AND_EXTRA"
    ABSTAIN = "ABSTAIN"


class AxisReview(BaseModel):
    """One categorical material-axis judgment with falsification evidence."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    axis: MaterialAxis = Field(..., strict=False)
    decision: MaterialAxisDecision = Field(..., strict=False)
    evidence_spans: tuple[str, ...] = Field(default=(), max_length=16)
    reasoning: str = Field(..., min_length=1, max_length=3000)
    falsification_condition: str = Field(..., min_length=1, max_length=3000)

    @field_validator("evidence_spans", mode="before")
    @classmethod
    def freeze_evidence_spans(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("evidence_spans")
    @classmethod
    def require_unique_evidence_spans(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not span.strip() for span in value) or len(set(value)) != len(value):
            raise ValueError("axis evidence spans must be nonempty and unique")
        return value

    @model_validator(mode="after")
    def require_evidence_for_decisive_axis(self) -> AxisReview:
        if (
            self.decision
            not in {
                MaterialAxisDecision.NOT_APPLICABLE,
                MaterialAxisDecision.ABSTAIN,
            }
            and not self.evidence_spans
        ):
            raise ValueError("decisive material-axis review requires source evidence")
        return self


class NormalizedCandidateReview(BaseModel):
    """Ordered source-entailment review for one normalized event."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    normalized_event_position: int = Field(..., ge=0)
    source_entailment: EntailmentDecision = Field(..., strict=False)
    evidence_spans: tuple[str, ...] = Field(default=(), max_length=16)
    reasoning: str = Field(..., min_length=1, max_length=3000)
    falsification_condition: str = Field(..., min_length=1, max_length=3000)

    @field_validator("evidence_spans", mode="before")
    @classmethod
    def freeze_evidence_spans(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("evidence_spans")
    @classmethod
    def require_unique_evidence_spans(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not span.strip() for span in value) or len(set(value)) != len(value):
            raise ValueError(
                "candidate-review evidence spans must be nonempty and unique"
            )
        return value

    @model_validator(mode="after")
    def require_decisive_evidence(self) -> NormalizedCandidateReview:
        if (
            self.source_entailment
            in {
                EntailmentDecision.ENTAILED,
                EntailmentDecision.CONTRADICTED,
            }
            and not self.evidence_spans
        ):
            raise ValueError("decisive candidate review requires source evidence")
        return self


class SourceUnitNormalizedReviewOutput(BaseModel):
    """Independent categorical review of original and normalized structures."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    eligibility_category: SourceUnitEligibilityCategory = Field(..., strict=False)
    inventory_coverage: InventoryCoverageDecision = Field(..., strict=False)
    unsupported_additions: PresenceDecision = Field(..., strict=False)
    family_validity: FamilyValidityDecision = Field(..., strict=False)
    cue_alignment: CueAlignmentDecision = Field(..., strict=False)
    axis_reviews: tuple[AxisReview, ...] = Field(..., min_length=10, max_length=10)
    candidate_reviews: tuple[NormalizedCandidateReview, ...] = Field(
        default=(), max_length=16
    )
    reasoning: str = Field(..., min_length=1, max_length=4000)
    falsification_condition: str = Field(..., min_length=1, max_length=4000)

    @field_validator("axis_reviews", "candidate_reviews", mode="before")
    @classmethod
    def freeze_sequences(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def require_complete_ordered_review(self) -> SourceUnitNormalizedReviewOutput:
        if tuple(review.axis for review in self.axis_reviews) != tuple(MaterialAxis):
            raise ValueError(
                "axis reviews must cover every material axis in enum order"
            )
        if tuple(
            review.normalized_event_position for review in self.candidate_reviews
        ) != tuple(range(len(self.candidate_reviews))):
            raise ValueError("candidate reviews must be ordered and exhaustive")
        return self


__all__ = [
    "AxisReview",
    "CueAlignmentDecision",
    "ContextDimension",
    "FamilyValidityDecision",
    "InventoryCoverageDecision",
    "MaterialAxis",
    "MaterialAxisDecision",
    "NormalizationAbstentionReason",
    "NormalizationFamily",
    "NormalizationOperation",
    "NormalizedCandidateReview",
    "NormalizedEventMapping",
    "PresenceDecision",
    "SourceUnitNormalizationOutput",
    "SourceUnitNormalizedReviewOutput",
]
