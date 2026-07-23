"""Occurrence-aware comparison with frozen acceptable source texts."""

from __future__ import annotations

from scripts.validation.public_gold.staged_event.generalization.span_identity import (
    ExactSpan,
    token_bounded_spans,
)


def mention_matches_any(
    *,
    source: str,
    evidence: ExactSpan,
    mention: ExactSpan,
    acceptable_texts: tuple[str, ...],
) -> bool:
    """Match a selected occurrence to an acceptable span within its evidence."""

    return any(
        _spans_overlap_by_containment(mention, expected)
        for acceptable in acceptable_texts
        for expected in token_bounded_spans(
            source=source,
            scope_start=evidence.start,
            scope_end=evidence.end,
            exact_text=acceptable,
        )
    )


def source_span_matches_any(
    *,
    source: str,
    context_start: int,
    context_end: int,
    actual: ExactSpan,
    acceptable_texts: tuple[str, ...],
) -> bool:
    """Match an already validated absolute span to frozen acceptable texts."""

    return any(
        _spans_overlap_by_containment(actual, expected)
        for acceptable in acceptable_texts
        for expected in token_bounded_spans(
            source=source,
            scope_start=context_start,
            scope_end=context_end,
            exact_text=acceptable,
        )
    )


def _spans_overlap_by_containment(first: ExactSpan, second: ExactSpan) -> bool:
    return first.contains(second) or second.contains(first)


__all__ = ["mention_matches_any", "source_span_matches_any"]
