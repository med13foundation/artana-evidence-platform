"""V2-only contracts for source-bound participant inventory."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from scripts.validation.public_gold.staged_event.contracts import (
    ParticipantTargetKind,
    SourceEntityType,
    StrictStageModel,
)


class SourceBoundParticipant(StrictStageModel):
    participant_key: str = Field(min_length=1, max_length=128)
    exact_text: str = Field(min_length=1, max_length=12000)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    occurrence_id: str = Field(pattern=r"^occurrence-[0-9]+$", max_length=64)
    candidate_target_kind: ParticipantTargetKind = Field(strict=False)
    source_entity_type: SourceEntityType | None = Field(default=None, strict=False)
    explanation: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_span_and_type(self) -> SourceBoundParticipant:
        if self.end <= self.start:
            raise ValueError("participant end must be greater than start")
        if self.candidate_target_kind is ParticipantTargetKind.PARTICIPANT:
            if self.source_entity_type is None:
                raise ValueError("direct participants require a source entity type")
        elif self.source_entity_type is not None:
            raise ValueError("event targets cannot include a source entity type")
        return self


class SourceBoundEventInventory(StrictStageModel):
    event_id: str = Field(min_length=1, max_length=128)
    decision: Literal["INVENTORIED", "ABSTAIN"]
    participants: tuple[SourceBoundParticipant, ...] = Field(max_length=64)
    abstention_reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_decision(self) -> SourceBoundEventInventory:
        if self.decision == "ABSTAIN":
            if self.participants or not self.abstention_reason:
                raise ValueError("ABSTAIN requires no participants and a reason")
        elif self.abstention_reason is not None:
            raise ValueError("INVENTORIED cannot include an abstention reason")
        return self


class SourceBoundParticipantOutput(StrictStageModel):
    inventories: tuple[SourceBoundEventInventory, ...] = Field(max_length=128)


__all__ = ["SourceBoundParticipantOutput"]
