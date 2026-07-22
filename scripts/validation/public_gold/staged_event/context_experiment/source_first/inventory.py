"""Agent-owned event inventory contract and deterministic exposed gate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import Field, model_validator

from scripts.validation.public_gold.lossless_event_experiment_contracts import (
    SourceEventType,  # noqa: TC001 - Pydantic runtime schema
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.anchors import (
    ResolvedAnchor,
    resolve_anchor,
)
from scripts.validation.public_gold.staged_event.contracts import StrictStageModel


class InventoryEvent(StrictStageModel):
    temporary_event_id: str = Field(min_length=1, max_length=128)
    event_type: SourceEventType = Field(strict=False)
    exact_trigger: str = Field(min_length=1, max_length=512)
    exact_evidence: str = Field(min_length=1, max_length=4000)
    structural_position: Literal["ROOT_CANDIDATE", "NESTED_EVENT", "UNRESOLVED"]
    explanation: str = Field(min_length=1, max_length=2000)


class EventInventoryOutput(StrictStageModel):
    packet_id: str = Field(min_length=1, max_length=128)
    events: tuple[InventoryEvent, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def unique_ids(self) -> EventInventoryOutput:
        ids = [item.temporary_event_id for item in self.events]
        if len(ids) != len(set(ids)):
            raise ValueError("inventory event IDs must be unique")
        return self


@dataclass(frozen=True, slots=True)
class ResolvedInventoryEvent:
    temporary_event_id: str
    event_type: SourceEventType
    trigger: ResolvedAnchor
    structural_position: str
    explanation: str


@dataclass(frozen=True, slots=True)
class InventoryGate:
    passed: bool
    intermediate_event_present: bool
    missing: tuple[tuple[str, int, int, str], ...]
    unsupported: tuple[tuple[str, int, int, str], ...]


def resolve_inventory(
    output: EventInventoryOutput,
    *,
    source: str,
    scope_start: int,
    scope_end: int,
) -> tuple[ResolvedInventoryEvent, ...]:
    return tuple(
        ResolvedInventoryEvent(
            temporary_event_id=item.temporary_event_id,
            event_type=item.event_type,
            trigger=resolve_anchor(
                source=source,
                scope_start=scope_start,
                scope_end=scope_end,
                exact_text=item.exact_trigger,
                exact_evidence=item.exact_evidence,
            ),
            structural_position=item.structural_position,
            explanation=item.explanation,
        )
        for item in output.events
    )


def compare_exposed_inventory(
    events: tuple[ResolvedInventoryEvent, ...],
) -> InventoryGate:
    expected = {
        ("Negative_regulation", 0, 8, "Decrease"),
        ("Positive_regulation", 27, 35, "enhances"),
        ("Regulation", 48, 59, "sensitivity"),
    }
    actual = {
        (
            item.event_type.value,
            item.trigger.start,
            item.trigger.end,
            item.trigger.exact_text,
        )
        for item in events
    }
    return InventoryGate(
        passed=actual == expected,
        intermediate_event_present=("Regulation", 48, 59, "sensitivity") in actual,
        missing=tuple(sorted(expected - actual)),
        unsupported=tuple(sorted(actual - expected)),
    )


__all__ = [
    "EventInventoryOutput",
    "InventoryEvent",
    "InventoryGate",
    "ResolvedInventoryEvent",
    "compare_exposed_inventory",
    "resolve_inventory",
]
