"""Typed contracts for extracted-entity grounding decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

CurieSource = Literal["none", "model", "verified_linker"]
ModelHintStatus = Literal["matched", "replaced", "invalid"]
GroundingDecisionKind = Literal[
    "verified",
    "model_hint_only",
    "review_only",
    "ambiguous",
    "unsupported_namespace",
    "missing",
]


@dataclass(frozen=True, slots=True)
class EntityGroundingCandidate:
    """Input label and optional hint being evaluated for trust."""

    label: str
    raw_curie: str | None
    source: CurieSource


@dataclass(frozen=True, slots=True)
class VerifiedEntityRecord:
    """A locally curated entity label that may produce a trusted identifier."""

    label: str
    curie: str
    aliases: tuple[str, ...] = ()
    relation_match_aliases: tuple[str, ...] = ()
    curation_status: str = "approved_for_relation_feasibility_v2"


@dataclass(frozen=True, slots=True)
class ReviewOnlyEntityRecord:
    """A known label that must stay review-only until a safe concept exists."""

    label: str
    reason: str = "grounding_requires_review"
    aliases: tuple[str, ...] = ()
    curation_status: str = "review_only_for_relation_feasibility_v2"


class EntityGrounder(Protocol):
    """Lookup interface for grounding implementations."""

    def verified_record_for_label(self, label: str) -> VerifiedEntityRecord | None:
        """Return a trusted record for the label when local curation allows it."""

    def review_only_record_for_label(
        self,
        label: str,
    ) -> ReviewOnlyEntityRecord | None:
        """Return a review-only record for labels that must not auto-promote."""


__all__ = [
    "CurieSource",
    "EntityGrounder",
    "EntityGroundingCandidate",
    "GroundingDecisionKind",
    "ModelHintStatus",
    "ReviewOnlyEntityRecord",
    "VerifiedEntityRecord",
]
