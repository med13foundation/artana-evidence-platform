"""
Publication repository interface - domain contract for publication data access.

Defines the operations available for publication entities without specifying
the underlying implementation.
"""

from abc import abstractmethod

from src.domain.entities.publication import Publication
from src.domain.repositories.base import Repository
from src.type_definitions.common import PublicationUpdate, QueryFilters


class PublicationRepository(Repository[Publication, int, PublicationUpdate]):
    """
    Domain repository interface for Publication entities.

    Defines all operations available for publication data access, maintaining
    domain purity by not exposing infrastructure details.
    """

    @abstractmethod
    def find_by_pmid(self, pmid: str) -> Publication | None:
        """Find a publication by PubMed ID."""

    @abstractmethod
    def find_by_doi(self, doi: str) -> Publication | None:
        """Find a publication by DOI."""

    @abstractmethod
    def find_by_title(self, title: str, *, fuzzy: bool = False) -> list[Publication]:
        """Find publications by title (exact or fuzzy match)."""

    @abstractmethod
    def find_by_author(self, author_name: str) -> list[Publication]:
        """Find publications by author name."""

    @abstractmethod
    def find_by_year_range(self, start_year: int, end_year: int) -> list[Publication]:
        """Find publications within a year range."""

    @abstractmethod
    def find_by_gene_associations(self, gene_id: int) -> list[Publication]:
        """Find publications associated with a gene."""

    @abstractmethod
    def find_by_variant_associations(self, variant_id: int) -> list[Publication]:
        """Find publications associated with a variant."""

    @abstractmethod
    def search_publications(
        self,
        query: str,
        limit: int = 10,
        filters: QueryFilters | None = None,
    ) -> list[Publication]:
        """Search publications with optional filters."""

    @abstractmethod
    def paginate_publications(
        self,
        page: int,
        per_page: int,
        sort_by: str,
        sort_order: str,
        filters: QueryFilters | None = None,
    ) -> tuple[list[Publication], int]:
        """Retrieve paginated publications with optional filters."""

    @abstractmethod
    def get_publication_statistics(self) -> dict[str, int | float | bool | str | None]:
        """Get statistics about publications in the repository."""

    @abstractmethod
    def find_recent_publications(self, days: int = 30) -> list[Publication]:
        """Find publications from the last N days."""

    @abstractmethod
    def find_med13_relevant(
        self,
        min_relevance: int = 3,
        limit: int | None = None,
    ) -> list[Publication]:
        """Find publications relevant to MED13 research."""

    @abstractmethod
    def update_publication(
        self,
        publication_id: int,
        updates: PublicationUpdate,
    ) -> Publication:
        """Update a publication with type-safe update parameters."""


__all__ = ["PublicationRepository"]
