"""Deterministic source localization for agent-authored mention anchors."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ClaimMentionAnchor(BaseModel):
    """Verbatim neighboring text that identifies one source mention."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    mention_span: str = Field(..., min_length=1, max_length=1000)
    left_context: str = Field(default="", max_length=500)
    right_context: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def require_context(self) -> ClaimMentionAnchor:
        if not self.left_context and not self.right_context:
            raise ValueError("mention anchor requires left or right verbatim context")
        return self


@dataclass(frozen=True, slots=True)
class BoundClaimMention:
    """One mention localized by deterministic code."""

    exact_span: str
    source_start: int
    source_end: int


class MentionBindingError(ValueError):
    """Raised when verbatim context does not identify a unique mention."""


class MentionAnchorContract(Protocol):
    mention_span: str
    left_context: str
    right_context: str


def bind_source_mentions(
    *,
    canonical_span: str,
    source_span: str,
    anchors: Sequence[MentionAnchorContract] = (),
    source_start_offset: int = 0,
) -> tuple[BoundClaimMention, ...]:
    """Resolve one semantic participant to one or more verbatim mentions."""

    if not anchors:
        occurrences = _occurrence_starts(source_span, canonical_span)
        if not occurrences:
            raise MentionBindingError("mention exact_span is outside the source span")
        if len(occurrences) != 1:
            raise MentionBindingError(
                "repeated mention exact_span requires a verbatim context anchor",
            )
        return (_bound_mention(canonical_span, occurrences[0], source_start_offset),)

    if not any(anchor.mention_span == canonical_span for anchor in anchors):
        raise MentionBindingError(
            "mention anchors must include the semantic argument's canonical span",
        )

    selected: list[tuple[str, int]] = []
    for anchor in anchors:
        occurrences = _occurrence_starts(source_span, anchor.mention_span)
        matches = tuple(
            start
            for start in occurrences
            if _anchor_matches(
                source_span=source_span,
                exact_span=anchor.mention_span,
                start=start,
                anchor=anchor,
            )
        )
        if len(matches) != 1:
            raise MentionBindingError(
                "verbatim mention context must identify exactly one occurrence",
            )
        mention_identity = (anchor.mention_span, matches[0])
        if mention_identity in selected:
            raise MentionBindingError(
                "multiple mention anchors resolve to the same source occurrence",
            )
        selected.append(mention_identity)
    return tuple(
        _bound_mention(mention_span, start, source_start_offset)
        for mention_span, start in sorted(selected, key=lambda item: item[1])
    )


def _occurrence_starts(source_span: str, exact_span: str) -> tuple[int, ...]:
    starts: list[int] = []
    search_from = 0
    while True:
        start = source_span.find(exact_span, search_from)
        if start < 0:
            return tuple(starts)
        starts.append(start)
        search_from = start + 1


def _anchor_matches(
    *,
    source_span: str,
    exact_span: str,
    start: int,
    anchor: MentionAnchorContract,
) -> bool:
    left_start = start - len(anchor.left_context)
    if left_start < 0 or source_span[left_start:start] != anchor.left_context:
        return False
    end = start + len(exact_span)
    return source_span[end : end + len(anchor.right_context)] == anchor.right_context


def _bound_mention(
    exact_span: str,
    relative_start: int,
    source_start_offset: int,
) -> BoundClaimMention:
    absolute_start = source_start_offset + relative_start
    return BoundClaimMention(
        exact_span=exact_span,
        source_start=absolute_start,
        source_end=absolute_start + len(exact_span),
    )


__all__ = [
    "BoundClaimMention",
    "ClaimMentionAnchor",
    "MentionBindingError",
    "bind_source_mentions",
]
