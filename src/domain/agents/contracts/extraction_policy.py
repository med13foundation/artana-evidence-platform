"""Contract models for extraction relation-policy proposals."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.domain.agents.contracts.base import BaseAgentContract


class UnknownRelationPattern(BaseModel):
    """One undefined relation pattern observed during extraction."""

    source_type: str = Field(..., min_length=1, max_length=64)
    relation_type: str = Field(..., min_length=1, max_length=64)
    target_type: str = Field(..., min_length=1, max_length=64)
    source_label_example: str | None = Field(default=None, max_length=255)
    target_label_example: str | None = Field(default=None, max_length=255)
    occurrences: int = Field(default=1, ge=1)


class RelationConstraintProposal(BaseModel):
    """Proposed constraint for a (source, relation, target) triple."""

    source_type: str = Field(..., min_length=1, max_length=64)
    relation_type: str = Field(..., min_length=1, max_length=64)
    target_type: str = Field(..., min_length=1, max_length=64)
    proposed_is_allowed: bool = True
    proposed_requires_evidence: bool = True
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    rationale: str = Field(..., min_length=1, max_length=2000)


class RelationTypeMappingProposal(BaseModel):
    """Proposal to map an observed relation label to a canonical relation type."""

    source_type: str = Field(..., min_length=1, max_length=64)
    observed_relation_type: str = Field(..., min_length=1, max_length=64)
    target_type: str = Field(..., min_length=1, max_length=64)
    mapped_relation_type: str = Field(..., min_length=1, max_length=64)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    rationale: str = Field(..., min_length=1, max_length=2000)


class ExtractionPolicyContract(BaseAgentContract):
    """Structured output from the extraction relation-policy agent."""

    decision: Literal["generated", "fallback", "escalate"] = Field(
        ...,
        description="Outcome of the policy proposal run",
    )
    source_type: str = Field(..., min_length=1, max_length=64)
    document_id: str = Field(..., min_length=1, max_length=64)
    unknown_patterns: list[UnknownRelationPattern] = Field(default_factory=list)
    relation_constraint_proposals: list[RelationConstraintProposal] = Field(
        default_factory=list,
    )
    relation_type_mapping_proposals: list[RelationTypeMappingProposal] = Field(
        default_factory=list,
    )
    agent_run_id: str | None = Field(
        default=None,
        description="Orchestration run identifier when available",
    )


__all__ = [
    "ExtractionPolicyContract",
    "RelationConstraintProposal",
    "RelationTypeMappingProposal",
    "UnknownRelationPattern",
]
