"""Canonical relation-type lexical normalization helpers."""

from __future__ import annotations


def normalize_relation_type(relation_type: str) -> str:
    """Normalize relation labels before dictionary-backed canonical resolution."""
    normalized = relation_type.strip().upper()
    if not normalized:
        return ""
    return normalized


__all__ = ["normalize_relation_type"]
