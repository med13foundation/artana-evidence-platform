"""Fail-closed validation of declared absolute source spans."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from scripts.validation.public_gold.staged_event.generalization.span_identity import (
    ExactSpan,
    SpanIdentityError,
    token_bounded_spans,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.occurrence_evaluator_v2.contracts import (
        AbsoluteSourceSpan,
        MentionIdentity,
    )


class OccurrenceResolutionError(ValueError):
    """An explicit occurrence identity does not match the frozen source."""


@dataclass(frozen=True, slots=True)
class SourceScope:
    """Frozen source text and the only permitted context for one case."""

    source: str
    context_start: int
    context_end: int

    def __post_init__(self) -> None:
        if not 0 <= self.context_start <= self.context_end <= len(self.source):
            raise OccurrenceResolutionError("permitted context is outside the source")


def resolve_declared_span(
    *,
    scope: SourceScope,
    declared_text: str,
    offsets: AbsoluteSourceSpan,
    label: str,
    require_token_boundaries: bool,
) -> ExactSpan:
    """Validate one absolute span against source text and permitted context."""

    if offsets.end > len(scope.source):
        raise OccurrenceResolutionError(f"{label} offsets are outside the source")
    if offsets.start < scope.context_start or offsets.end > scope.context_end:
        raise OccurrenceResolutionError(
            f"{label} offsets are outside the permitted context"
        )
    if scope.source[offsets.start : offsets.end] != declared_text:
        raise OccurrenceResolutionError(
            f"{label} offsets do not reproduce the declared text"
        )
    resolved = ExactSpan(offsets.start, offsets.end, declared_text)
    if require_token_boundaries:
        try:
            candidates = token_bounded_spans(
                source=scope.source,
                scope_start=scope.context_start,
                scope_end=scope.context_end,
                exact_text=declared_text,
            )
        except SpanIdentityError as exc:
            raise OccurrenceResolutionError(
                f"{label} is not a valid token-bounded source span"
            ) from exc
        if resolved not in candidates:
            raise OccurrenceResolutionError(
                f"{label} offsets split a source token"
            )
    return resolved


def resolve_mention_identity(
    *,
    scope: SourceScope,
    declared_evidence: str,
    declared_mention: str,
    identity: MentionIdentity,
) -> tuple[ExactSpan, ExactSpan]:
    """Resolve an evidence span and its selected child mention."""

    evidence = resolve_declared_span(
        scope=scope,
        declared_text=declared_evidence,
        offsets=identity.evidence_span,
        label="evidence",
        require_token_boundaries=False,
    )
    mention = resolve_declared_span(
        scope=scope,
        declared_text=declared_mention,
        offsets=identity.mention_span,
        label="mention",
        require_token_boundaries=True,
    )
    if not evidence.contains(mention):
        raise OccurrenceResolutionError(
            "mention offsets are outside the declared evidence"
        )
    return evidence, mention


__all__ = [
    "OccurrenceResolutionError",
    "SourceScope",
    "resolve_declared_span",
    "resolve_mention_identity",
]
