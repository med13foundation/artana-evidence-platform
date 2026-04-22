"""
Domain repository interfaces for Data Discovery.

These interfaces define the contracts for data access operations
related to data discovery sessions, source catalogs, and query testing.
"""

from abc import ABC, abstractmethod
from uuid import UUID

from src.domain.entities.data_discovery_parameters import QueryParameters
from src.domain.entities.data_discovery_session import (
    DataDiscoverySession,
    QueryTestResult,
    SourceCatalogEntry,
)
from src.domain.entities.discovery_preset import DiscoveryPreset
from src.domain.entities.discovery_search_job import DiscoverySearchJob
from src.type_definitions.common import JSONObject


class DataDiscoverySessionRepository(ABC):
    """
    Repository interface for data discovery session operations.

    Defines the contract for managing data discovery sessions in the domain layer.
    """

    @abstractmethod
    def save(self, session: DataDiscoverySession) -> DataDiscoverySession:
        """
        Save a data discovery session.

        Args:
            session: The session to save

        Returns:
            The saved session with any generated IDs
        """

    @abstractmethod
    def find_by_id(self, session_id: UUID) -> DataDiscoverySession | None:
        """
        Find a data discovery session by ID.

        Args:
            session_id: The session ID to search for

        Returns:
            The session if found, None otherwise
        """

    @abstractmethod
    def find_owned_session(
        self,
        session_id: UUID,
        owner_id: UUID,
    ) -> DataDiscoverySession | None:
        """
        Find a session by ID that belongs to the specified owner.

        Args:
            session_id: The session identifier to load
            owner_id: The user who must own the session

        Returns:
            The session if it belongs to the owner, None otherwise
        """

    @abstractmethod
    def find_by_owner(
        self,
        owner_id: UUID,
        *,
        include_inactive: bool = False,
    ) -> list[DataDiscoverySession]:
        """
        Find all data discovery sessions for a specific owner.

        Args:
            owner_id: The owner ID to search for
            include_inactive: Whether to include inactive sessions

        Returns:
            List of sessions owned by the user
        """

    @abstractmethod
    def find_by_space(
        self,
        space_id: UUID,
        *,
        include_inactive: bool = False,
    ) -> list[DataDiscoverySession]:
        """
        Find all data discovery sessions for a specific research space.

        Args:
            space_id: The research space ID

        Returns:
            List of sessions in the space
        """

    @abstractmethod
    def delete(self, session_id: UUID) -> bool:
        """
        Delete a data discovery session.

        Args:
            session_id: The session ID to delete

        Returns:
            True if deleted, False if not found
        """


class SourceCatalogRepository(ABC):
    """
    Repository interface for source catalog operations.

    Defines the contract for managing the data source catalog.
    """

    @abstractmethod
    def save(self, entry: SourceCatalogEntry) -> SourceCatalogEntry:
        """
        Save a source catalog entry.

        Args:
            entry: The catalog entry to save

        Returns:
            The saved entry
        """

    @abstractmethod
    def find_by_id(self, entry_id: str) -> SourceCatalogEntry | None:
        """
        Find a catalog entry by ID.

        Args:
            entry_id: The entry ID to search for

        Returns:
            The entry if found, None otherwise
        """

    @abstractmethod
    def find_all_active(self) -> list[SourceCatalogEntry]:
        """
        Find all active catalog entries.

        Returns:
            List of all active entries
        """

    @abstractmethod
    def find_all(self) -> list[SourceCatalogEntry]:
        """
        Find all catalog entries regardless of status.

        Returns:
            List of entries
        """

    @abstractmethod
    def find_by_category(self, category: str) -> list[SourceCatalogEntry]:
        """
        Find catalog entries by category.

        Args:
            category: The category to filter by

        Returns:
            List of entries in the category
        """

    @abstractmethod
    def search(
        self,
        query: str,
        category: str | None = None,
    ) -> list[SourceCatalogEntry]:
        """
        Search catalog entries by query.

        Args:
            query: Search query (name, description, tags)
            category: Optional category filter

        Returns:
            List of matching entries
        """

    @abstractmethod
    def update_usage_stats(
        self,
        entry_id: str,
        *,
        success: bool,
    ) -> bool:
        """
        Update usage statistics for a catalog entry.

        Args:
            entry_id: The entry ID to update
            success: Whether the usage was successful

        Returns:
            True if updated successfully
        """


