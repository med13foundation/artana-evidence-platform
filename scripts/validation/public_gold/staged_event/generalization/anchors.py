"""Resolve agent-returned text to exact source offsets without semantic inference."""

from __future__ import annotations

from dataclasses import dataclass


class GeneralizationAnchorError(ValueError):
    """An evidence or child span cannot be resolved unambiguously."""


@dataclass(frozen=True, slots=True)
class ResolvedText:
    start: int
    end: int
    exact_text: str


def resolve_in_context(
    *,
    source: str,
    context_start: int,
    context_end: int,
    exact_evidence: str,
    exact_text: str,
) -> tuple[ResolvedText, ResolvedText]:
    if source[context_start:context_end].count(exact_evidence) != 1:
        raise GeneralizationAnchorError("evidence is absent or ambiguous in context")
    evidence_local = source[context_start:context_end].find(exact_evidence)
    evidence_start = context_start + evidence_local
    if exact_evidence.count(exact_text) != 1:
        raise GeneralizationAnchorError("child text is absent or ambiguous in evidence")
    child_start = evidence_start + exact_evidence.find(exact_text)
    evidence = ResolvedText(
        evidence_start,
        evidence_start + len(exact_evidence),
        exact_evidence,
    )
    child = ResolvedText(child_start, child_start + len(exact_text), exact_text)
    if source[evidence.start : evidence.end] != evidence.exact_text:
        raise GeneralizationAnchorError("evidence does not match source offsets")
    if source[child.start : child.end] != child.exact_text:
        raise GeneralizationAnchorError("child text does not match source offsets")
    return evidence, child


def resolve_evidence(
    *, source: str, context_start: int, context_end: int, exact_text: str
) -> ResolvedText:
    context = source[context_start:context_end]
    if context.count(exact_text) != 1:
        raise GeneralizationAnchorError(
            "evidence item is absent or ambiguous in context"
        )
    start = context_start + context.find(exact_text)
    return ResolvedText(start, start + len(exact_text), exact_text)


__all__ = [
    "GeneralizationAnchorError",
    "ResolvedText",
    "resolve_evidence",
    "resolve_in_context",
]
