"""Relation synonym proposal aggregation helpers for extraction policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.application.agents.services._extraction_relation_synonym_proposal import (
    RelationSynonymProposalResult,
    propose_relation_synonym_from_mapping,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from artana_evidence_db.semantic_ports import DictionaryPort


@dataclass(frozen=True)
class RelationSynonymProposalStoreResult:
    """Aggregated relation synonym proposal persistence result."""

    mapping_proposals_count: int = 0
    attempted_count: int = 0
    created_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class _PolicyProposalStoreResult:
    constraint_proposals_created_count: int = 0
    relation_type_mapping_proposals_count: int = 0
    relation_synonym_proposals_attempted_count: int = 0
    relation_synonym_proposals_created_count: int = 0
    relation_synonym_proposals_skipped_count: int = 0
    relation_synonym_proposals_failed_count: int = 0
    errors: tuple[str, ...] = ()


def store_relation_synonym_proposals(
    mappings: Sequence[object],
    *,
    dictionary: DictionaryPort | None,
) -> RelationSynonymProposalStoreResult:
    """Persist pending-review synonyms for policy mapping proposals."""

    results = tuple(
        propose_relation_synonym_from_mapping(mapping, dictionary=dictionary)
        for mapping in mappings
    )
    return RelationSynonymProposalStoreResult(
        mapping_proposals_count=len(mappings),
        attempted_count=sum(1 for result in results if result.attempted),
        created_count=sum(1 for result in results if result.status == "created"),
        skipped_count=sum(1 for result in results if result.status == "skipped"),
        failed_count=sum(1 for result in results if result.status == "failed"),
        errors=tuple(
            _relation_synonym_error(result)
            for result in results
            if result.status == "failed"
        ),
    )


def _relation_synonym_error(result: RelationSynonymProposalResult) -> str:
    observed = result.observed_relation_type or "UNKNOWN"
    mapped = result.mapped_relation_type or "UNKNOWN"
    return f"relation_synonym_proposal_failed:{observed}:{mapped}:{result.reason}"


__all__ = [
    "RelationSynonymProposalStoreResult",
    "_PolicyProposalStoreResult",
    "store_relation_synonym_proposals",
]
