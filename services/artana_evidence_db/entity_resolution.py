"""Deterministic normalization helpers for entity resolution."""

from __future__ import annotations

import unicodedata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable


def canonicalize_entity_match_text(value: str) -> str:
    """Normalize user-supplied entity text while preserving display casing."""
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.split())


def normalize_entity_match_text(value: str) -> str:
    """Build one deterministic exact-match key for labels, aliases, and IDs."""
    canonical = canonicalize_entity_match_text(value)
    return canonical.casefold()


def normalize_entity_alias_labels(values: Iterable[str]) -> list[str]:
    """Collapse one alias list to unique, canonicalized labels."""
    normalized_labels: list[str] = []
    seen: set[str] = set()
    for raw in values:
        label = canonicalize_entity_match_text(raw)
        if not label:
            continue
        normalized = normalize_entity_match_text(label)
        if normalized in seen:
            continue
        seen.add(normalized)
        normalized_labels.append(label)
    return normalized_labels


__all__ = [
    "canonicalize_entity_match_text",
    "normalize_entity_alias_labels",
    "normalize_entity_match_text",
]
