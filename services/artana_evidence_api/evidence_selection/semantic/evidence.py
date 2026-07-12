"""Deterministic source-text options for semantic agent grounding."""

from __future__ import annotations

import re
from dataclasses import dataclass

from artana_evidence_api.types.common import JSONObject, JSONValue

_MAX_EVIDENCE_OPTION_CHARACTERS = 500
_MAX_EVIDENCE_OPTIONS_PER_RECORD = 64
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True, slots=True)
class SemanticEvidenceOption:
    """One immutable source span that an agent may reference by identity."""

    reference: str
    source_path: str
    text: str


def semantic_evidence_options(
    *,
    record_index: int,
    record: JSONObject,
) -> tuple[SemanticEvidenceOption, ...]:
    """Expose exact bounded spans without asking the model to transcribe them."""

    options: list[SemanticEvidenceOption] = []
    seen_text: set[str] = set()
    for source_path, value in _source_string_values(record):
        for span in _bounded_source_spans(value):
            if not span or span in seen_text:
                continue
            seen_text.add(span)
            options.append(
                SemanticEvidenceOption(
                    reference=(f"record:{record_index}:evidence:{len(options)}"),
                    source_path=source_path,
                    text=span,
                ),
            )
            if len(options) >= _MAX_EVIDENCE_OPTIONS_PER_RECORD:
                return tuple(options)
    return tuple(options)


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


def _source_string_values(
    value: JSONValue,
    *,
    path: str = "$",
) -> tuple[tuple[str, str], ...]:
    if isinstance(value, str):
        return ((path, value),)
    if isinstance(value, dict):
        return tuple(
            item
            for key, nested in value.items()
            for item in _source_string_values(nested, path=f"{path}.{key}")
        )
    if isinstance(value, list | tuple):
        return tuple(
            item
            for index, nested in enumerate(value)
            for item in _source_string_values(nested, path=f"{path}[{index}]")
        )
    return ()


__all__ = [
    "SemanticEvidenceOption",
    "resolve_semantic_evidence_references",
    "semantic_evidence_options",
]
