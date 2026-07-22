"""Deterministic event-local resolution of agent-returned exact source text."""

from __future__ import annotations

from dataclasses import dataclass


class AnchorResolutionError(ValueError):
    """Exact text cannot be resolved uniquely inside its permitted scope."""


@dataclass(frozen=True, slots=True)
class ResolvedAnchor:
    start: int
    end: int
    exact_text: str
    evidence_start: int
    evidence_end: int
    exact_evidence: str


def resolve_anchor(
    *,
    source: str,
    scope_start: int,
    scope_end: int,
    exact_text: str,
    exact_evidence: str,
) -> ResolvedAnchor:
    """Resolve one exact mention through its exact containing evidence."""

    if not 0 <= scope_start < scope_end <= len(source):
        raise AnchorResolutionError("invalid permitted scope")
    if not exact_text or not exact_evidence:
        raise AnchorResolutionError("exact text and evidence are required")
    scope = source[scope_start:scope_end]
    evidence_offsets = _occurrences(scope, exact_evidence)
    if not evidence_offsets:
        raise AnchorResolutionError("evidence text is absent from permitted scope")
    candidates: list[tuple[int, int]] = []
    for evidence_local in evidence_offsets:
        mention_offsets = _occurrences(exact_evidence, exact_text)
        candidates.extend(
            (evidence_local, mention_local) for mention_local in mention_offsets
        )
    if not candidates:
        raise AnchorResolutionError("exact text is absent from supplied evidence")
    absolute = {
        (
            scope_start + evidence_local + mention_local,
            scope_start + evidence_local + mention_local + len(exact_text),
            scope_start + evidence_local,
            scope_start + evidence_local + len(exact_evidence),
        )
        for evidence_local, mention_local in candidates
    }
    if len(absolute) != 1:
        raise AnchorResolutionError("exact text remains ambiguous in supplied evidence")
    start, end, evidence_start, evidence_end = absolute.pop()
    return ResolvedAnchor(
        start=start,
        end=end,
        exact_text=exact_text,
        evidence_start=evidence_start,
        evidence_end=evidence_end,
        exact_evidence=exact_evidence,
    )


def _occurrences(value: str, target: str) -> tuple[int, ...]:
    found: list[int] = []
    cursor = 0
    while True:
        offset = value.find(target, cursor)
        if offset < 0:
            return tuple(found)
        found.append(offset)
        cursor = offset + 1


__all__ = ["AnchorResolutionError", "ResolvedAnchor", "resolve_anchor"]
