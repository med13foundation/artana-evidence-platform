"""
Search-related typed contracts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from src.type_definitions.common import JSONObject


class RawSearchResult(TypedDict):
    """Raw search result payload from the service."""

    entity_type: str
    entity_id: int | str
    title: str
    description: str
    relevance_score: float
    metadata: JSONObject


class UnifiedSearchPayload(TypedDict, total=False):
    """Typed representation of the unified search payload."""

    query: str
    total_results: int
    entity_breakdown: dict[str, int]
    results: list[RawSearchResult]


__all__ = ["RawSearchResult", "UnifiedSearchPayload"]
