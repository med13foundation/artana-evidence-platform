"""Alias helpers for ontology entity ingestion."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.services.ontology_ingestion import OntologyTerm


def alias_labels_for_term(term: OntologyTerm) -> list[str]:
    """Return normalized, deduplicated synonym labels for one ontology term."""
    aliases: list[str] = []
    seen: set[str] = set()
    for synonym in term.synonyms:
        alias = synonym.strip()
        if not alias or alias in seen:
            continue
        seen.add(alias)
        aliases.append(alias)
    return aliases


def response_indicates_created(result: object) -> bool:
    """Return True when a graph entity upsert response says it created a row."""
    return isinstance(result, dict) and result.get("created") is True


def entity_payload_from_upsert_response(result: object) -> object:
    """Return the entity payload from either wrapped or flat upsert responses."""
    if not isinstance(result, dict):
        return None
    entity_payload = result.get("entity")
    return entity_payload if entity_payload is not None else result


def alias_labels_from_entity_payload(entity_payload: object) -> set[str]:
    """Return normalized aliases included in one graph entity response payload."""
    if not isinstance(entity_payload, dict):
        return set()
    aliases = entity_payload.get("aliases")
    if not isinstance(aliases, list):
        return set()
    return {
        alias.strip() for alias in aliases if isinstance(alias, str) and alias.strip()
    }
