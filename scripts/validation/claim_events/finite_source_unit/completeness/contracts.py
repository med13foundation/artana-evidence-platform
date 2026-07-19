"""Closed categorical output for an independent whole-source inventory."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitEligibilityCategory,
)
from scripts.validation.claim_events.finite_source_unit.normalization.context_dimensions import (
    ContextDimension,  # noqa: TC001 - Pydantic resolves the model at runtime.
)
from scripts.validation.claim_events.finite_source_unit.normalization.v13_contracts import (
    V13NormalizedClaimInventoryItem,
    require_controlled_event_topology,
)


class CompletenessInventoryDecision(StrEnum):
    """Agent-authored whole-unit inventory disposition."""

    COMPLETE_INVENTORY = "COMPLETE_INVENTORY"
    NO_EVENT = "NO_EVENT"
    ABSTAIN = "ABSTAIN"


class SourceUnitCompletenessInventoryOutputV1(BaseModel):
    """A source-only event inventory with no trust or numeric judgment."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    eligibility_category: SourceUnitEligibilityCategory = Field(..., strict=False)
    decision: CompletenessInventoryDecision = Field(..., strict=False)
    events: tuple[V13NormalizedClaimInventoryItem, ...] = Field(
        default=(),
        max_length=16,
    )
    context_dimensions: tuple[ContextDimension, ...] = Field(
        default=(),
        max_length=16,
    )
    evidence_spans: tuple[str, ...] = Field(default=(), max_length=16)
    reasoning: str = Field(..., min_length=1, max_length=4000)
    falsification_condition: str = Field(..., min_length=1, max_length=4000)

    @field_validator(
        "events",
        "context_dimensions",
        "evidence_spans",
        mode="before",
    )
    @classmethod
    def freeze_sequences(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("evidence_spans")
    @classmethod
    def require_unique_evidence_spans(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if any(not span.strip() for span in value) or len(set(value)) != len(value):
            raise ValueError("completeness evidence spans must be nonempty and unique")
        return value

    @model_validator(mode="after")
    def require_decision_consistency(self) -> SourceUnitCompletenessInventoryOutputV1:
        if self.decision is CompletenessInventoryDecision.COMPLETE_INVENTORY:
            if not self.eligibility_category.scientific or not self.events:
                raise ValueError(
                    "COMPLETE_INVENTORY requires a scientific category and events"
                )
            if not self.evidence_spans:
                raise ValueError("COMPLETE_INVENTORY requires source evidence")
        elif self.decision is CompletenessInventoryDecision.NO_EVENT:
            if self.eligibility_category.scientific:
                raise ValueError("NO_EVENT cannot use a scientific category")
            if self.eligibility_category is SourceUnitEligibilityCategory.ABSTAIN:
                raise ValueError("ABSTAIN eligibility requires ABSTAIN decision")
            if self.events or self.context_dimensions:
                raise ValueError("NO_EVENT cannot contain events or context")
        else:
            if self.eligibility_category is not SourceUnitEligibilityCategory.ABSTAIN:
                raise ValueError("ABSTAIN decision requires ABSTAIN eligibility")
            if self.events or self.context_dimensions:
                raise ValueError("ABSTAIN cannot contain events or context")

        local_event_ids = tuple(event.local_event_id for event in self.events)
        if len(set(local_event_ids)) != len(local_event_ids):
            raise ValueError("completeness event local IDs must be unique")
        require_controlled_event_topology(self.events)
        return self


__all__ = [
    "CompletenessInventoryDecision",
    "SourceUnitCompletenessInventoryOutputV1",
]
