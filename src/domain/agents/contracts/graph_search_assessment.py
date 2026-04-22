"""Qualitative assessment model for graph-search outputs."""

from __future__ import annotations

from enum import Enum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field


class GraphSearchSupportBand(str, Enum):
    """Coarse support strength for graph-search results."""

    INSUFFICIENT = "INSUFFICIENT"
    TENTATIVE = "TENTATIVE"
    SUPPORTED = "SUPPORTED"
    STRONG = "STRONG"


class GraphSearchGroundingLevel(str, Enum):
    """How directly a graph-search result is grounded in graph evidence."""

    NONE = "NONE"
    ENTITY = "ENTITY"
    RELATION = "RELATION"
    OBSERVATION = "OBSERVATION"
    AGGREGATED = "AGGREGATED"


class GraphSearchAssessment(BaseModel):
    """Structured qualitative assessment for graph-search results and evidence."""

    support_band: GraphSearchSupportBand = Field(
        ...,
        description="Coarse support strength for the search result.",
    )
    grounding_level: GraphSearchGroundingLevel = Field(
        ...,
        description="How directly the result is grounded in graph evidence.",
    )
    confidence_rationale: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Short explanation for why this assessment was chosen.",
    )

    model_config = ConfigDict(use_enum_values=True)


_GRAPH_SEARCH_SUPPORT_BAND_RANKS: dict[GraphSearchSupportBand, int] = {
    GraphSearchSupportBand.INSUFFICIENT: 0,
    GraphSearchSupportBand.TENTATIVE: 1,
    GraphSearchSupportBand.SUPPORTED: 2,
    GraphSearchSupportBand.STRONG: 3,
}

_GRAPH_SEARCH_GROUNDING_LEVEL_RANKS: dict[GraphSearchGroundingLevel, int] = {
    GraphSearchGroundingLevel.NONE: 0,
    GraphSearchGroundingLevel.ENTITY: 1,
    GraphSearchGroundingLevel.RELATION: 2,
    GraphSearchGroundingLevel.OBSERVATION: 2,
    GraphSearchGroundingLevel.AGGREGATED: 3,
}

_GRAPH_SEARCH_SUPPORT_BAND_WEIGHTS: dict[GraphSearchSupportBand, float] = {
    GraphSearchSupportBand.INSUFFICIENT: 0.2,
    GraphSearchSupportBand.TENTATIVE: 0.45,
    GraphSearchSupportBand.SUPPORTED: 0.7,
    GraphSearchSupportBand.STRONG: 0.9,
}

_GRAPH_SEARCH_STRONG_THRESHOLD: Final[float] = 0.85
_GRAPH_SEARCH_SUPPORTED_THRESHOLD: Final[float] = 0.7
_GRAPH_SEARCH_TENTATIVE_THRESHOLD: Final[float] = 0.45
_GRAPH_SEARCH_NONE_GROUNDING_CAP: Final[float] = 0.4


def build_graph_search_assessment_from_confidence(
    confidence: float,
    *,
    confidence_rationale: str,
    grounding_level: GraphSearchGroundingLevel,
) -> GraphSearchAssessment:
    """Convert a legacy numeric score into a qualitative graph-search assessment."""
    if confidence >= _GRAPH_SEARCH_STRONG_THRESHOLD:
        support_band = GraphSearchSupportBand.STRONG
    elif confidence >= _GRAPH_SEARCH_SUPPORTED_THRESHOLD:
        support_band = GraphSearchSupportBand.SUPPORTED
    elif confidence >= _GRAPH_SEARCH_TENTATIVE_THRESHOLD:
        support_band = GraphSearchSupportBand.TENTATIVE
    else:
        support_band = GraphSearchSupportBand.INSUFFICIENT
    return GraphSearchAssessment(
        support_band=support_band,
        grounding_level=grounding_level,
        confidence_rationale=confidence_rationale,
    )


def graph_search_assessment_confidence(assessment: GraphSearchAssessment) -> float:
    """Derive a deterministic numeric weight from a qualitative assessment."""
    support_band = GraphSearchSupportBand(assessment.support_band)
    grounding_level = GraphSearchGroundingLevel(assessment.grounding_level)
    base_weight = _GRAPH_SEARCH_SUPPORT_BAND_WEIGHTS[support_band]
    capped_weight = min(
        base_weight,
        (
            1.0
            if grounding_level != GraphSearchGroundingLevel.NONE
            else _GRAPH_SEARCH_NONE_GROUNDING_CAP
        ),
    )
    return max(0.0, min(capped_weight, 1.0))


def graph_search_assessment_priority(
    assessment: GraphSearchAssessment,
) -> tuple[int, int]:
    """Return a deterministic ordering key for comparison and merging."""
    return (
        _GRAPH_SEARCH_SUPPORT_BAND_RANKS[
            GraphSearchSupportBand(assessment.support_band)
        ],
        _GRAPH_SEARCH_GROUNDING_LEVEL_RANKS[
            GraphSearchGroundingLevel(assessment.grounding_level)
        ],
    )


def is_stronger_graph_search_assessment(
    candidate: GraphSearchAssessment,
    existing: GraphSearchAssessment,
) -> bool:
    """Return True when the candidate should replace the existing assessment."""
    return graph_search_assessment_priority(
        candidate,
    ) > graph_search_assessment_priority(
        existing,
    )


def graph_search_support_band_from_confidence(
    confidence: float,
) -> GraphSearchSupportBand:
    """Map a numeric score into a graph-search support band."""
    if confidence >= _GRAPH_SEARCH_STRONG_THRESHOLD:
        return GraphSearchSupportBand.STRONG
    if confidence >= _GRAPH_SEARCH_SUPPORTED_THRESHOLD:
        return GraphSearchSupportBand.SUPPORTED
    if confidence >= _GRAPH_SEARCH_TENTATIVE_THRESHOLD:
        return GraphSearchSupportBand.TENTATIVE
    return GraphSearchSupportBand.INSUFFICIENT


def graph_search_grounding_level_from_counts(
    *,
    relation_count: int,
    observation_count: int,
) -> GraphSearchGroundingLevel:
    """Infer a grounding level from the available graph evidence counts."""
    if relation_count > 0 and observation_count > 0:
        return GraphSearchGroundingLevel.AGGREGATED
    if observation_count > 0:
        return GraphSearchGroundingLevel.OBSERVATION
    if relation_count > 0:
        return GraphSearchGroundingLevel.RELATION
    return GraphSearchGroundingLevel.ENTITY


__all__ = [
    "GraphSearchAssessment",
    "GraphSearchGroundingLevel",
    "GraphSearchSupportBand",
    "build_graph_search_assessment_from_confidence",
    "graph_search_assessment_confidence",
    "graph_search_assessment_priority",
    "graph_search_grounding_level_from_counts",
    "graph_search_support_band_from_confidence",
    "is_stronger_graph_search_assessment",
]
