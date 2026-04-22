from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SubmittedForReview:
    entity_type: str
    entity_id: str
    priority: str


__all__ = ["SubmittedForReview"]
