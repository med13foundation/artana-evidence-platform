"""
Session repository interface for Artana Resource Library.

Defines the contract for session data persistence operations.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from src.domain.entities.session import UserSession


class SessionRepository(ABC):
    """
    Abstract repository interface for session data operations.

    Defines the contract that all session repository implementations must follow.
    """

    @abstractmethod
    async def create(self, session: UserSession) -> UserSession:
        """
        Create a new session.

        Args:
            session: Session entity to create

        Returns:
            Created session entity with any generated fields
        """

    @abstractmethod
    async def get_by_id(self, session_id: UUID) -> UserSession | None:
        """
        Get session by ID.

        Args:
            session_id: Session's unique identifier

        Returns:
            Session entity if found, None otherwise
        """

    @abstractmethod
    async def get_by_access_token(self, access_token: str) -> UserSession | None:
        """
        Get session by access token.

        Args:
            access_token: JWT access token

        Returns:
            Session entity if found, None otherwise
        """

    @abstractmethod
    async def get_by_refresh_token(self, refresh_token: str) -> UserSession | None:
        """
        Get session by refresh token.

        Args:
            refresh_token: JWT refresh token

        Returns:
            Session entity if found, None otherwise
        """

    @abstractmethod
    async def get_active_by_refresh_token(
        self,
        refresh_token: str,
    ) -> UserSession | None:
        """
        Get active session by refresh token.

        Args:
            refresh_token: JWT refresh token

        Returns:
            Active session entity if found, None otherwise
        """

    @abstractmethod
    async def update(self, session: UserSession) -> UserSession:
        """
        Update an existing session.

        Args:
            session: Session entity with updated data

        Returns:
            Updated session entity
        """

    @abstractmethod
    async def delete(self, session_id: UUID) -> None:
        """
        Delete a session by ID.

        Args:
            session_id: Session's unique identifier
        """

    @abstractmethod
    async def revoke_session(self, session_id: UUID) -> None:
        """
        Revoke a session (mark as revoked).

        Args:
            session_id: Session's unique identifier
        """

    @abstractmethod
    async def get_user_sessions(
        self,
        user_id: UUID,
        *,
        include_expired: bool = False,
    ) -> list[UserSession]:
        """
        Get all sessions for a user.

        Args:
            user_id: User's unique identifier
            include_expired: Whether to include expired sessions

        Returns:
            List of user's sessions
        """

    @abstractmethod
    async def get_active_sessions(self, user_id: UUID) -> list[UserSession]:
        """
        Get active sessions for a user.

        Args:
            user_id: User's unique identifier

        Returns:
            List of active user sessions
        """

    @abstractmethod
    async def count_active_sessions(self, user_id: UUID) -> int:
        """
        Count active sessions for a user.

        Args:
            user_id: User's unique identifier

        Returns:
            Number of active sessions
        """

    @abstractmethod
    async def revoke_all_user_sessions(self, user_id: UUID) -> int:
        """
        Revoke all sessions for a user.

        Args:
            user_id: User's unique identifier

        Returns:
            Number of sessions revoked
        """

    @abstractmethod
    async def revoke_expired_sessions(self) -> int:
        """
        Revoke all expired sessions.

        Returns:
            Number of sessions revoked
        """

    @abstractmethod
    async def cleanup_expired_sessions(
        self,
        before_date: datetime | None = None,
    ) -> int:
        """
        Clean up old expired sessions.

        Args:
            before_date: Delete sessions expired before this date
                        (default: 30 days ago)

        Returns:
            Number of sessions deleted
        """

    @abstractmethod
    async def get_sessions_by_ip(self, ip_address: str) -> list[UserSession]:
        """
        Get sessions by IP address (for security monitoring).

        Args:
            ip_address: IP address to search for

        Returns:
            List of sessions from the IP address
        """

    @abstractmethod
    async def update_session_activity(self, session_id: UUID) -> None:
        """
        Update session's last activity timestamp.

        Args:
            session_id: Session's unique identifier
        """
