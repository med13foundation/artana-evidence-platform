"""Deterministic source-document entity extraction helpers."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from artana_evidence_api.types.common import JSONObject


@dataclass(frozen=True)
class RecognizedEntityCandidate:
    """One deterministic entity mention recognized in source-document text."""

    label: str
    entity_type: str
    normalized_label: str
    evidence_text: str


_GENE_SYMBOL_RE = re.compile(r"\b[A-Z][A-Z0-9-]{1,10}\b")
_DISEASE_RE = re.compile(
    r"\b[A-Z][A-Za-z0-9 -]{2,80}\s(?:syndrome|disease|disorder|cancer)\b",
)
_COMPLEX_RE = re.compile(
    r"\b[A-Z0-9][A-Za-z0-9-]*(?:\s+[A-Za-z0-9-]+){0,3}\s+"
    r"(?:complex|module)\b",
    flags=re.IGNORECASE,
)
_GENE_SYMBOL_STOPWORDS = frozenset(
    {
        "AND",
        "API",
        "DNA",
        "FIG",
        "HTML",
        "HTTP",
        "JSON",
        "PDF",
        "RNA",
        "THE",
        "URL",
        "XML",
    },
)
_MIN_GENE_SYMBOL_LENGTH = 2
_MAX_GENE_SYMBOL_LENGTH = 12
_MAX_ENTITY_CANDIDATES = 12


def source_document_text(metadata: JSONObject) -> str:
    """Build deterministic extraction text from source-document metadata."""
    raw_record = metadata.get("raw_record")
    parts: list[str] = []
    if isinstance(raw_record, Mapping):
        for key in ("title", "abstract", "text", "full_text", "summary"):
            value = raw_record.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
    for key in ("title", "text", "full_text", "abstract"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return "\n".join(parts)


def extract_entity_candidates(text: str) -> list[RecognizedEntityCandidate]:
    """Extract conservative deterministic entity candidates from document text."""
    normalized_text = text.strip()
    if not normalized_text:
        return []
    candidates: list[RecognizedEntityCandidate] = []
    seen: set[tuple[str, str]] = set()
    for match in _GENE_SYMBOL_RE.finditer(normalized_text):
        label = match.group(0).strip()
        if _is_likely_gene_symbol(label):
            _append_candidate(
                candidates=candidates,
                seen=seen,
                label=label,
                entity_type="GENE",
                text=normalized_text,
                start=match.start(),
                end=match.end(),
            )
    for match in _COMPLEX_RE.finditer(normalized_text):
        label = _normalize_label(match.group(0))
        if label:
            _append_candidate(
                candidates=candidates,
                seen=seen,
                label=label,
                entity_type="PROTEIN_COMPLEX",
                text=normalized_text,
                start=match.start(),
                end=match.end(),
            )
    for match in _DISEASE_RE.finditer(normalized_text):
        label = _normalize_label(match.group(0))
        if label:
            _append_candidate(
                candidates=candidates,
                seen=seen,
                label=label,
                entity_type="DISEASE",
                text=normalized_text,
                start=match.start(),
                end=match.end(),
            )
    return candidates[:_MAX_ENTITY_CANDIDATES]


def _append_candidate(
    *,
    candidates: list[RecognizedEntityCandidate],
    seen: set[tuple[str, str]],
    label: str,
    entity_type: str,
    text: str,
    start: int,
    end: int,
) -> None:
    normalized_label = _normalize_entity_key(label)
    key = (entity_type, normalized_label)
    if key in seen:
        return
    seen.add(key)
    candidates.append(
        RecognizedEntityCandidate(
            label=label,
            entity_type=entity_type,
            normalized_label=normalized_label,
            evidence_text=_evidence_window(text=text, start=start, end=end),
        ),
    )


def _is_likely_gene_symbol(label: str) -> bool:
    if label in _GENE_SYMBOL_STOPWORDS:
        return False
    if (
        len(label) < _MIN_GENE_SYMBOL_LENGTH
        or len(label) > _MAX_GENE_SYMBOL_LENGTH
    ):
        return False
    return any(char.isdigit() for char in label) or "-" in label


def _normalize_label(label: str) -> str:
    return " ".join(label.strip(".,;:()[]{}").split())


def _normalize_entity_key(label: str) -> str:
    return re.sub(r"\s+", " ", label.strip().casefold())


def _evidence_window(*, text: str, start: int, end: int) -> str:
    window_start = max(0, start - 160)
    window_end = min(len(text), end + 220)
    snippet = " ".join(text[window_start:window_end].split())
    return snippet[:500]


__all__ = [
    "RecognizedEntityCandidate",
    "extract_entity_candidates",
    "source_document_text",
]