class QueryTestResultRepository(ABC):
    """
    Repository interface for query test result operations.

    Defines the contract for managing query test results.
    """

    @abstractmethod
    def save(self, result: QueryTestResult) -> QueryTestResult:
        """
        Save a query test result.

        Args:
            result: The test result to save

        Returns:
            The saved result
        """

    @abstractmethod
    def find_by_session(self, session_id: UUID) -> list[QueryTestResult]:
        """
        Find all test results for a data discovery session.

        Args:
            session_id: The session ID

        Returns:
            List of test results for the session
        """

    @abstractmethod
    def find_by_source(
        self,
        catalog_entry_id: str,
        limit: int = 50,
    ) -> list[QueryTestResult]:
        """
        Find recent test results for a catalog entry.

        Args:
            catalog_entry_id: The catalog entry ID
            limit: Maximum number of results to return

        Returns:
            List of recent test results
        """

    @abstractmethod
    def find_by_id(self, result_id: UUID) -> QueryTestResult | None:
        """
        Find a test result by ID.

        Args:
            result_id: The result ID

        Returns:
            The result if found, None otherwise
        """

    @abstractmethod
    def delete_session_results(self, session_id: UUID) -> int:
        """
        Delete all test results for a session.

        Args:
            session_id: The session ID

        Returns:
            Number of results deleted
        """


class DiscoveryPresetRepository(ABC):
    """Repository interface for discovery preset operations."""

    @abstractmethod
    def create(self, preset: DiscoveryPreset) -> DiscoveryPreset:
        """Persist a new preset."""

    @abstractmethod
    def update(self, preset: DiscoveryPreset) -> DiscoveryPreset:
        """Update an existing preset."""

    @abstractmethod
    def delete(self, preset_id: UUID, owner_id: UUID) -> bool:
        """Delete a preset if owned by the given user."""

    @abstractmethod
    def get_owned_preset(
        self,
        preset_id: UUID,
        owner_id: UUID,
    ) -> DiscoveryPreset | None:
        """Return a preset owned by the specified user."""

    @abstractmethod
    def list_for_owner(self, owner_id: UUID) -> list[DiscoveryPreset]:
        """List presets created by a specific user."""

    @abstractmethod
    def list_for_space(self, space_id: UUID) -> list[DiscoveryPreset]:
        """List presets shared with the specified research space."""


class DiscoverySearchJobRepository(ABC):
    """Repository interface for asynchronous discovery search jobs."""

    @abstractmethod
    def create(self, job: DiscoverySearchJob) -> DiscoverySearchJob:
        """Persist a new search job record."""

    @abstractmethod
    def update(self, job: DiscoverySearchJob) -> DiscoverySearchJob:
        """Update an existing job record."""

    @abstractmethod
    def get(self, job_id: UUID) -> DiscoverySearchJob | None:
        """Retrieve a job by identifier."""

    @abstractmethod
    def list_for_owner(self, owner_id: UUID) -> list[DiscoverySearchJob]:
        """List jobs initiated by the specified owner."""

    @abstractmethod
    def list_for_session(self, session_id: UUID) -> list[DiscoverySearchJob]:
        """List jobs associated with a discovery session."""


class SourceQueryClient(ABC):
    """
    Interface for executing queries against external data sources.

    This abstracts the actual HTTP/API calls to external sources.
    """

    @abstractmethod
    async def execute_query(
        self,
        catalog_entry: SourceCatalogEntry,
        parameters: QueryParameters,
        timeout_seconds: int = 30,
    ) -> JSONObject:
        """
        Execute a query against an external data source.

        Args:
            catalog_entry: The catalog entry describing the source
            parameters: Query parameters to use
            timeout_seconds: Timeout for the query

        Returns:
            Query result data

        Raises:
            QueryExecutionError: If the query fails
        """

    @abstractmethod
    def generate_url(
        self,
        catalog_entry: SourceCatalogEntry,
        parameters: QueryParameters,
    ) -> str | None:
        """
        Generate a URL for external link sources.

        Args:
            catalog_entry: The catalog entry
            parameters: Query parameters

        Returns:
            URL string or None if parameters are invalid
        """

    @abstractmethod
    def validate_parameters(
        self,
        catalog_entry: SourceCatalogEntry,
        parameters: QueryParameters,
    ) -> bool:
        """
        Validate that parameters are suitable for the source.

        Args:
            catalog_entry: The catalog entry
            parameters: Parameters to validate

        Returns:
            True if parameters are valid
        """
