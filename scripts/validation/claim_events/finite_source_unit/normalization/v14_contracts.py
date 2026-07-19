"""V14 provider proposal without agent-authored mapping operations."""

from __future__ import annotations

from artana_evidence_api.document_extraction_support.claim_frames import (
    InventoryAssertionScope,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitEligibilityCategory,  # noqa: TC001 - Pydantic resolves at runtime.
)
from scripts.validation.claim_events.finite_source_unit.normalization.context_dimensions import (
    ContextDimension,  # noqa: TC001 - Pydantic resolves at runtime.
)
from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
    NormalizationAbstentionReason,
    NormalizationFamily,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v13_contracts import (
    V13NormalizedClaimInventoryItem,
    require_controlled_event_topology,
)


class V14SourceEventMapping(BaseModel):
    """Agent-authored scientific correspondence without a procedural label."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    normalized_event_position: int = Field(..., ge=0)
    source_event_positions: tuple[int, ...] = Field(..., min_length=1, max_length=16)
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


class SourceUnitNormalizationProposalV14(BaseModel):
    """Standalone V14 provider contract preserving agent scientific authority."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    eligibility_category: SourceUnitEligibilityCategory = Field(..., strict=False)
    family: NormalizationFamily = Field(..., strict=False)
    abstention_reason: NormalizationAbstentionReason = Field(..., strict=False)
    events: tuple[V13NormalizedClaimInventoryItem, ...] = Field(
        default=(),
        max_length=16,
    )
    mappings: tuple[V14SourceEventMapping, ...] = Field(default=(), max_length=16)
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
    def require_family_consistency(self) -> SourceUnitNormalizationProposalV14:
        if self.family is NormalizationFamily.ABSTAIN:
            if self.events or self.mappings or self.context_dimensions:
                raise ValueError(
                    "ABSTAIN cannot contain normalized events, mappings, or "
                    "context dimensions"
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
        has_reference = any(
            argument.controlled_event_ref
            for event in self.events
            for argument in event.arguments
        )
        has_controlled_target = any(
            event.assertion_scope is InventoryAssertionScope.CONTROLLED_TARGET
            for event in self.events
        )
        if self.family is NormalizationFamily.DIRECT and (
            has_reference or has_controlled_target
        ):
            raise ValueError("DIRECT cannot contain controlled-event structure")
        if self.family is NormalizationFamily.NESTED and not has_reference:
            raise ValueError("NESTED requires an explicit event-to-event reference")
        require_controlled_event_topology(self.events)
        return self


__all__ = ["SourceUnitNormalizationProposalV14", "V14SourceEventMapping"]
