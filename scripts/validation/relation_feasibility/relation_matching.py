"""Relation-key and endpoint matching helpers for feasibility scoring."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from artana_evidence_api.document_extraction_support.entity_grounding.verified_dictionary import (
    relation_match_label_for_label,
)

if TYPE_CHECKING:
    from scripts.validation.relation_feasibility.models import (
        ExtractedRelation,
        GoldRelation,
    )

_RELATION_SYNONYMS = {
    "LINKED_TO": "ASSOCIATED_WITH",
    "LINKS_TO": "ASSOCIATED_WITH",
    "CORRELATED_WITH": "ASSOCIATED_WITH",
    "INTERACTS_WITH": "PHYSICALLY_INTERACTS_WITH",
    "BINDS_TO": "PHYSICALLY_INTERACTS_WITH",
    "UPREGULATES": "ACTIVATES",
    "DOWNREGULATES": "INHIBITS",
}


def normalized_relation_key(
    relation: ExtractedRelation | GoldRelation,
) -> tuple[str, str, str]:
    """Return the normalized triple key used for support matching."""

    return (
        normalize_entity(relation.subject),
        normalize_relation_type(relation.relation_type),
        normalize_entity(relation.object),
    )


def relation_matches_gold(
    *,
    candidate: ExtractedRelation,
    gold_relation: GoldRelation,
) -> bool:
    """Return whether a candidate can be assessed against a gold relation."""

    if normalize_relation_type(candidate.relation_type) != normalize_relation_type(
        gold_relation.relation_type,
    ):
        return False
    return _endpoint_matches_gold(
        candidate_label=candidate.subject,
        candidate_curie=candidate.subject_curie,
        candidate_curie_source=candidate.subject_curie_source,
        gold_label=gold_relation.subject,
        gold_curie=gold_relation.subject_curie,
    ) and _endpoint_matches_gold(
        candidate_label=candidate.object,
        candidate_curie=candidate.object_curie,
        candidate_curie_source=candidate.object_curie_source,
        gold_label=gold_relation.object,
        gold_curie=gold_relation.object_curie,
    )


def normalize_entity(value: str) -> str:
    """Normalize an entity label for exact relation matching."""

    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def normalize_relation_type(value: str) -> str:
    """Normalize a relation type and known relation synonyms."""

    token = re.sub(r"[^A-Z0-9]+", "_", value.strip().upper()).strip("_")
    return _RELATION_SYNONYMS.get(token, token)


def curie_matches(
    *,
    candidate_curie: str | None,
    gold_curie: str | None,
) -> bool:
    """Return whether two CURIE values are equal after prefix normalization."""

    return (
        gold_curie is not None
        and candidate_curie is not None
        and _normalize_curie(candidate_curie) == _normalize_curie(gold_curie)
    )


def _endpoint_matches_gold(
    *,
    candidate_label: str,
    candidate_curie: str | None,
    candidate_curie_source: str,
    gold_label: str,
    gold_curie: str | None,
) -> bool:
    if normalize_entity(candidate_label) == normalize_entity(gold_label):
        return True

    candidate_relation_label = _relation_match_label(candidate_label)
    gold_relation_label = _relation_match_label(gold_label)
    return (
        candidate_curie_source == "verified_linker"
        and curie_matches(candidate_curie=candidate_curie, gold_curie=gold_curie)
        and candidate_relation_label == gold_relation_label
        and candidate_relation_label is not None
    )


def _relation_match_label(label: str) -> str | None:
    canonical_label = relation_match_label_for_label(label)
    if canonical_label is None:
        return None
    return normalize_entity(canonical_label)


def _normalize_curie(value: str) -> str:
    prefix, separator, local = value.strip().partition(":")
    if separator == "":
        return value.strip().upper()
    return f"{prefix.upper()}:{local}"


__all__ = [
    "curie_matches",
    "normalize_entity",
    "normalize_relation_type",
    "normalized_relation_key",
    "relation_matches_gold",
]
