"""Strict agent-owned contracts for dual role adjudication."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from scripts.validation.public_gold.staged_event.contracts import StrictStageModel

SourceSemanticRole = Literal[
    "AFFECTED_ENTITY",
    "CAUSAL_AGENT",
    "STIMULUS_OR_OBJECT",
    "INSTRUMENT",
    "CONTEXTUAL_PARTICIPANT",
    "OTHER_EXPLICIT",
    "ABSTAIN",
]
BenchmarkRole = Literal["THEME", "CAUSE", "INSTRUMENT", "OTHER", "ABSTAIN"]


class EvidenceItem(StrictStageModel):
    exact_text: str = Field(min_length=1, max_length=2000)


class SourceRoleDecision(StrictStageModel):
    case_id: str = Field(min_length=1, max_length=128)
    source_semantic_role: SourceSemanticRole
    evidence_items: tuple[EvidenceItem, ...] = Field(min_length=1, max_length=8)
    explanation: str = Field(min_length=1, max_length=2000)
    falsification_explanation: str = Field(min_length=1, max_length=2000)


class SourceRoleReview(StrictStageModel):
    decisions: tuple[SourceRoleDecision, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def unique_case_ids(self) -> SourceRoleReview:
        case_ids = [item.case_id for item in self.decisions]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("source-role case IDs must be unique")
        return self


class BenchmarkRoleDecision(StrictStageModel):
    case_id: str = Field(min_length=1, max_length=128)
    benchmark_projection_role: BenchmarkRole
    policy_rule_id: str = Field(min_length=1, max_length=128)
    evidence_items: tuple[EvidenceItem, ...] = Field(min_length=1, max_length=8)
    explanation: str = Field(min_length=1, max_length=2000)


class BenchmarkRoleReview(StrictStageModel):
    decisions: tuple[BenchmarkRoleDecision, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def unique_case_ids(self) -> BenchmarkRoleReview:
        case_ids = [item.case_id for item in self.decisions]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("benchmark-role case IDs must be unique")
        return self


class DualRoleTieBreakDecision(StrictStageModel):
    case_id: str = Field(min_length=1, max_length=128)
    source_semantic_role: SourceSemanticRole
    benchmark_projection_role: BenchmarkRole
    policy_rule_id: str = Field(min_length=1, max_length=128)
    evidence_items: tuple[EvidenceItem, ...] = Field(min_length=1, max_length=8)
    source_explanation: str = Field(min_length=1, max_length=2000)
    benchmark_explanation: str = Field(min_length=1, max_length=2000)
    falsification_explanation: str = Field(min_length=1, max_length=2000)


class DualRoleTieBreakReview(StrictStageModel):
    decisions: tuple[DualRoleTieBreakDecision, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def unique_case_ids(self) -> DualRoleTieBreakReview:
        case_ids = [item.case_id for item in self.decisions]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("tie-break case IDs must be unique")
        return self


__all__ = [
    "BenchmarkRoleDecision",
    "BenchmarkRoleReview",
    "DualRoleTieBreakDecision",
    "DualRoleTieBreakReview",
    "EvidenceItem",
    "SourceRoleDecision",
    "SourceRoleReview",
]
