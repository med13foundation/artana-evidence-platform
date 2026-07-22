"""Exact source-span identity with biomedical token-boundary awareness."""

from __future__ import annotations

from dataclasses import dataclass

_TOKEN_CONNECTORS = frozenset("-_‐‑‒–—")


class SpanIdentityError(ValueError):
    """An exact text span is absent or cannot be identified uniquely."""


@dataclass(frozen=True, slots=True)
class ExactSpan:
    start: int
    end: int
    exact_text: str

    def contains(self, other: ExactSpan) -> bool:
        return self.start <= other.start and other.end <= self.end


def token_bounded_spans(
    *, source: str, scope_start: int, scope_end: int, exact_text: str
) -> tuple[ExactSpan, ...]:
    """Return exact occurrences that do not split an alphanumeric/hyphen token."""
    if not exact_text:
        raise SpanIdentityError("exact text must not be empty")
    if not 0 <= scope_start <= scope_end <= len(source):
        raise SpanIdentityError("span scope is outside the source")
    scope = source[scope_start:scope_end]
    matches: list[ExactSpan] = []
    search_start = 0
    while True:
        local_start = scope.find(exact_text, search_start)
        if local_start < 0:
            break
        local_end = local_start + len(exact_text)
        left_ok = not (
            _is_token_character(exact_text[0])
            and local_start > 0
            and _is_token_character(scope[local_start - 1])
        )
        right_ok = not (
            _is_token_character(exact_text[-1])
            and local_end < len(scope)
            and _is_token_character(scope[local_end])
        )
        if left_ok and right_ok:
            start = scope_start + local_start
            matches.append(ExactSpan(start, start + len(exact_text), exact_text))
        search_start = local_start + 1
    return tuple(matches)


def resolve_unique_span(
    *, source: str, scope_start: int, scope_end: int, exact_text: str
) -> ExactSpan:
    matches = token_bounded_spans(
        source=source,
        scope_start=scope_start,
        scope_end=scope_end,
        exact_text=exact_text,
    )
    if len(matches) != 1:
        raise SpanIdentityError("exact text is absent or ambiguous in scope")
    return matches[0]


def source_spans_equivalent(
    *,
    source: str,
    scope_start: int,
    scope_end: int,
    actual_text: str,
    expected_text: str,
) -> bool:
    """Accept only uniquely grounded equal or directly containing exact spans."""
    try:
        actual = resolve_unique_span(
            source=source,
            scope_start=scope_start,
            scope_end=scope_end,
            exact_text=actual_text,
        )
        expected = resolve_unique_span(
            source=source,
            scope_start=scope_start,
            scope_end=scope_end,
            exact_text=expected_text,
        )
    except SpanIdentityError:
        return False
    return actual.contains(expected) or expected.contains(actual)


def _is_token_character(character: str) -> bool:
    return character.isalnum() or character in _TOKEN_CONNECTORS


__all__ = [
    "ExactSpan",
    "SpanIdentityError",
    "resolve_unique_span",
    "source_spans_equivalent",
    "token_bounded_spans",
]
