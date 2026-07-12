"""Agent-only categorical contracts for graph-search execution."""

from __future__ import annotations

from typing import Annotated, Literal

from artana_evidence_api.agent_contracts import (
    EvidenceChainItem,
    GraphSearchAssessment,
    GraphSearchGroundingLevel,
    GraphSearchResultEntry,
    ModelEvidenceCitation,
    graph_search_assessment_confidence,
)
from pydantic import BaseModel, ConfigDict, Field

_Identifier = Annotated[str, Field(min_length=1, max_length=64)]
_GROUNDING_PRIORITY = {
    GraphSearchGroundingLevel.NONE: 0,
    GraphSearchGroundingLevel.ENTITY: 1,
    GraphSearchGroundingLevel.RELATION: 2,
    GraphSearchGroundingLevel.OBSERVATION: 3,
    GraphSearchGroundingLevel.AGGREGATED: 4,
}
if set(_GROUNDING_PRIORITY) != set(GraphSearchGroundingLevel):
    msg = "Graph-search grounding priority must cover every grounding level."
    raise RuntimeError(msg)


class AgentGraphSearchAssessment(GraphSearchAssessment):
    """Fail-closed categorical assessment accepted from the search agent."""

    model_config = ConfigDict(use_enum_values=True, extra="forbid")


class AgentEvidenceChainItem(BaseModel):
    """One categorically assessed graph evidence reference."""

    provenance_id: _Identifier | None = None
    relation_id: _Identifier | None = None
    observation_id: _Identifier | None = None
    evidence_tier: str | None = Field(default=None, min_length=1, max_length=32)
    assessment: AgentGraphSearchAssessment
    evidence_sentence: str | None = Field(default=None, max_length=2000)
    source_ref: str | None = Field(default=None, max_length=1024)

    model_config = ConfigDict(strict=True, extra="forbid")

    def to_public_item(self) -> EvidenceChainItem:
        """Derive the compatibility weight from categorical assessment."""
        return EvidenceChainItem(
            provenance_id=self.provenance_id,
            relation_id=self.relation_id,
            observation_id=self.observation_id,
            evidence_tier=self.evidence_tier,
            assessment=self.assessment,
            evidence_sentence=self.evidence_sentence,
            source_ref=self.source_ref,
        )


class AgentGraphSearchResult(BaseModel):
    """One graph result with categorical relevance and grounding judgments."""

    entity_id: _Identifier
    entity_type: _Identifier
    display_label: str | None = Field(default=None, max_length=512)
    assessment: AgentGraphSearchAssessment
    matching_observation_ids: list[_Identifier] = Field(
        default_factory=list,
        max_length=200,
    )
    matching_relation_ids: list[_Identifier] = Field(
        default_factory=list,
        max_length=200,
    )
    evidence_chain: list[AgentEvidenceChainItem] = Field(
        default_factory=list,
        max_length=200,
    )
    explanation: str = Field(..., min_length=1, max_length=4000)
    support_summary: str = Field(..., min_length=1, max_length=1000)

    model_config = ConfigDict(strict=True, extra="forbid")

    def to_public_result(self) -> GraphSearchResultEntry:
        """Derive ranking weight and evidence weights from categories."""
        return GraphSearchResultEntry(
            entity_id=self.entity_id,
            entity_type=self.entity_type,
            display_label=self.display_label,
            relevance_score=graph_search_assessment_confidence(self.assessment),
            assessment=self.assessment,
            matching_observation_ids=list(dict.fromkeys(self.matching_observation_ids)),
            matching_relation_ids=list(dict.fromkeys(self.matching_relation_ids)),
            evidence_chain=[item.to_public_item() for item in self.evidence_chain],
            explanation=self.explanation,
            support_summary=self.support_summary,
        )


class _GraphSearchExecutionContract(BaseModel):
    """Strict final model output for graph-search execution."""

    assessment: AgentGraphSearchAssessment | None = Field(
        default=None,
        description="Qualitative assessment for the graph-search run.",
    )
    rationale: str | None = Field(default=None, min_length=1, max_length=4000)
    evidence: list[ModelEvidenceCitation] = Field(default_factory=list, max_length=200)
    decision: Literal["generated", "fallback", "escalate"] | None = None
    interpreted_intent: str | None = Field(default=None, min_length=1, max_length=2000)
    query_plan_summary: str | None = Field(default=None, min_length=1, max_length=4000)
    results: list[AgentGraphSearchResult] = Field(default_factory=list, max_length=200)
    warnings: list[str] = Field(default_factory=list, max_length=50)

    model_config = ConfigDict(strict=True, extra="forbid")


def normalize_graph_search_results(
    results: list[AgentGraphSearchResult],
    *,
    limit: int,
) -> list[GraphSearchResultEntry]:
    """Convert, deduplicate, rank, and cap by deterministic policy."""
    normalized = [result.to_public_result() for result in results]
    ranked = sorted(normalized, key=_graph_search_result_rank)
    deduplicated: list[GraphSearchResultEntry] = []
    seen_entity_ids: set[str] = set()
    for result in ranked:
        if result.entity_id in seen_entity_ids:
            continue
        seen_entity_ids.add(result.entity_id)
        deduplicated.append(result)
    return deduplicated[: max(limit, 0)]


def _graph_search_result_rank(
    result: GraphSearchResultEntry,
) -> tuple[float, int, int, int, str]:
    assessment = result.assessment
    if assessment is None:
        return (0.0, 0, 0, 0, result.entity_id)
    return (
        -graph_search_assessment_confidence(assessment),
        -_GROUNDING_PRIORITY[
            GraphSearchGroundingLevel(assessment.grounding_level)
        ],
        -len(result.evidence_chain),
        -(len(result.matching_relation_ids) + len(result.matching_observation_ids)),
        result.entity_id,
    )


__all__ = [
    "AgentEvidenceChainItem",
    "AgentGraphSearchAssessment",
    "AgentGraphSearchResult",
    "_GraphSearchExecutionContract",
    "normalize_graph_search_results",
]
