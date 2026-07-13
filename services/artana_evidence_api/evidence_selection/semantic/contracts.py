"""Typed categorical contracts for agent-first evidence selection."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SemanticCandidateDecision = Literal["select", "reject", "review"]
SemanticCriterionAssessment = Literal[
    "match",
    "no_match",
    "not_required",
    "uncertain",
]
SemanticObjectiveAssessment = Literal[
    "direct",
    "supporting",
    "context_only",
    "off_objective",
    "uncertain",
]
SemanticInclusionAssessment = Literal["met", "not_met", "uncertain"]
SemanticExclusionAssessment = Literal["not_triggered", "triggered", "uncertain"]
_MIN_EVIDENCE_REFERENCE_LENGTH = 4
_OPAQUE_RECORD_REFERENCE_PATTERN = r"^sr_[a-f0-9]{32}$"
_OPAQUE_EVIDENCE_REFERENCE_PATTERN = r"^se_[a-f0-9]{32}$"


class EvidenceSelectionSemanticCandidateAssessment(BaseModel):
    """One evidence-backed categorical judgment from the selection agent."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    record_ref: str = Field(pattern=_OPAQUE_RECORD_REFERENCE_PATTERN)
    decision: SemanticCandidateDecision
    objective_match: SemanticObjectiveAssessment
    entity_variant_match: SemanticCriterionAssessment
    population_match: SemanticCriterionAssessment
    intervention_match: SemanticCriterionAssessment
    outcome_match: SemanticCriterionAssessment
    study_type_match: SemanticCriterionAssessment
    inclusion_assessment: SemanticInclusionAssessment
    exclusion_assessment: SemanticExclusionAssessment
    explanation: str = Field(min_length=1, max_length=3000)
    evidence_references: tuple[str, ...] = Field(min_length=1, max_length=5)

    @field_validator("evidence_references", mode="before")
    @classmethod
    def _accept_json_evidence_references(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("explanation")
    @classmethod
    def _require_literal_explanation(cls, value: str) -> str:
        return _literal_nonblank(value)

    @field_validator("evidence_references")
    @classmethod
    def _validate_evidence_references(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(_literal_nonblank(reference) for reference in value)
        if any(
            len(reference) < _MIN_EVIDENCE_REFERENCE_LENGTH for reference in normalized
        ):
            msg = "evidence_references must contain at least four literal characters"
            raise ValueError(msg)
        if any(
            re.fullmatch(_OPAQUE_EVIDENCE_REFERENCE_PATTERN, reference) is None
            for reference in normalized
        ):
            msg = "evidence_references must contain opaque service-owned references"
            raise ValueError(msg)
        if len(set(normalized)) != len(normalized):
            msg = "evidence_references must be unique within one assessment"
            raise ValueError(msg)
        return normalized

    @model_validator(mode="after")
    def _decision_must_follow_categorical_findings(
        self,
    ) -> EvidenceSelectionSemanticCandidateAssessment:
        if self.decision == "select" and (
            self.objective_match not in {"direct", "supporting"}
            or self.inclusion_assessment != "met"
            or self.exclusion_assessment != "not_triggered"
            or any(
                finding not in {"match", "not_required"}
                for finding in (
                    self.entity_variant_match,
                    self.population_match,
                    self.intervention_match,
                    self.outcome_match,
                    self.study_type_match,
                )
            )
        ):
            msg = (
                "select requires supported objective, inclusion, and exclusion findings"
            )
            raise ValueError(msg)
        if self.decision == "reject" and (
            self.objective_match == "uncertain"
            or self.inclusion_assessment == "uncertain"
            or self.exclusion_assessment == "uncertain"
        ):
            msg = "uncertain findings must use the review decision"
            raise ValueError(msg)
        if self.decision == "reject" and not (
            self.objective_match in {"context_only", "off_objective"}
            or "no_match"
            in {
                self.entity_variant_match,
                self.population_match,
                self.intervention_match,
                self.outcome_match,
                self.study_type_match,
            }
            or self.inclusion_assessment == "not_met"
            or self.exclusion_assessment == "triggered"
        ):
            msg = "reject requires at least one explicit negative categorical finding"
            raise ValueError(msg)
        return self


class EvidenceSelectionSemanticBatchContract(BaseModel):
    """Complete agent response for one saved source-search result set."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal["evidence_selection_semantic_agent.v2"]
    agent_run_id: str | None = Field(default=None, min_length=1, max_length=255)
    reasoning_summary: str = Field(min_length=1, max_length=3000)
    assessments: tuple[EvidenceSelectionSemanticCandidateAssessment, ...] = Field(
        min_length=1,
    )

    @field_validator("assessments", mode="before")
    @classmethod
    def _accept_json_assessments(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("reasoning_summary")
    @classmethod
    def _require_literal_text(cls, value: str) -> str:
        return _literal_nonblank(value)

    @field_validator("agent_run_id")
    @classmethod
    def _validate_optional_agent_run_id(cls, value: str | None) -> str | None:
        return _literal_nonblank(value) if value is not None else None

    @model_validator(mode="after")
    def _record_references_must_be_unique(
        self,
    ) -> EvidenceSelectionSemanticBatchContract:
        references = [assessment.record_ref for assessment in self.assessments]
        if len(set(references)) != len(references):
            msg = "semantic agent returned duplicate record_ref values"
            raise ValueError(msg)
        return self


def _literal_nonblank(value: str) -> str:
    if not value.strip():
        msg = "semantic assessment text must be nonblank"
        raise ValueError(msg)
    if value != value.strip():
        msg = "semantic assessment text must not have surrounding whitespace"
        raise ValueError(msg)
    return value


__all__ = [
    "EvidenceSelectionSemanticBatchContract",
    "EvidenceSelectionSemanticCandidateAssessment",
    "SemanticCandidateDecision",
    "SemanticCriterionAssessment",
    "SemanticExclusionAssessment",
    "SemanticInclusionAssessment",
    "SemanticObjectiveAssessment",
]
