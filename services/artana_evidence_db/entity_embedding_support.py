"""Shared helpers for graph-owned entity embedding readiness."""

from __future__ import annotations

import hashlib

_DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
_DEFAULT_EMBEDDING_VERSION = 1


def canonical_entity_embedding_text(
    *,
    entity_type: str,
    display_label: str | None,
) -> str:
    """Build the canonical text used for entity embedding generation."""
    normalized_parts = [
        part.strip()
        for part in (entity_type, display_label or "")
        if isinstance(part, str) and part.strip()
    ]
    return " ".join(normalized_parts)


def canonical_entity_embedding_fingerprint(
    *,
    entity_type: str,
    display_label: str | None,
) -> str:
    """Return a stable content fingerprint for the canonical embedding text."""
    canonical_text = canonical_entity_embedding_text(
        entity_type=entity_type,
        display_label=display_label,
    )
    return hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()


__all__ = [
    "_DEFAULT_EMBEDDING_MODEL",
    "_DEFAULT_EMBEDDING_VERSION",
    "canonical_entity_embedding_fingerprint",
    "canonical_entity_embedding_text",
]
