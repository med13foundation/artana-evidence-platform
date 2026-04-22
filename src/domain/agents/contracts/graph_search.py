"""Graph search output contract for read-only graph query workflows."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from src.domain.agents.contracts.base import EvidenceBackedAgentContract
from src.domain.agents.contracts.graph_search_assessment import (
    GraphSearchAssessment,
    GraphSearchGroundingLevel,
    build_graph_search_assessment_from_confidence,
    graph_search_assessment_confidence,
    graph_search_grounding_level_from_counts,
)


class EvidenceChainItem(BaseModel):
    """One provenance-linked evidence reference backing a search result."""

    provenance_id: str | None = Field(default=None, min_length=1, max_length=64)
    relation_id: str | None = Field(default=None, min_length=1, max_length=64)
    observation_id: str | None = Field(default=None, min_length=1, max_length=64)
    evidence_tier: str | None = Field(default=None, min_length=1, max_length=32)
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Derived numeric weight for compatibility and ranking.",
    )
    assessment: GraphSearchAssessment | None = Field(
        default=None,
        description="Qualitative assessment for this evidence reference.",
    )
    evidence_sentence: str | None = Field(default=None, max_length=2000)
    source_ref: str | None = Field(default=None, max_length=1024)

    @model_validator(mode="after")
    def _normalize_assessment(self) -> EvidenceChainItem:
        if self.assessment is None:
            source_confidence = self.confidence if self.confidence is not None else 0.45
            grounding_level = (
                GraphSearchGroundingLevel.RELATION
                if self.relation_id is not None
                else (
                    GraphSearchGroundingLevel.OBSERVATION
                    if self.observation_id is not None
                    else GraphSearchGroundingLevel.NONE
                )
            )
            rationale = (
                "Derived from numeric evidence confidence."
                if self.confidence is not None
                else "No explicit graph-search assessment was supplied."
            )
            self.assessment = build_graph_search_assessment_from_confidence(
                source_confidence,
                confidence_rationale=rationale,
                grounding_level=grounding_level,
            )
        self.confidence = graph_search_assessment_confidence(self.assessment)
        return self


class GraphSearchResultEntry(BaseModel):
    """One ranked graph search result."""

    entity_id: str = Field(..., min_length=1, max_length=64)
    entity_type: str = Field(..., min_length=1, max_length=64)
    display_label: str | None = Field(default=None, max_length=512)
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    assessment: GraphSearchAssessment | None = Field(
        default=None,
        description="Qualitative assessment for the search result.",
    )
    matching_observation_ids: list[str] = Field(default_factory=list)
    matching_relation_ids: list[str] = Field(default_factory=list)
    evidence_chain: list[EvidenceChainItem] = Field(default_factory=list)
    explanation: str = Field(..., min_length=1, max_length=4000)
    support_summary: str = Field(..., min_length=1, max_length=1000)

    @model_validator(mode="after")
    def _normalize_assessment(self) -> GraphSearchResultEntry:
        if self.assessment is None:
            grounding_level = graph_search_grounding_level_from_counts(
                relation_count=len(self.matching_relation_ids),
                observation_count=len(self.matching_observation_ids),
            )
            rationale = (
                f"Derived from relevance_score={self.relevance_score:.2f} "
                f"and {len(self.matching_relation_ids)} relation(s) / "
                f"{len(self.matching_observation_ids)} observation(s)."
            )
            self.assessment = build_graph_search_assessment_from_confidence(
                self.relevance_score,
                confidence_rationale=rationale,
                grounding_level=grounding_level,
            )
        return self


class GraphSearchContract(EvidenceBackedAgentContract):
    """Contract for Graph Search Agent outputs."""

    decision: Literal["generated", "fallback", "escalate"] = Field(
        ...,
        description="Outcome of the graph-search run",
    )
    research_space_id: str = Field(..., min_length=1, max_length=64)
    original_query: str = Field(..., min_length=1, max_length=2000)
    interpreted_intent: str = Field(..., min_length=1, max_length=2000)
    query_plan_summary: str = Field(..., min_length=1, max_length=4000)
    total_results: int = Field(default=0, ge=0)
    results: list[GraphSearchResultEntry] = Field(default_factory=list)
    assessment: GraphSearchAssessment | None = Field(
        default=None,
        description="Qualitative assessment for the overall search result set.",
    )
    confidence_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Derived numeric weight for routing compatibility.",
    )
    executed_path: Literal["deterministic", "agent", "agent_fallback"] = Field(
        default="deterministic",
    )
    warnings: list[str] = Field(default_factory=list)
    agent_run_id: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def _normalize_assessment(self) -> GraphSearchContract:
        if self.assessment is None:
            if self.results:
                mean_relevance = sum(
                    result.relevance_score for result in self.results
                ) / len(self.results)
                grounding_level = (
                    GraphSearchGroundingLevel.AGGREGATED
                    if any(result.evidence_chain for result in self.results)
                    else GraphSearchGroundingLevel.ENTITY
                )
                rationale = (
                    f"Derived from {len(self.results)} ranked result(s) with "
                    f"mean relevance {mean_relevance:.2f}."
                )
                self.assessment = build_graph_search_assessment_from_confidence(
                    mean_relevance,
                    confidence_rationale=rationale,
                    grounding_level=grounding_level,
                )
            elif self.confidence_score is not None:
                self.assessment = build_graph_search_assessment_from_confidence(
                    self.confidence_score,
                    confidence_rationale=(
                        "Derived from the graph-search summary confidence score."
                    ),
                    grounding_level=GraphSearchGroundingLevel.NONE,
                )
            else:
                self.assessment = build_graph_search_assessment_from_confidence(
                    0.2,
                    confidence_rationale="No ranked graph-search results were produced.",
                    grounding_level=GraphSearchGroundingLevel.NONE,
                )
        self.confidence_score = graph_search_assessment_confidence(self.assessment)
        return self


__all__ = [
    "EvidenceChainItem",
    "GraphSearchContract",
    "GraphSearchResultEntry",
]
