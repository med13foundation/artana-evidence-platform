"""Resolve independent agent evidence items without semantic inference."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.context_experiment.role_alignment.contracts import (
        EvidenceItem,
    )


class EvidenceResolutionError(ValueError):
    """An evidence item is not an exact, unique, local source span."""


@dataclass(frozen=True, slots=True)
class ResolvedEvidenceItem:
    start: int
    end: int
    exact_text: str


def resolve_evidence_items(
    items: tuple[EvidenceItem, ...],
    *,
    source: str,
    scope_start: int,
    scope_end: int,
    required_texts: tuple[str, ...],
) -> tuple[ResolvedEvidenceItem, ...]:
    scope = source[scope_start:scope_end]
    resolved: list[ResolvedEvidenceItem] = []
    for item in items:
        text = item.exact_text
        if '" "' in text or "' '" in text:
            raise EvidenceResolutionError(
                "concatenated quotations are not evidence items"
            )
        first = scope.find(text)
        if first < 0:
            raise EvidenceResolutionError(
                "evidence text is absent from permitted scope"
            )
        if scope.find(text, first + 1) >= 0:
            raise EvidenceResolutionError(
                "evidence text is ambiguous in permitted scope"
            )
        resolved.append(
            ResolvedEvidenceItem(
                start=scope_start + first,
                end=scope_start + first + len(text),
                exact_text=text,
            )
        )
    combined = " ".join(item.exact_text for item in resolved)
    if any(required not in combined for required in required_texts):
        raise EvidenceResolutionError(
            "evidence items must cover both the trigger and participant"
        )
    return tuple(resolved)


__all__ = [
    "EvidenceResolutionError",
    "ResolvedEvidenceItem",
    "resolve_evidence_items",
]
