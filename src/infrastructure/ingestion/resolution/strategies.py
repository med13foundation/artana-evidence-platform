"""
Resolution strategies for the ingestion pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from artana_evidence_db.kernel_domain_models import KernelEntity
    from artana_evidence_db.kernel_repositories import KernelEntityRepository

    from src.type_definitions.common import JSONObject


class ResolutionStrategy(Protocol):
    """Protocol for entity resolution strategies."""

    def resolve(
        self,
        identifiers: JSONObject,
        entity_type: str,
        research_space_id: str,
    ) -> KernelEntity | None:
        """Resolve an entity based on identifiers."""
        ...


class StrictMatchStrategy:
    """
    Resolves entities by looking up exact identifier matches.
    """

    def __init__(self, entity_repository: KernelEntityRepository) -> None:
        self.entity_repo = entity_repository

    def resolve(
        self,
        identifiers: JSONObject,
        entity_type: str,
        research_space_id: str,
    ) -> KernelEntity | None:
        # Use the repository's resolve method which handles identifier lookup
        # We assume 'identifiers' dictionary keys correspond to namespaces (e.g. 'mrn', 'hgnc_id')
        # and values are the identifier strings.

        # Cast values to strings as identifiers are stored as strings
        string_identifiers = {k: str(v) for k, v in identifiers.items()}

        return self.entity_repo.resolve(
            research_space_id=research_space_id,
            entity_type=entity_type,
            identifiers=string_identifiers,
        )


class LookupStrategy:
    """
    Placeholder for Lookup strategy (might be same as Strict Match for now).
    """

    def __init__(self, entity_repository: KernelEntityRepository) -> None:
        self.entity_repo = entity_repository

    def resolve(
        self,
        identifiers: JSONObject,
        entity_type: str,
        research_space_id: str,
    ) -> KernelEntity | None:
        # For now, behaves like strict match on supported keys
        return StrictMatchStrategy(self.entity_repo).resolve(
            identifiers,
            entity_type,
            research_space_id,
        )


class FuzzyStrategy:
    """
    Placeholder for Fuzzy implementation.
    """

    def __init__(self, entity_repository: KernelEntityRepository) -> None:
        self.entity_repo = entity_repository
        self._fallback = StrictMatchStrategy(entity_repository)

    def resolve(
        self,
        identifiers: JSONObject,
        entity_type: str,
        research_space_id: str,
    ) -> KernelEntity | None:
        # Deterministic fallback: treat FUZZY as strict identifier matching until
        # we add a proper fuzzy match strategy (e.g. trigram/pgvector).
        return self._fallback.resolve(identifiers, entity_type, research_space_id)
