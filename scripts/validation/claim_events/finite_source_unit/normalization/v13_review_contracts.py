"""V13-v6 categorical review contract for experimental context dimensions."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
    SourceUnitNormalizedReviewOutput,
)


class ContextFactorEligibilityDecision(StrEnum):
    """Whether one proposed factor is explicit and scientifically eligible."""

    EXPLICIT_MULTI_LEVEL_FACTOR = "EXPLICIT_MULTI_LEVEL_FACTOR"
    PARTICIPANT_ONLY = "PARTICIPANT_ONLY"
    IMPLICIT_OR_INFERRED = "IMPLICIT_OR_INFERRED"
    ABSTAIN = "ABSTAIN"


class ContextLevelSetDecision(StrEnum):
    """Whether proposed levels are one explicit mutually exclusive set."""

    SAME_FACTOR_MUTUALLY_EXCLUSIVE = "SAME_FACTOR_MUTUALLY_EXCLUSIVE"
    MIXED_OR_UNRELATED = "MIXED_OR_UNRELATED"
    SERIES_OR_OVERLAPPING = "SERIES_OR_OVERLAPPING"
    IMPLICIT_OR_INFERRED = "IMPLICIT_OR_INFERRED"
    ABSTAIN = "ABSTAIN"


class ContextScopeDecision(StrEnum):
    """Whether the source applies the level contrast to the referenced events."""

    SOURCE_EXPLICIT = "SOURCE_EXPLICIT"
    UNSUPPORTED = "UNSUPPORTED"
    ABSTAIN = "ABSTAIN"


class ContextCrossingDecision(StrEnum):
    """Whether crossed-factor edges are explicit and correctly paired."""

    SOURCE_EXPLICIT = "SOURCE_EXPLICIT"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNSUPPORTED = "UNSUPPORTED"
    ABSTAIN = "ABSTAIN"


class ContextDimensionDecision(StrEnum):
    """Independent source-only disposition for one proposed dimension."""

    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    ABSTAIN = "ABSTAIN"


class ContextLevelMembershipDecision(StrEnum):
    """Whether one proposed level belongs to the reviewed source factor."""

    SAME_FACTOR_LEVEL = "SAME_FACTOR_LEVEL"
    UNRELATED_OR_MIXED = "UNRELATED_OR_MIXED"
    IMPLICIT_OR_INFERRED = "IMPLICIT_OR_INFERRED"
    ABSTAIN = "ABSTAIN"


class ContextLevelReview(BaseModel):
    """Identity-bound source evidence for one proposed factor level."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    level_position: int = Field(..., ge=0)
    level_span: str = Field(..., min_length=1, max_length=1000)
    membership: ContextLevelMembershipDecision = Field(..., strict=False)
    evidence_spans: tuple[str, ...] = Field(..., min_length=1, max_length=8)
    reasoning: str = Field(..., min_length=1, max_length=3000)
    falsification_condition: str = Field(..., min_length=1, max_length=3000)

    @field_validator("evidence_spans", mode="before")
    @classmethod
    def freeze_evidence_spans(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def require_ordered_level_evidence(self) -> ContextLevelReview:
        if any(not span.strip() for span in self.evidence_spans) or len(
            set(self.evidence_spans)
        ) != len(self.evidence_spans):
            raise ValueError("level evidence spans must be nonempty and unique")
        return self


class ContextDimensionReview(BaseModel):
    """Ordered categorical adjudication of one normalized context dimension."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    context_dimension_position: int = Field(..., ge=0)
    dimension_id: str = Field(..., min_length=1, max_length=128)
    factor_eligibility: ContextFactorEligibilityDecision = Field(..., strict=False)
    level_set_validity: ContextLevelSetDecision = Field(..., strict=False)
    event_scope_validity: ContextScopeDecision = Field(..., strict=False)
    crossing_validity: ContextCrossingDecision = Field(..., strict=False)
    decision: ContextDimensionDecision = Field(..., strict=False)
    factor_evidence_spans: tuple[str, ...] = Field(..., min_length=1, max_length=8)
    level_reviews: tuple[ContextLevelReview, ...] = Field(
        ...,
        min_length=2,
        max_length=16,
    )
    contrast_evidence_spans: tuple[str, ...] = Field(..., min_length=1, max_length=8)
    event_scope_evidence_spans: tuple[str, ...] = Field(
        ...,
        min_length=1,
        max_length=8,
    )
    crossing_evidence_spans: tuple[str, ...] = Field(default=(), max_length=8)
    reasoning: str = Field(..., min_length=1, max_length=3000)
    falsification_condition: str = Field(..., min_length=1, max_length=3000)

    @field_validator(
        "factor_evidence_spans",
        "level_reviews",
        "contrast_evidence_spans",
        "event_scope_evidence_spans",
        "crossing_evidence_spans",
        mode="before",
    )
    @classmethod
    def freeze_evidence_spans(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator(
        "factor_evidence_spans",
        "contrast_evidence_spans",
        "event_scope_evidence_spans",
        "crossing_evidence_spans",
    )
    @classmethod
    def require_unique_evidence_spans(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not span.strip() for span in value) or len(set(value)) != len(value):
            raise ValueError(
                "context subdecision evidence spans must be nonempty and unique"
            )
        return value

    @model_validator(mode="after")
    def require_categorical_consistency(self) -> ContextDimensionReview:
        unsupported = (
            self.factor_eligibility
            in {
                ContextFactorEligibilityDecision.PARTICIPANT_ONLY,
                ContextFactorEligibilityDecision.IMPLICIT_OR_INFERRED,
            }
            or self.level_set_validity
            in {
                ContextLevelSetDecision.MIXED_OR_UNRELATED,
                ContextLevelSetDecision.SERIES_OR_OVERLAPPING,
                ContextLevelSetDecision.IMPLICIT_OR_INFERRED,
            }
            or self.event_scope_validity is ContextScopeDecision.UNSUPPORTED
            or self.crossing_validity is ContextCrossingDecision.UNSUPPORTED
        )
        unresolved = (
            self.factor_eligibility is ContextFactorEligibilityDecision.ABSTAIN
            or self.level_set_validity is ContextLevelSetDecision.ABSTAIN
            or self.event_scope_validity is ContextScopeDecision.ABSTAIN
            or self.crossing_validity is ContextCrossingDecision.ABSTAIN
        )
        fully_supported = (
            self.factor_eligibility
            is ContextFactorEligibilityDecision.EXPLICIT_MULTI_LEVEL_FACTOR
            and self.level_set_validity
            is ContextLevelSetDecision.SAME_FACTOR_MUTUALLY_EXCLUSIVE
            and self.event_scope_validity is ContextScopeDecision.SOURCE_EXPLICIT
            and self.crossing_validity
            in {
                ContextCrossingDecision.SOURCE_EXPLICIT,
                ContextCrossingDecision.NOT_APPLICABLE,
            }
        )
        expected = (
            ContextDimensionDecision.UNSUPPORTED
            if unsupported
            else ContextDimensionDecision.ABSTAIN
            if unresolved
            else ContextDimensionDecision.SUPPORTED
            if fully_supported
            else None
        )
        if expected is None or self.decision is not expected:
            raise ValueError(
                "context-dimension decision must match its categorical findings"
            )
        if tuple(review.level_position for review in self.level_reviews) != tuple(
            range(len(self.level_reviews))
        ):
            raise ValueError("level reviews must be ordered and exhaustive")
        memberships = tuple(review.membership for review in self.level_reviews)
        if (
            self.level_set_validity
            is ContextLevelSetDecision.SAME_FACTOR_MUTUALLY_EXCLUSIVE
            and any(
                membership is not ContextLevelMembershipDecision.SAME_FACTOR_LEVEL
                for membership in memberships
            )
        ):
            raise ValueError("valid level set requires every level in the same factor")
        if (
            self.level_set_validity is ContextLevelSetDecision.MIXED_OR_UNRELATED
            and ContextLevelMembershipDecision.UNRELATED_OR_MIXED not in memberships
        ):
            raise ValueError("mixed level set requires an unrelated level finding")
        if (
            self.level_set_validity is ContextLevelSetDecision.IMPLICIT_OR_INFERRED
            and ContextLevelMembershipDecision.IMPLICIT_OR_INFERRED not in memberships
        ):
            raise ValueError("implicit level set requires an inferred level finding")
        if (
            self.level_set_validity is ContextLevelSetDecision.ABSTAIN
            and ContextLevelMembershipDecision.ABSTAIN not in memberships
        ):
            raise ValueError("abstained level set requires an abstained level finding")
        if (
            self.crossing_validity is ContextCrossingDecision.NOT_APPLICABLE
            and self.crossing_evidence_spans
        ):
            raise ValueError("NOT_APPLICABLE crossing cannot contain crossing evidence")
        if (
            self.crossing_validity is not ContextCrossingDecision.NOT_APPLICABLE
            and not self.crossing_evidence_spans
        ):
            raise ValueError("reviewed crossing requires source evidence")
        return self


class SourceUnitNormalizedReviewOutputV13V6(SourceUnitNormalizedReviewOutput):
    """Review every proposed context dimension independently and in order."""

    context_dimension_reviews: tuple[ContextDimensionReview, ...] = Field(
        default=(),
        max_length=16,
    )

    @field_validator("context_dimension_reviews", mode="before")
    @classmethod
    def freeze_context_reviews(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def require_ordered_context_reviews(self) -> SourceUnitNormalizedReviewOutputV13V6:
        positions = tuple(
            review.context_dimension_position
            for review in self.context_dimension_reviews
        )
        if positions != tuple(range(len(self.context_dimension_reviews))):
            raise ValueError("context-dimension reviews must be ordered and exhaustive")
        return self


__all__ = [
    "ContextCrossingDecision",
    "ContextDimensionDecision",
    "ContextDimensionReview",
    "ContextFactorEligibilityDecision",
    "ContextLevelSetDecision",
    "ContextLevelMembershipDecision",
    "ContextLevelReview",
    "ContextScopeDecision",
    "SourceUnitNormalizedReviewOutputV13V6",
]
