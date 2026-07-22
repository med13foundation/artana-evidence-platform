"""Strict categorical contract for the specialist-assisted Luna micro-canary."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from scripts.validation.public_gold.staged_event.contracts import StrictStageModel


class SpecialistProposalDecision(StrictStageModel):
    proposal_id: str = Field(min_length=1, max_length=128)
    decision: Literal["ACCEPT", "REJECT", "ABSTAIN"]
    target_kind: Literal["PARTICIPANT", "EVENT"]
    scientific_role: Literal[
        "THEME", "CAUSE", "INSTRUMENT", "PARTICIPANT", "OTHER_EXPLICIT"
    ]
    exact_evidence: str = Field(min_length=1, max_length=2000)
    evidence_start: int = Field(ge=0)
    evidence_end: int = Field(gt=0)
    attachment: Literal["CURRENT_EVENT", "NESTED_EVENT"]
    explanation: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_evidence_span(self) -> SpecialistProposalDecision:
        if self.evidence_end <= self.evidence_start:
            raise ValueError("evidence end must be greater than start")
        return self


class SpecialistLunaOutput(StrictStageModel):
    packet_id: str = Field(min_length=1, max_length=128)
    proposal_decisions: tuple[SpecialistProposalDecision, ...] = Field(max_length=32)
    structure_assessment: Literal[
        "COMPLETE", "INCOMPLETE", "CONTRADICTED", "ABSTAIN"
    ]
    structure_explanation: str = Field(min_length=1, max_length=3000)


__all__ = ["SpecialistLunaOutput", "SpecialistProposalDecision"]
