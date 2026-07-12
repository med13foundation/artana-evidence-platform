"""Deterministic source-text options for semantic agent grounding."""

from __future__ import annotations

import re
from dataclasses import dataclass

from artana_evidence_api.types.common import JSONObject, JSONValue

_MAX_EVIDENCE_OPTION_CHARACTERS = 500
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True, slots=True)
class SemanticEvidenceOption:
    """One immutable source span that an agent may reference by identity."""

    reference: str
    text: str


def semantic_evidence_options(
    *,
    record_index: int,
    record: JSONObject,
) -> tuple[SemanticEvidenceOption, ...]:
    """Expose exact bounded spans without asking the model to transcribe them."""

    spans = tuple(
        span
        for value in _source_string_values(record)
        for span in _bounded_source_spans(value)
        if span
    )
    return tuple(
        SemanticEvidenceOption(
            reference=f"record:{record_index}:evidence:{option_index}",
            text=span,
        )
        for option_index, span in enumerate(dict.fromkeys(spans))
    )


def resolve_semantic_evidence_references(
    *,
    record_index: int,
    record: JSONObject,
    references: tuple[str, ...],
) -> tuple[str, ...]:
    """Resolve only references owned by this exact record."""

    options = {
        option.reference: option.text
        for option in semantic_evidence_options(
            record_index=record_index,
            record=record,
        )
    }
    unknown = tuple(reference for reference in references if reference not in options)
    if unknown:
        msg = (
            f"semantic agent returned unknown evidence references for record "
            f"{record_index}: {list(unknown)}"
        )
        raise ValueError(msg)
    return tuple(options[reference] for reference in references)


def _bounded_source_spans(value: str) -> tuple[str, ...]:
    normalized = value.strip()
    if not normalized:
        return ()
    sentences = tuple(
        sentence.strip()
        for sentence in _SENTENCE_BOUNDARY.split(normalized)
        if sentence.strip()
    )
    spans: list[str] = []
    for sentence in sentences:
        spans.extend(
            sentence[offset : offset + _MAX_EVIDENCE_OPTION_CHARACTERS]
            for offset in range(0, len(sentence), _MAX_EVIDENCE_OPTION_CHARACTERS)
        )
    return tuple(spans)


def _source_string_values(value: JSONValue) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, dict):
        return tuple(
            text for nested in value.values() for text in _source_string_values(nested)
        )
    if isinstance(value, list | tuple):
        return tuple(text for nested in value for text in _source_string_values(nested))
    return ()


__all__ = [
    "SemanticEvidenceOption",
    "resolve_semantic_evidence_references",
    "semantic_evidence_options",
]
