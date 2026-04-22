"""Contract models for LLM-based mapper disambiguation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from src.domain.agents.contracts.base import EvidenceBackedAgentContract
from src.domain.agents.contracts.mapping_judge_assessment import (
    CandidateSeparation,
    MappingJudgeAssessment,
    MappingResolutionStatus,
    MappingSupportBand,
    build_mapping_judge_assessment_from_confidence,
    mapping_judge_assessment_confidence,
)
from src.type_definitions.common import JSONObject  # noqa: TC001

_CLEAR_CANDIDATE_SEPARATION_THRESHOLD = 0.85
_MODERATE_CANDIDATE_SEPARATION_THRESHOLD = 0.7


class MappingJudgeCandidate(BaseModel):
    """Candidate variable definition presented to the mapping judge."""

    variable_id: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=255)
    match_method: Literal["exact", "synonym", "fuzzy", "vector"]
    similarity_score: float = Field(..., ge=0.0, le=1.0)
    description: str | None = None
    metadata: JSONObject = Field(default_factory=dict)


class MappingJudgeContract(EvidenceBackedAgentContract):
    """Structured output for one mapper disambiguation decision."""

    confidence_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Derived backend confidence for routing and audit compatibility.",
    )
    decision: Literal["matched", "no_match", "ambiguous"]
    assessment: MappingJudgeAssessment | None = Field(
        default=None,
        description="Qualitative assessment of the mapping decision.",
    )
    selected_variable_id: str | None = Field(default=None, min_length=1, max_length=64)
    candidate_count: int = Field(default=0, ge=0)
    selection_rationale: str = Field(..., min_length=1, max_length=4000)
    selected_candidate: MappingJudgeCandidate | None = None
    agent_run_id: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def _normalize_assessment(self) -> MappingJudgeContract:
        if self.assessment is None:
            self.assessment = build_mapping_judge_assessment_from_confidence(
                confidence=self.confidence_score,
                confidence_rationale=self.selection_rationale,
                resolution_status=_resolution_status_for_decision(self.decision),
                candidate_separation=_candidate_separation_for_decision(
                    self.decision,
                    confidence=self.confidence_score,
                ),
            )
        self.confidence_score = mapping_judge_assessment_confidence(self.assessment)
        return self


def _resolution_status_for_decision(
    decision: Literal["matched", "no_match", "ambiguous"],
) -> MappingResolutionStatus:
    if decision == "matched":
        return MappingResolutionStatus.RESOLVED
    if decision == "ambiguous":
        return MappingResolutionStatus.AMBIGUOUS
    return MappingResolutionStatus.NO_MATCH


def _candidate_separation_for_decision(
    decision: Literal["matched", "no_match", "ambiguous"],
    *,
    confidence: float,
) -> CandidateSeparation:
    if decision == "no_match":
        return CandidateSeparation.NOT_APPLICABLE
    if confidence >= _CLEAR_CANDIDATE_SEPARATION_THRESHOLD:
        return CandidateSeparation.CLEAR
    if confidence >= _MODERATE_CANDIDATE_SEPARATION_THRESHOLD:
        return CandidateSeparation.MODERATE
    return CandidateSeparation.TIGHT


__all__ = [
    "CandidateSeparation",
    "MappingJudgeAssessment",
    "MappingJudgeCandidate",
    "MappingJudgeContract",
    "MappingResolutionStatus",
    "MappingSupportBand",
]
