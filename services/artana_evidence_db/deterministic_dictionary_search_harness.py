"""Repository-backed dictionary search harness for deterministic graph governance."""

from __future__ import annotations

from typing import TYPE_CHECKING

from artana_evidence_db.governance_ports import DictionarySearchHarnessPort

if TYPE_CHECKING:
    from artana_evidence_db.kernel_domain_models import DictionarySearchResult
    from artana_evidence_db.kernel_domain_ports import (
        DictionarySearchRepository,
    )


class GraphDeterministicDictionarySearchHarness(DictionarySearchHarnessPort):
    """Run dictionary term search directly against the repository."""

    def __init__(self, *, dictionary_repo: DictionarySearchRepository) -> None:
        self._dictionary = dictionary_repo

    def search(
        self,
        *,
        terms: list[str],
        dimensions: list[str] | None = None,
        domain_context: str | None = None,
        limit: int = 50,
        include_inactive: bool = False,
    ) -> list[DictionarySearchResult]:
        normalized_terms = [
            term.strip() for term in terms if isinstance(term, str) and term.strip()
        ]
        if not normalized_terms:
            return []

        return self._dictionary.search_dictionary(
            terms=normalized_terms,
            dimensions=dimensions,
            domain_context=domain_context,
            limit=limit,
            query_embeddings=None,
            include_inactive=include_inactive,
        )


__all__ = ["GraphDeterministicDictionarySearchHarness"]
