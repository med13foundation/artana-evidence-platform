"""
Repository interface for User Data Source entities.

Defines the contract for data access operations on user-managed data sources,
providing a clean separation between domain logic and data persistence.
"""

from abc import ABC, abstractmethod
from uuid import UUID

from src.domain.entities.user_data_source import (
    IngestionSchedule,
    QualityMetrics,
    SourceConfiguration,
    SourceStatus,
    SourceType,
    UserDataSource,
)
from src.type_definitions.common import StatisticsResponse


class UserDataSourceRepository(ABC):
    """
    Abstract repository for UserDataSource entities.

    Defines the interface for CRUD operations and specialized queries
    related to user-managed data sources.
    """

    @abstractmethod
    def save(self, source: UserDataSource) -> UserDataSource:
        """
        Save a user data source to the repository.

        Args:
            source: The UserDataSource entity to save

        Returns:
            The saved UserDataSource with any generated fields populated
        """

    @abstractmethod
    def find_by_id(self, source_id: UUID) -> UserDataSource | None:
        """
        Find a user data source by its ID.

        Args:
            source_id: The unique identifier of the source

        Returns:
            The UserDataSource if found, None otherwise
        """

    @abstractmethod
    def find_by_owner(
        self,
        owner_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[UserDataSource]:
        """
        Find all data sources owned by a specific user.

        Args:
            owner_id: The user ID of the owner
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of UserDataSource entities owned by the user
        """

    @abstractmethod
    def find_by_type(
        self,
        source_type: SourceType,
        skip: int = 0,
        limit: int = 50,
    ) -> list[UserDataSource]:
        """
        Find all data sources of a specific type.

        Args:
            source_type: The type of source to search for
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of UserDataSource entities of the specified type
        """

    @abstractmethod
    def find_by_status(
        self,
        status: SourceStatus,
        skip: int = 0,
        limit: int = 50,
    ) -> list[UserDataSource]:
        """
        Find all data sources with a specific status.

        Args:
            status: The status to filter by
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of UserDataSource entities with the specified status
        """

    @abstractmethod
    def find_active_sources(
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> list[UserDataSource]:
        """
        Find all active data sources.

        Args:
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of active UserDataSource entities
        """

    @abstractmethod
    def find_by_tag(
        self,
        tag: str,
        skip: int = 0,
        limit: int = 50,
    ) -> list[UserDataSource]:
        """
        Find data sources that have a specific tag.

        Args:
            tag: The tag to search for
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of UserDataSource entities with the specified tag
        """

    @abstractmethod
    def search_by_name(
        self,
        query: str,
        owner_id: UUID | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[UserDataSource]:
        """
        Search data sources by name using fuzzy matching.

        Args:
            query: The search query string
            owner_id: Optional owner filter
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of UserDataSource entities matching the search
        """

    @abstractmethod
    def update_status(
        self,
        source_id: UUID,
        status: SourceStatus,
    ) -> UserDataSource | None:
        """
        Update the status of a data source.

        Args:
            source_id: The ID of the source to update
            status: The new status

        Returns:
            The updated UserDataSource if found, None otherwise
        """

    @abstractmethod
    def update_quality_metrics(
        self,
        source_id: UUID,
        metrics: QualityMetrics,
    ) -> UserDataSource | None:
        """
        Update the quality metrics of a data source.

        Args:
            source_id: The ID of the source to update
            metrics: The new quality metrics

        Returns:
            The updated UserDataSource if found, None otherwise
        """

    @abstractmethod
    def update_configuration(
        self,
        source_id: UUID,
        config: SourceConfiguration,
    ) -> UserDataSource | None:
        """
        Update the configuration of a data source.

        Args:
            source_id: The ID of the source to update
            config: The new configuration

        Returns:
            The updated UserDataSource if found, None otherwise
        """

    @abstractmethod
    def update_ingestion_schedule(
        self,
        source_id: UUID,
        schedule: IngestionSchedule,
    ) -> UserDataSource | None:
        """
        Update the ingestion schedule of a data source.

        Args:
            source_id: The ID of the source to update
            schedule: The new ingestion schedule

        Returns:
            The updated UserDataSource if found, None otherwise
        """

    @abstractmethod
    def record_ingestion(self, source_id: UUID) -> UserDataSource | None:
        """
        Record that ingestion has occurred for a data source.

        Args:
            source_id: The ID of the source

        Returns:
            The updated UserDataSource if found, None otherwise
        """

    @abstractmethod
    def delete(self, source_id: UUID) -> bool:
        """
        Delete a data source from the repository.

        Args:
            source_id: The ID of the source to delete

        Returns:
            True if deleted, False if not found
        """

    @abstractmethod
    def count_by_owner(self, owner_id: UUID) -> int:
        """
        Count the number of data sources owned by a user.

        Args:
            owner_id: The user ID

        Returns:
            The count of sources owned by the user
        """

    @abstractmethod
    def count_by_status(self, status: SourceStatus) -> int:
        """
        Count the number of data sources with a specific status.

        Args:
            status: The status to count

        Returns:
            The count of sources with the specified status
        """

    @abstractmethod
    def count_by_type(self, source_type: SourceType) -> int:
        """
        Count the number of data sources of a specific type.

        Args:
            source_type: The type to count

        Returns:
            The count of sources of the specified type
        """

    @abstractmethod
    def exists(self, source_id: UUID) -> bool:
        """
        Check if a data source exists.

        Args:
            source_id: The ID to check

        Returns:
            True if exists, False otherwise
        """

    @abstractmethod
    def get_statistics(self) -> StatisticsResponse:
        """
        Get overall statistics about data sources.

        Returns:
            Dictionary with various statistics
        """
