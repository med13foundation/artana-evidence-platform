"""
Graph connection output contract for graph-layer reasoning workflows.

The Graph Connection Agent proposes relation candidates inferred from
cross-document/cross-edge patterns in the existing kernel graph.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.agents.contracts.assessment_compat import (
    confidence_from_graph_connection_contract,
)
from src.domain.agents.contracts.base import EvidenceBackedAgentContract
from src.domain.agents.contracts.fact_assessment import (
    FactAssessment,
    assessment_confidence,
)


class ProposedRelation(BaseModel):
    """One relation candidate proposed by graph-level reasoning."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(..., min_length=1, max_length=64)
    relation_type: str = Field(..., min_length=1, max_length=64)
    target_id: str = Field(..., min_length=1, max_length=64)
    assessment: FactAssessment = Field(
        ...,
        description="Qualitative assessment for this proposed relation.",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Derived backend weight normalized from assessment.",
    )
    evidence_summary: str = Field(..., min_length=1, max_length=2000)
    evidence_tier: Literal["COMPUTATIONAL"] = "COMPUTATIONAL"
    supporting_provenance_ids: list[str] = Field(default_factory=list)
    supporting_document_count: int = Field(default=0, ge=0)
    reasoning: str = Field(..., min_length=1, max_length=4000)

    @model_validator(mode="after")
    def _normalize_confidence(self) -> ProposedRelation:
        self.confidence = assessment_confidence(self.assessment)
        return self


class RejectedCandidate(BaseModel):
    """A candidate relation that was considered but not proposed."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(..., min_length=1, max_length=64)
    relation_type: str = Field(..., min_length=1, max_length=64)
    target_id: str = Field(..., min_length=1, max_length=64)
    assessment: FactAssessment = Field(
        ...,
        description="Qualitative assessment explaining why the candidate was rejected.",
    )
    reason: str = Field(..., min_length=1, max_length=512)
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Derived backend weight normalized from assessment.",
    )

    @model_validator(mode="after")
    def _normalize_confidence(self) -> RejectedCandidate:
        self.confidence = assessment_confidence(self.assessment)
        return self


class GraphConnectionContract(EvidenceBackedAgentContract):
    """Contract for Graph Connection Agent outputs."""

    confidence_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Derived backend run-level confidence for graph connection routing.",
    )
    decision: Literal["generated", "fallback", "escalate"] = Field(
        ...,
        description="Outcome of the graph-connection run",
    )
    source_type: str = Field(..., min_length=1, max_length=64)
    research_space_id: str = Field(..., min_length=1, max_length=64)
    seed_entity_id: str = Field(..., min_length=1, max_length=64)
    proposed_relations: list[ProposedRelation] = Field(default_factory=list)
    rejected_candidates: list[RejectedCandidate] = Field(default_factory=list)
    shadow_mode: bool = Field(
        default=True,
        description="Whether persistence side effects should be suppressed",
    )
    agent_run_id: str | None = Field(
        default=None,
        description="Orchestration run identifier when available",
    )

    @model_validator(mode="after")
    def _normalize_run_confidence(self) -> GraphConnectionContract:
        derived_confidence = confidence_from_graph_connection_contract(self)
        self.confidence_score = derived_confidence
        return self


__all__ = [
    "GraphConnectionContract",
    "ProposedRelation",
    "RejectedCandidate",
]
