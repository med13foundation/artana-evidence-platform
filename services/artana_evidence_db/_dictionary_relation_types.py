"""Dictionary-backed canonical relation-type resolution helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from artana_evidence_db.relation_type_support import normalize_relation_type

if TYPE_CHECKING:
    from artana_evidence_db.semantic_ports import DictionaryPort


def canonicalize_dictionary_relation_type(
    dictionary_service: DictionaryPort,
    relation_type: str,
) -> str:
    """Resolve one incoming relation label onto the canonical dictionary ID."""
    normalized_relation_type = normalize_relation_type(relation_type)
    resolved = dictionary_service.resolve_relation_synonym(
        normalized_relation_type,
    )
    if resolved is not None:
        return resolved.id
    return normalized_relation_type


__all__ = ["canonicalize_dictionary_relation_type"]
