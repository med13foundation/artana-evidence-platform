"""Categorical experimental-context topology authored by the normalizer."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ContextDimensionType(StrEnum):
    """Closed kinds of experimental factors represented by source levels."""

    GENOTYPE = "GENOTYPE"
    TREATMENT = "TREATMENT"
    CONDITION = "CONDITION"
    POPULATION = "POPULATION"
    OTHER_EXPLICIT = "OTHER_EXPLICIT"


class ContextDimensionOperator(StrEnum):
    """How mutually exclusive source levels relate within one factor."""

    ALTERNATIVE_LEVELS = "ALTERNATIVE_LEVELS"


class ContextDimension(BaseModel):
    """One source-explicit factor, its levels, scope, and crossed factors."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    dimension_id: str = Field(
        ..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"
    )
    dimension_type: ContextDimensionType = Field(..., strict=False)
    operator: ContextDimensionOperator = Field(..., strict=False)
    factor_span: str = Field(..., min_length=1, max_length=1000)
    level_spans: tuple[str, ...] = Field(..., min_length=2, max_length=16)
    applies_to_local_event_ids: tuple[str, ...] = Field(
        ..., min_length=1, max_length=16
    )
    crossed_dimension_ids: tuple[str, ...] = Field(default=(), max_length=16)
    reasoning: str = Field(..., min_length=1, max_length=3000)
    falsification_condition: str = Field(..., min_length=1, max_length=3000)

    @field_validator(
        "level_spans",
        "applies_to_local_event_ids",
        "crossed_dimension_ids",
        mode="before",
    )
    @classmethod
    def freeze_sequences(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def require_unique_members(self) -> ContextDimension:
        sequences = (
            self.level_spans,
            self.applies_to_local_event_ids,
            self.crossed_dimension_ids,
        )
        if any(len(set(sequence)) != len(sequence) for sequence in sequences):
            raise ValueError("context dimension members must be unique")
        if self.dimension_id in self.crossed_dimension_ids:
            raise ValueError("context dimension cannot cross itself")
        return self


__all__ = [
    "ContextDimension",
    "ContextDimensionOperator",
    "ContextDimensionType",
]
