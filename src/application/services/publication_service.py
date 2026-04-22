"""
Publication application service orchestration layer.

Coordinates domain services and repositories to implement publication management
use cases while preserving strong typing.
"""

from src.domain.entities.publication import Publication, PublicationType
from src.domain.repositories.publication_repository import PublicationRepository
from src.domain.value_objects.identifiers import PublicationIdentifier
from src.type_definitions.common import (
    PublicationUpdate,
    QueryFilters,
    clone_query_filters,
)


class PublicationApplicationService:
    """
    Application service for publication management use cases.

    Orchestrates domain services and repositories to implement
    publication-related business operations with proper dependency injection.
    """

    def __init__(
        self,
        publication_repository: PublicationRepository,
    ):
        """
        Initialize the publication application service.

        Args:
            publication_repository: Domain repository for publications
        """
        self._publication_repository = publication_repository

    def create_publication(  # noqa: PLR0913 - explicit domain fields
        self,
        title: str,
        authors: list[str],
        publication_year: int,
        journal: str,
        *,
        doi: str | None = None,
        pmid: str | None = None,
        pmc_id: str | None = None,
        abstract: str | None = None,
        publication_type: str = PublicationType.JOURNAL_ARTICLE,
        keywords: list[str] | None = None,
        citation_count: int = 0,
        impact_factor: float | None = None,
        relevance_score: int | None = None,
        open_access: bool = False,
    ) -> Publication:
        """
        Create a new publication.

        Args:
            title: Publication title
            authors: List of authors
            publication_year: Year of publication
            journal: Journal name
            doi: DOI identifier
            pmid: PubMed ID
            abstract: Publication abstract
            publication_type: Type of publication

        Returns:
            Created Publication entity
        """
        identifier = PublicationIdentifier(
            pubmed_id=pmid,
            pmc_id=pmc_id,
            doi=doi,
        )

        publication_entity = Publication(
            identifier=identifier,
            title=title,
            authors=tuple(authors),
            journal=journal,
            publication_year=publication_year,
            publication_type=PublicationType.validate(publication_type),
            abstract=abstract,
            keywords=tuple(keywords) if keywords else (),
            citation_count=citation_count,
            impact_factor=impact_factor,
            relevance_score=relevance_score,
            open_access=open_access,
        )

        return self._publication_repository.create(publication_entity)

    def get_publication_by_pmid(self, pmid: str) -> Publication | None:
        """Find a publication by PubMed ID."""
        return self._publication_repository.find_by_pmid(pmid)

    def get_publication_by_doi(self, doi: str) -> Publication | None:
        """Find a publication by DOI."""
        return self._publication_repository.find_by_doi(doi)

    def search_publications_by_title(
        self,
        title: str,
        *,
        fuzzy: bool = False,
    ) -> list[Publication]:
        """Find publications by title."""
        return self._publication_repository.find_by_title(title, fuzzy=fuzzy)

    def search_publications_by_author(self, author_name: str) -> list[Publication]:
        """Find publications by author name."""
        return self._publication_repository.find_by_author(author_name)

    def find_med13_relevant_publications(
        self,
        min_relevance: int = 3,
        limit: int | None = None,
    ) -> list[Publication]:
        """Find publications marked as relevant to MED13 research."""
        return self._publication_repository.find_med13_relevant(
            min_relevance,
            limit,
        )

    def get_publications_by_year_range(
        self,
        start_year: int,
        end_year: int,
    ) -> list[Publication]:
        """Find publications within a year range."""
        return self._publication_repository.find_by_year_range(start_year, end_year)

    def search_publications(
        self,
        query: str,
        limit: int = 10,
        filters: QueryFilters | None = None,
    ) -> list[Publication]:
        """Search publications with optional filters."""
        normalized_filters = self._normalize_filters(filters)
        return self._publication_repository.search_publications(
            query,
            limit,
            normalized_filters,
        )

    def list_publications(
        self,
        page: int,
        per_page: int,
        sort_by: str,
        sort_order: str,
        filters: QueryFilters | None = None,
    ) -> tuple[list[Publication], int]:
        """Retrieve paginated publications with optional filters."""
        normalized_filters = self._normalize_filters(filters)
        return self._publication_repository.paginate_publications(
            page,
            per_page,
            sort_by,
            sort_order,
            normalized_filters,
        )

    def update_publication(
        self,
        publication_id: int,
        updates: PublicationUpdate,
    ) -> Publication:
        """Update publication fields."""
        if not updates:
            msg = "No publication updates provided"
            raise ValueError(msg)
        return self._publication_repository.update(publication_id, updates)

    def get_publication_statistics(self) -> dict[str, int | float | bool | str | None]:
        """Get statistics about publications in the repository."""
        return self._publication_repository.get_publication_statistics()

    def find_recent_publications(self, days: int = 30) -> list[Publication]:
        """Find publications from the last N days."""
        return self._publication_repository.find_recent_publications(days)

    def validate_publication_exists(self, publication_id: int) -> bool:
        """
        Validate that a publication exists.

        Args:
            publication_id: Publication ID to validate

        Returns:
            True if publication exists, False otherwise
        """
        return self._publication_repository.exists(publication_id)

    @staticmethod
    def _normalize_filters(
        filters: QueryFilters | None,
    ) -> QueryFilters | None:
        return clone_query_filters(filters)


__all__ = ["PublicationApplicationService"]
