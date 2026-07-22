"""Resolve agent-returned text to exact source offsets without semantic inference."""

from __future__ import annotations

from scripts.validation.public_gold.staged_event.generalization.span_identity import (
    ExactSpan,
    SpanIdentityError,
    resolve_unique_span,
)


class GeneralizationAnchorError(ValueError):
    """An evidence or child span cannot be resolved unambiguously."""


ResolvedText = ExactSpan


def resolve_in_context(
    *,
    source: str,
    context_start: int,
    context_end: int,
    exact_evidence: str,
    exact_text: str,
) -> tuple[ResolvedText, ResolvedText]:
    try:
        evidence = resolve_unique_span(
            source=source,
            scope_start=context_start,
            scope_end=context_end,
            exact_text=exact_evidence,
        )
    except SpanIdentityError as exc:
        raise GeneralizationAnchorError(
            "evidence is absent or ambiguous in context"
        ) from exc
    try:
        child = resolve_unique_span(
            source=source,
            scope_start=evidence.start,
            scope_end=evidence.end,
            exact_text=exact_text,
        )
    except SpanIdentityError as exc:
        raise GeneralizationAnchorError(
            "child text is absent or ambiguous in evidence"
        ) from exc
    return evidence, child


def resolve_evidence(
    *, source: str, context_start: int, context_end: int, exact_text: str
) -> ResolvedText:
    try:
        return resolve_unique_span(
            source=source,
            scope_start=context_start,
            scope_end=context_end,
            exact_text=exact_text,
        )
    except SpanIdentityError as exc:
        raise GeneralizationAnchorError(
            "evidence item is absent or ambiguous in context"
        ) from exc


__all__ = [
    "GeneralizationAnchorError",
    "ResolvedText",
    "resolve_evidence",
    "resolve_in_context",
]
