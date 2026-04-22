"""
Base repository interfaces and specifications for domain data access.

Defines the fundamental contracts for repository patterns with proper
separation of concerns and dependency inversion.
"""

import types
from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.type_definitions.common import QueryFilters


@dataclass
class QuerySpecification:
    """Base class for query specifications."""

    filters: QueryFilters
    sort_by: str | None = None
    sort_order: str | None = None
    limit: int | None = None
    offset: int | None = None


class Repository[TEntity, TId, TUpdate](ABC):
    """
    Abstract base repository interface.

    Defines the contract for data access operations without specifying
    the underlying implementation technology.

    Type Parameters:
        TEntity: The entity type
        TId: The entity ID type
        TUpdate: The update type (TypedDict for type-safe updates)
    """

    @abstractmethod
    def get_by_id(self, entity_id: TId) -> TEntity | None:
        """Retrieve an entity by its ID."""

    @abstractmethod
    def find_all(
        self,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[TEntity]:
        """Retrieve all entities with optional pagination."""

    @abstractmethod
    def exists(self, entity_id: TId) -> bool:
        """Check if an entity exists."""

    @abstractmethod
    def count(self) -> int:
        """Count total entities."""

    @abstractmethod
    def create(self, entity: TEntity) -> TEntity:
        """Create a new entity."""

    @abstractmethod
    def update(self, entity_id: TId, updates: TUpdate) -> TEntity:
        """Update an existing entity with type-safe update parameters."""

    @abstractmethod
    def delete(self, entity_id: TId) -> bool:
        """Delete an entity."""

    @abstractmethod
    def find_by_criteria(self, spec: QuerySpecification) -> list[TEntity]:
        """Find entities matching the given specification."""


class UnitOfWork(ABC):
    """
    Unit of Work pattern for managing transactions across repositories.

    Ensures atomic operations across multiple repositories.
    """

    @abstractmethod
    def begin(self) -> None:
        """Begin a transaction."""

    @abstractmethod
    def commit(self) -> None:
        """Commit the transaction."""

    @abstractmethod
    def rollback(self) -> None:
        """Rollback the transaction."""

    @abstractmethod
    def __enter__(self) -> "UnitOfWork":
        """Context manager entry."""

    @abstractmethod
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """Context manager exit."""


__all__ = [
    "QuerySpecification",
    "Repository",
    "UnitOfWork",
]
