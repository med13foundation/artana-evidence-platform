"""Deterministic helpers for relation-level evidence span extraction/validation."""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.type_definitions.common import JSONObject  # noqa: TC001

_MIN_SPAN_CHARS = 24
_MAX_SPAN_CHARS = 500
_MIN_SPAN_TOKENS = 4
_MIN_LABEL_TOKEN_LENGTH = 3
_MAX_SOURCE_TEXT_CHARS = 120_000
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "with",
    },
)
_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")
_WHITESPACE_PATTERN = re.compile(r"\s+")
_GENERIC_SPAN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bextracted from source_document\b", re.IGNORECASE),
    re.compile(r"\bvalidation:\b", re.IGNORECASE),
    re.compile(r"\bgovernance_override:\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class RelationEvidenceSpanResult:
    """Resolved evidence span candidate plus diagnostic metadata."""

    span_text: str | None
    metadata: JSONObject
    failure_reason: str | None = None


def normalize_span_text(raw_value: str | None) -> str | None:
    """Trim and normalize whitespace for evidence span text."""
    if not isinstance(raw_value, str):
        return None
    normalized = _WHITESPACE_PATTERN.sub(" ", raw_value.strip())
    if not normalized:
        return None
    return normalized[:_MAX_SPAN_CHARS]


def extract_document_text(raw_record: JSONObject) -> tuple[str | None, str | None]:
    """Resolve best-available source text for span derivation."""
    for field_name in ("full_text", "text", "abstract", "title"):
        value = raw_record.get(field_name)
        if not isinstance(value, str):
            continue
        normalized = _WHITESPACE_PATTERN.sub(" ", value.strip())
        if not normalized:
            continue
        return normalized[:_MAX_SOURCE_TEXT_CHARS], field_name
    return None, None


def resolve_relation_evidence_span(
    *,
    source_label: str | None,
    target_label: str | None,
    candidate_excerpt: str | None,
    candidate_locator: str | None,
    raw_record: JSONObject,
) -> RelationEvidenceSpanResult:
    """Return a validated span using candidate excerpt first, then text derivation."""
    normalized_excerpt = normalize_span_text(candidate_excerpt)
    normalized_locator = normalize_span_text(candidate_locator)
    if normalized_excerpt is not None:
        if _is_valid_span(
            span_text=normalized_excerpt,
            source_label=source_label,
            target_label=target_label,
        ):
            return RelationEvidenceSpanResult(
                span_text=normalized_excerpt,
                metadata={
                    "span_source": "candidate_excerpt",
                    "span_locator": normalized_locator,
                },
            )
        return RelationEvidenceSpanResult(
            span_text=None,
            failure_reason="candidate_evidence_excerpt_invalid",
            metadata={
                "span_source": "candidate_excerpt",
                "span_locator": normalized_locator,
            },
        )

    source_text, text_field = extract_document_text(raw_record)
    if source_text is None or text_field is None:
        return RelationEvidenceSpanResult(
            span_text=None,
            failure_reason="document_text_unavailable",
            metadata={"span_source": "none"},
        )

    derived_span = _derive_cooccurrence_span(
        text=source_text,
        source_label=source_label,
        target_label=target_label,
    )
    if derived_span is None:
        return RelationEvidenceSpanResult(
            span_text=None,
            failure_reason="cooccurrence_span_not_found",
            metadata={
                "span_source": "derived",
                "span_text_field": text_field,
            },
        )
    if not _is_valid_span(
        span_text=derived_span,
        source_label=source_label,
        target_label=target_label,
    ):
        return RelationEvidenceSpanResult(
            span_text=None,
            failure_reason="derived_span_invalid",
            metadata={
                "span_source": "derived",
                "span_text_field": text_field,
            },
        )
    return RelationEvidenceSpanResult(
        span_text=derived_span,
        metadata={
            "span_source": "derived",
            "span_text_field": text_field,
        },
    )


def append_span_to_summary(*, base_summary: str, span_text: str) -> str:
    """Append a bounded span excerpt to a relation evidence summary."""
    excerpt = normalize_span_text(span_text) or span_text.strip()
    return f"{base_summary} | span:{excerpt}"


def _derive_cooccurrence_span(
    *,
    text: str,
    source_label: str | None,
    target_label: str | None,
) -> str | None:
    normalized_text = _WHITESPACE_PATTERN.sub(" ", text.strip())
    if not normalized_text:
        return None
    sentences = [
        segment.strip() for segment in _SENTENCE_SPLIT_PATTERN.split(normalized_text)
    ]
    sentences = [segment for segment in sentences if segment]
    if not sentences:
        return None

    for window_size in (1, 2):
        max_start = len(sentences) - window_size + 1
        for start_index in range(max_start):
            window = " ".join(
                sentences[start_index : start_index + window_size],
            ).strip()
            if not window:
                continue
            if not _span_mentions_label(window, source_label):
                continue
            if not _span_mentions_label(window, target_label):
                continue
            return normalize_span_text(window)
    return None


def _is_valid_span(
    *,
    span_text: str,
    source_label: str | None,
    target_label: str | None,
) -> bool:
    valid_length = _MIN_SPAN_CHARS <= len(span_text) <= _MAX_SPAN_CHARS
    has_alnum = any(char.isalnum() for char in span_text)
    token_count = len(re.findall(r"[A-Za-z0-9]+", span_text))
    has_tokens = token_count >= _MIN_SPAN_TOKENS
    lowered = span_text.lower()
    has_generic_noise = any(
        pattern.search(lowered) for pattern in _GENERIC_SPAN_PATTERNS
    )
    mentions_source = _span_mentions_label(span_text, source_label)
    mentions_target = _span_mentions_label(span_text, target_label)
    return (
        valid_length
        and has_alnum
        and has_tokens
        and not has_generic_noise
        and mentions_source
        and mentions_target
    )


def _span_mentions_label(span_text: str, label: str | None) -> bool:
    normalized_label = normalize_span_text(label)
    if normalized_label is None:
        return True
    normalized_span = f" {span_text.lower()} "
    label_lowered = normalized_label.lower()
    if f" {label_lowered} " in normalized_span:
        return True
    label_tokens = [
        token
        for token in re.findall(r"[A-Za-z0-9]+", label_lowered)
        if len(token) >= _MIN_LABEL_TOKEN_LENGTH and token not in _STOPWORDS
    ]
    if not label_tokens:
        return True
    return any(f" {token} " in normalized_span for token in label_tokens)


__all__ = [
    "RelationEvidenceSpanResult",
    "append_span_to_summary",
    "resolve_relation_evidence_span",
]
