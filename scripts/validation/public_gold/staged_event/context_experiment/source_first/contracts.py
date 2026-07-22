"""Typed source-first scientific event graph returned by Luna."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from scripts.validation.public_gold.lossless_event_experiment_contracts import (
    SourceEventType,  # noqa: TC001 - required at runtime by Pydantic
)
from scripts.validation.public_gold.staged_event.contracts import (
    SourceEntityType,
    StrictStageModel,
)


class EvidenceSpan(StrictStageModel):
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    exact_text: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_order(self) -> EvidenceSpan:
        if self.end <= self.start:
            raise ValueError("evidence end must be greater than start")
        return self


class ParticipantNode(StrictStageModel):
    participant_id: str = Field(min_length=1, max_length=128)
    entity_type: SourceEntityType = Field(strict=False)
    evidence: EvidenceSpan


class EventArgument(StrictStageModel):
    role: Literal["THEME", "CAUSE", "INSTRUMENT", "OTHER_EXPLICIT"]
    target_kind: Literal["PARTICIPANT", "EVENT"]
    target_id: str = Field(min_length=1, max_length=128)


class EventNode(StrictStageModel):
    event_id: str = Field(min_length=1, max_length=128)
    event_type: SourceEventType = Field(strict=False)
    trigger: EvidenceSpan
    arguments: tuple[EventArgument, ...] = Field(max_length=32)
    short_explanation: str = Field(min_length=1, max_length=2000)


class CompleteEventOutput(StrictStageModel):
    packet_id: str = Field(min_length=1, max_length=128)
    participants: tuple[ParticipantNode, ...] = Field(max_length=32)
    events: tuple[EventNode, ...] = Field(max_length=32)
    root_event_id: str | None = Field(default=None, max_length=128)
    structure_assessment: Literal[
        "COMPLETE", "INCOMPLETE", "CONTRADICTED", "ABSTAIN"
    ]
    structure_explanation: str = Field(min_length=1, max_length=3000)


__all__ = [
    "CompleteEventOutput",
    "EventArgument",
    "EventNode",
    "EvidenceSpan",
    "ParticipantNode",
]
