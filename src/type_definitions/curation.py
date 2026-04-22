"""
Curation-related typed contracts.
"""

from __future__ import annotations

from typing import TypedDict


class ReviewRecordLike(TypedDict, total=False):
    """Typed representation of curation review queue records."""

    id: int
    entity_type: str
    entity_id: str
    status: str
    priority: str
    quality_score: float | None
    issues: int
    research_space_id: str | None
    last_updated: object | None


__all__ = ["ReviewRecordLike"]
