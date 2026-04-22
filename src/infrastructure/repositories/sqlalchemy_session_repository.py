"""
SQLAlchemy implementation of SessionRepository for Artana Resource Library.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import TYPE_CHECKING

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.session import SessionStatus, UserSession
from src.domain.repositories.session_repository import SessionRepository
from src.models.database.session import SessionModel

if TYPE_CHECKING:  # pragma: no cover - typing only
    from uuid import UUID

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class SqlAlchemySessionRepository(SessionRepository):
    """
    SQLAlchemy implementation of session repository.

    Converts between SQLAlchemy models and domain entities while providing
    asynchronous persistence operations for session management.
    """

    @staticmethod
    def _hash_token(token: str | None) -> str | None:
        """Hash tokens before persisting to the database."""
        if token is None:
            return None
        return sha256(token.encode()).hexdigest()

    def __init__(self, session_factory: SessionFactory) -> None:
        """
        Initialize repository with session factory.

        Args:
            session_factory: Async session factory used to create DB sessions.
        """
        self._session_factory = session_factory

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[AsyncSession]:
        """Provide an async session context."""
        async with self._session_factory() as session:
            yield session

    @staticmethod
    def _to_domain(model: SessionModel | None) -> UserSession | None:
        """Convert a SQLAlchemy model to a domain entity."""
        if model is None:
            return None
        return UserSession.model_validate(model)

    @staticmethod
    def _to_domain_list(models: list[SessionModel]) -> list[UserSession]:
        """Convert a list of SQLAlchemy models to domain entities."""
        return [UserSession.model_validate(model) for model in models]

    @staticmethod
    def _rowcount(result: object) -> int:
        """Safely extract rowcount from SQLAlchemy result objects."""
        count = getattr(result, "rowcount", None)
        return int(count) if isinstance(count, int) else 0

    async def create(self, session_entity: UserSession) -> UserSession:
        """Create a new session."""
        async with self._session() as session:
            now = datetime.now(UTC)
            data = session_entity.model_dump(mode="python")
            data.setdefault("created_at", now)
            data.setdefault("last_activity", now)
            data["session_token"] = self._hash_token(data.get("session_token"))
            data["refresh_token"] = self._hash_token(data.get("refresh_token"))

            db_session = SessionModel(**data)
            session.add(db_session)
            await session.commit()
            await session.refresh(db_session)
            return UserSession.model_validate(db_session)

    async def get_by_id(self, session_id: UUID) -> UserSession | None:
        """Get session by ID."""
        async with self._session() as session:
            stmt = select(SessionModel).where(SessionModel.id == session_id)
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()
            return self._to_domain(model)

    async def get_by_access_token(self, access_token: str) -> UserSession | None:
        """Get session by access token."""
        async with self._session() as session:
            now = datetime.now(UTC)
            stmt = (
                select(SessionModel)
                .where(
                    and_(
                        SessionModel.session_token == self._hash_token(access_token),
                        SessionModel.status == SessionStatus.ACTIVE,
                        SessionModel.expires_at > now,
                    ),
                )
                .order_by(SessionModel.created_at.desc(), SessionModel.id.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            model = result.scalars().first()
            return self._to_domain(model)

    async def get_by_refresh_token(self, refresh_token: str) -> UserSession | None:
        """Get session by refresh token."""
        async with self._session() as session:
            stmt = (
                select(SessionModel)
                .where(
                    SessionModel.refresh_token == self._hash_token(refresh_token),
                )
                .order_by(SessionModel.created_at.desc(), SessionModel.id.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            model = result.scalars().first()
            return self._to_domain(model)

    async def get_active_by_refresh_token(
        self,
        refresh_token: str,
    ) -> UserSession | None:
        """Get active session by refresh token."""
        async with self._session() as session:
            now = datetime.now(UTC)
            stmt = (
                select(SessionModel)
                .where(
                    and_(
                        SessionModel.refresh_token == self._hash_token(refresh_token),
                        SessionModel.status == SessionStatus.ACTIVE,
                        SessionModel.refresh_expires_at > now,
                    ),
                )
                .order_by(SessionModel.created_at.desc(), SessionModel.id.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            model = result.scalars().first()
            return self._to_domain(model)

    async def update(self, session_entity: UserSession) -> UserSession:
        """Update an existing session."""
        async with self._session() as session:
            db_session = await session.get(SessionModel, session_entity.id)
            if db_session is None:
                message = f"Session with id {session_entity.id} not found"
                raise ValueError(message)

            data = session_entity.model_dump(mode="python")
            data.pop("id", None)
            data.pop("created_at", None)
            data.setdefault("last_activity", datetime.now(UTC))
            if "session_token" in data:
                data["session_token"] = self._hash_token(data["session_token"])
            if "refresh_token" in data:
                data["refresh_token"] = self._hash_token(data["refresh_token"])

            for field, value in data.items():
                setattr(db_session, field, value)

            await session.commit()
            await session.refresh(db_session)
            return UserSession.model_validate(db_session)

    async def delete(self, session_id: UUID) -> None:
        """Delete a session by ID."""
        async with self._session() as session:
            stmt = delete(SessionModel).where(SessionModel.id == session_id)
            await session.execute(stmt)
            await session.commit()

    async def revoke_session(self, session_id: UUID) -> None:
        """Revoke a session (mark as revoked)."""
        async with self._session() as session:
            now = datetime.now(UTC)
            stmt = (
                update(SessionModel)
                .where(SessionModel.id == session_id)
                .values(status=SessionStatus.REVOKED, last_activity=now)
            )
            await session.execute(stmt)
            await session.commit()

    async def get_user_sessions(
        self,
        user_id: UUID,
        include_expired: bool = False,  # noqa: FBT001, FBT002
    ) -> list[UserSession]:
        """Get all sessions for a user."""
        async with self._session() as session:
            stmt = select(SessionModel).where(SessionModel.user_id == user_id)

            if not include_expired:
                now = datetime.now(UTC)
                stmt = stmt.where(
                    and_(
                        SessionModel.status == SessionStatus.ACTIVE,
                        SessionModel.expires_at > now,
                    ),
                )

            stmt = stmt.order_by(SessionModel.created_at.desc())
            result = await session.execute(stmt)
            models = list(result.scalars().all())
            return self._to_domain_list(models)

    async def get_active_sessions(self, user_id: UUID) -> list[UserSession]:
        """Get active sessions for a user."""
        async with self._session() as session:
            now = datetime.now(UTC)
            stmt = (
                select(SessionModel)
                .where(
                    and_(
                        SessionModel.user_id == user_id,
                        SessionModel.status == SessionStatus.ACTIVE,
                        SessionModel.expires_at > now,
                    ),
                )
                .order_by(SessionModel.last_activity.desc())
            )
            result = await session.execute(stmt)
            models = list(result.scalars().all())
            return self._to_domain_list(models)

    async def count_active_sessions(self, user_id: UUID) -> int:
        """Count active sessions for a user."""
        async with self._session() as session:
            now = datetime.now(UTC)
            stmt = select(func.count(SessionModel.id)).where(
                and_(
                    SessionModel.user_id == user_id,
                    SessionModel.status == SessionStatus.ACTIVE,
                    SessionModel.expires_at > now,
                ),
            )
            result = await session.execute(stmt)
            count = result.scalar_one()
            return int(count)

    async def revoke_all_user_sessions(self, user_id: UUID) -> int:
        """Revoke all sessions for a user."""
        async with self._session() as session:
            now = datetime.now(UTC)
            stmt = (
                update(SessionModel)
                .where(
                    and_(
                        SessionModel.user_id == user_id,
                        SessionModel.status == SessionStatus.ACTIVE,
                    ),
                )
                .values(status=SessionStatus.REVOKED, last_activity=now)
            )
            result = await session.execute(stmt)
            await session.commit()
            return self._rowcount(result)

    async def revoke_expired_sessions(self) -> int:
        """Revoke all expired sessions."""
        async with self._session() as session:
            now = datetime.now(UTC)
            stmt = (
                update(SessionModel)
                .where(
                    and_(
                        SessionModel.status == SessionStatus.ACTIVE,
                        SessionModel.expires_at <= now,
                    ),
                )
                .values(status=SessionStatus.EXPIRED, last_activity=now)
            )
            result = await session.execute(stmt)
            await session.commit()
            return self._rowcount(result)

    async def cleanup_expired_sessions(
        self,
        before_date: datetime | None = None,
    ) -> int:
        """Clean up old expired sessions."""
        if before_date is None:
            before_date = datetime.now(UTC) - timedelta(days=30)

        async with self._session() as session:
            stmt = delete(SessionModel).where(
                and_(
                    or_(
                        SessionModel.status == SessionStatus.EXPIRED,
                        SessionModel.status == SessionStatus.REVOKED,
                    ),
                    SessionModel.created_at < before_date,
                ),
            )
            result = await session.execute(stmt)
            await session.commit()
            return self._rowcount(result)

    async def get_sessions_by_ip(self, ip_address: str) -> list[UserSession]:
        """Get sessions by IP address (for security monitoring)."""
        async with self._session() as session:
            stmt = (
                select(SessionModel)
                .where(SessionModel.ip_address == ip_address)
                .order_by(SessionModel.created_at.desc())
                .limit(100)
            )
            result = await session.execute(stmt)
            models = list(result.scalars().all())
            return self._to_domain_list(models)

    async def update_session_activity(self, session_id: UUID) -> None:
        """Update session's last activity timestamp."""
        async with self._session() as session:
            now = datetime.now(UTC)
            stmt = (
                update(SessionModel)
                .where(SessionModel.id == session_id)
                .values(last_activity=now)
            )
            await session.execute(stmt)
            await session.commit()

    async def get_recent_sessions(self, limit: int = 50) -> list[UserSession]:
        """Get most recently active sessions."""
        async with self._session() as session:
            stmt = (
                select(SessionModel)
                .where(SessionModel.status == SessionStatus.ACTIVE)
                .order_by(SessionModel.last_activity.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            models = list(result.scalars().all())
            return self._to_domain_list(models)

    async def get_sessions_expiring_soon(
        self,
        within_minutes: int = 60,
    ) -> list[UserSession]:
        """Get sessions expiring within specified time."""
        now = datetime.now(UTC)
        expiration_threshold = now + timedelta(minutes=within_minutes)

        async with self._session() as session:
            stmt = (
                select(SessionModel)
                .where(
                    and_(
                        SessionModel.status == SessionStatus.ACTIVE,
                        SessionModel.expires_at <= expiration_threshold,
                        SessionModel.expires_at > now,
                    ),
                )
                .order_by(SessionModel.expires_at.asc())
            )
            result = await session.execute(stmt)
            models = list(result.scalars().all())
            return self._to_domain_list(models)
