"""Deterministic source-text options for semantic agent grounding."""

from __future__ import annotations

import math
import re
from collections.abc import Iterator
from dataclasses import dataclass

from artana_evidence_api.types.common import JSONObject, JSONValue

_MAX_EVIDENCE_OPTION_CHARACTERS = 500
_MAX_EVIDENCE_OPTIONS_PER_RECORD = 64
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
_PRIORITY_SOURCE_FIELDS = (
    "title",
    "brief_title",
    "official_title",
    "name",
    "label",
    "gene_symbol",
    "resolved_variant",
    "hgvs_notation",
    "variant",
    "variant_id",
    "rsid",
    "accession",
    "uniprot_id",
    "abstract",
    "summary",
    "description",
    "population",
    "intervention",
    "outcome",
    "study_type",
    "allele_frequency",
    "af",
    "allele_count",
    "ac",
    "allele_number",
    "an",
)


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
    seen_groundings: set[tuple[str, str]] = set()
    for source_path, value in _iter_record_evidence_values(record):
        for span in _iter_bounded_source_spans(value):
            grounding_key = (source_path, span)
            if not span or grounding_key in seen_groundings:
                continue
            seen_groundings.add(grounding_key)
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


def _iter_record_evidence_values(record: JSONObject) -> Iterator[tuple[str, str]]:
    prioritized = frozenset(_PRIORITY_SOURCE_FIELDS)
    for key in _PRIORITY_SOURCE_FIELDS:
        if key in record:
            yield from _iter_source_evidence_values(record[key], path=f"$.{key}")
    for key, value in record.items():
        if key not in prioritized:
            yield from _iter_source_evidence_values(value, path=f"$.{key}")


def resolve_semantic_evidence_references(
    *,
    record_index: int,
    record: JSONObject,
    references: tuple[str, ...],
) -> tuple[SemanticEvidenceOption, ...]:
    """Resolve only references owned by this exact record."""

    options = {
        option.reference: option
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


def _iter_bounded_source_spans(value: str) -> Iterator[str]:
    normalized = value.strip()
    if not normalized:
        return
    for raw_sentence in _SENTENCE_BOUNDARY.split(normalized):
        sentence = raw_sentence.strip()
        if not sentence:
            continue
        for offset in range(0, len(sentence), _MAX_EVIDENCE_OPTION_CHARACTERS):
            yield sentence[offset : offset + _MAX_EVIDENCE_OPTION_CHARACTERS]


def _iter_source_evidence_values(
    value: JSONValue,
    *,
    path: str = "$",
) -> Iterator[tuple[str, str]]:
    scalar_text = _scalar_evidence_text(value)
    if scalar_text is not None:
        yield path, scalar_text
        return
    if isinstance(value, dict):
        for key, nested in value.items():
            yield from _iter_source_evidence_values(nested, path=f"{path}.{key}")
        return
    if isinstance(value, list | tuple):
        for index, nested in enumerate(value):
            yield from _iter_source_evidence_values(nested, path=f"{path}[{index}]")


def _scalar_evidence_text(value: JSONValue) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and math.isfinite(value):
        return repr(value)
    return None


__all__ = [
    "SemanticEvidenceOption",
    "resolve_semantic_evidence_references",
    "semantic_evidence_options",
]
