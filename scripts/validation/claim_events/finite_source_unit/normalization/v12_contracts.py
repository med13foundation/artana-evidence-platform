"""V12 provider contract closing normalized event-identity ambiguity."""

from __future__ import annotations

from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimInventoryItem,
)
from pydantic import Field, field_validator, model_validator

from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
    SourceUnitNormalizationOutput,
)


class V12NormalizedClaimInventoryItem(ClaimInventoryItem):
    """Normalized event with an agent-authored stable local identity."""

    local_event_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z][A-Za-z0-9_-]*$",
    )

    @field_validator("local_event_id")
    @classmethod
    def require_nonblank_local_event_id(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("normalized local event ID cannot contain edge whitespace")
        return value


class SourceUnitNormalizationOutputV12(SourceUnitNormalizationOutput):
    """V12 normalization output with schema-required unique event IDs."""

    events: tuple[V12NormalizedClaimInventoryItem, ...] = Field(
        default=(),
        max_length=16,
    )

    @model_validator(mode="after")
    def require_unique_local_event_ids(self) -> SourceUnitNormalizationOutputV12:
        event_ids = tuple(event.local_event_id for event in self.events)
        if len(set(event_ids)) != len(event_ids):
            raise ValueError("normalized local event IDs must be unique")
        return self


__all__ = [
    "SourceUnitNormalizationOutputV12",
    "V12NormalizedClaimInventoryItem",
]
