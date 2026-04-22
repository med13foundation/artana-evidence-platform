"""
User repository interface for Artana Resource Library.

Defines the contract for user data persistence operations.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from src.domain.entities.user import User, UserStatus


class UserRepository(ABC):
    """
    Abstract repository interface for user data operations.

    Defines the contract that all user repository implementations must follow.
    """

    @abstractmethod
    async def get_by_id(self, user_id: UUID) -> User | None:
        """
        Get user by ID.

        Args:
            user_id: User's unique identifier

        Returns:
            User entity if found, None otherwise
        """

    @abstractmethod
    async def get_by_email(self, email: str) -> User | None:
        """
        Get user by email address.

        Args:
            email: User's email address

        Returns:
            User entity if found, None otherwise
        """

    @abstractmethod
    async def get_by_username(self, username: str) -> User | None:
        """
        Get user by username.

        Args:
            username: User's username

        Returns:
            User entity if found, None otherwise
        """

    @abstractmethod
    async def create(self, user: User) -> User:
        """
        Create a new user.

        Args:
            user: User entity to create

        Returns:
            Created user entity with any generated fields
        """

    @abstractmethod
    async def update(self, user: User) -> User:
        """
        Update an existing user.

        Args:
            user: User entity with updated data

        Returns:
            Updated user entity
        """

    @abstractmethod
    async def delete(self, user_id: UUID) -> None:
        """
        Delete a user by ID.

        Args:
            user_id: User's unique identifier
        """

    @abstractmethod
    async def exists_by_email(self, email: str) -> bool:
        """
        Check if user exists with given email.

        Args:
            email: Email address to check

        Returns:
            True if user exists, False otherwise
        """

    @abstractmethod
    async def exists_by_username(self, username: str) -> bool:
        """
        Check if user exists with given username.

        Args:
            username: Username to check

        Returns:
            True if user exists, False otherwise
        """

    @abstractmethod
    async def list_users(
        self,
        skip: int = 0,
        limit: int = 100,
        role: str | None = None,
        status: UserStatus | None = None,
    ) -> list[User]:
        """
        List users with optional filtering.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            role: Filter by user role
            status: Filter by user status

        Returns:
            List of user entities
        """

    @abstractmethod
    async def count_users(
        self,
        role: str | None = None,
        status: UserStatus | None = None,
    ) -> int:
        """
        Count users with optional filtering.

        Args:
            role: Filter by user role
            status: Filter by user status

        Returns:
            Number of users matching criteria
        """

    @abstractmethod
    async def count_users_by_status(self, status: UserStatus) -> int:
        """
        Count users by status.

        Args:
            status: User status to count

        Returns:
            Number of users with given status
        """

    @abstractmethod
    async def update_last_login(self, user_id: UUID) -> None:
        """
        Update user's last login timestamp.

        Args:
            user_id: User's unique identifier
        """

    @abstractmethod
    async def increment_login_attempts(self, user_id: UUID) -> int:
        """
        Increment login attempts counter.

        Args:
            user_id: User's unique identifier

        Returns:
            New login attempts count
        """

    @abstractmethod
    async def reset_login_attempts(self, user_id: UUID) -> None:
        """
        Reset login attempts counter.

        Args:
            user_id: User's unique identifier
        """

    @abstractmethod
    async def lock_account(self, user_id: UUID, locked_until: datetime) -> None:
        """
        Lock user account until specified time.

        Args:
            user_id: User's unique identifier
            locked_until: Time until account is locked
        """

    @abstractmethod
    async def unlock_account(self, user_id: UUID) -> None:
        """
        Unlock user account.

        Args:
            user_id: User's unique identifier
        """
