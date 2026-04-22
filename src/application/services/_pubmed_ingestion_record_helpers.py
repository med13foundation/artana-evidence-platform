"""Small reusable helpers for PubMed record payloads."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.type_definitions.common import JSONObject


def extract_pubmed_id(record: JSONObject) -> str | None:
    """Return the normalized PubMed identifier when present."""
    for key in ("pmid", "pubmed_id"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int):
            return str(value)
    return None


__all__ = ["extract_pubmed_id"]
