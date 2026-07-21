"""Deterministically preflight public gold against Artana's current contract."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.validation.public_gold.bionlp_cg_adapter import Document, Event

SUPPORTED_EVENT_TYPES = frozenset(
    {
        "Binding",
        "Gene_expression",
        "Localization",
        "Negative_regulation",
        "Phosphorylation",
        "Positive_regulation",
        "Regulation",
        "Transcription",
    }
)
SUPPORTED_ARGUMENT_ROLES = frozenset(
    {"AtLoc", "CSite", "Cause", "FromLoc", "Site", "Theme", "ToLoc"}
)
MINIMUM_ARTANA_ARGUMENTS = 2
_ROLE_ORDINAL = re.compile(r"\d+$")


@dataclass(frozen=True, slots=True)
class RepresentabilityReport:
    total_events: int
    representable_events: int
    excluded_by_reason: dict[str, int]
    blockers_by_dimension: dict[str, int]

    @property
    def representable_rate(self) -> float | None:
        return self.representable_events / self.total_events if self.total_events else None


def analyze_cancer_genetics(documents: tuple[Document, ...]) -> RepresentabilityReport:
    """Count exact structural incompatibilities without interpreting science."""

    reasons: Counter[str] = Counter()
    dimensions: Counter[str] = Counter()
    total = representable = 0
    for document in documents:
        event_ids = {event.event_id for event in document.events}
        for event in document.events:
            total += 1
            blockers = _blockers(event, event_ids)
            dimensions.update(blockers)
            if not blockers:
                representable += 1
            else:
                reasons[blockers[0]] += 1
    return RepresentabilityReport(
        total,
        representable,
        dict(sorted(reasons.items())),
        dict(sorted(dimensions.items())),
    )


def _blockers(event: Event, event_ids: set[str]) -> tuple[str, ...]:
    blockers: list[str] = []
    if event.event_type not in SUPPORTED_EVENT_TYPES:
        blockers.append("UNSUPPORTED_EVENT_TYPE")
    if any(
        _base_role(argument.role) not in SUPPORTED_ARGUMENT_ROLES
        for argument in event.arguments
    ):
        blockers.append("UNSUPPORTED_ARGUMENT_ROLE")
    if any(argument.target_id in event_ids for argument in event.arguments):
        blockers.append("NESTED_EVENT_ARGUMENT")
    if len({argument.target_id for argument in event.arguments}) < MINIMUM_ARTANA_ARGUMENTS:
        blockers.append("INSUFFICIENT_DIRECT_ARGUMENTS")
    return tuple(blockers)


def _base_role(role: str) -> str:
    """Remove BioNLP's argument ordinal without changing its semantic role."""

    return _ROLE_ORDINAL.sub("", role)


__all__ = ["RepresentabilityReport", "analyze_cancer_genetics"]
