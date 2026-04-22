"""
SQLAlchemy implementation of UserRepository for Artana Resource Library.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import and_, delete, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.user import User, UserRole, UserStatus
from src.domain.repositories.user_repository import UserRepository
from src.models.database.user import UserModel

if TYPE_CHECKING:  # pragma: no cover - typing only
    from uuid import UUID

    from sqlalchemy.sql.elements import ColumnElement


SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class SqlAlchemyUserRepository(UserRepository):
    """
    SQLAlchemy implementation of user repository.

    Provides asynchronous database operations for user management using
    SQLAlchemy models mapped to domain entities.
    """

    def __init__(self, session_factory: SessionFactory) -> None:
        """
        Initialize repository with session factory.

        Args:
            session_factory: Async session factory for creating database sessions.
        """
        self._session_factory = session_factory

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[AsyncSession]:
        """Provide an async session context."""
        async with self._session_factory() as session:
            yield session

    @staticmethod
    def _to_domain(model: UserModel | None) -> User | None:
        """Convert a SQLAlchemy model to a domain entity."""
        if model is None:
            return None
        return User.model_validate(
            {
                "id": model.id,
                "email": model.email,
                "username": model.username,
                "full_name": model.full_name,
                "hashed_password": model.hashed_password,
                "role": SqlAlchemyUserRepository._normalize_role(model.role),
                "status": SqlAlchemyUserRepository._normalize_status(model.status),
                "email_verified": model.email_verified,
                "email_verification_token": model.email_verification_token,
                "password_reset_token": model.password_reset_token,
                "password_reset_expires": model.password_reset_expires,
                "last_login": model.last_login,
                "login_attempts": model.login_attempts,
                "locked_until": model.locked_until,
                "created_at": model.created_at,
                "updated_at": model.updated_at,
            },
        )

    @staticmethod
    def _to_domain_list(models: list[UserModel]) -> list[User]:
        """Convert a list of SQLAlchemy models to domain entities."""
        users: list[User] = []
        for user_model in models:
            user = SqlAlchemyUserRepository._to_domain(user_model)
            if user is not None:
                users.append(user)
        return users

    @staticmethod
    def _enum_to_text(raw_value: object) -> str:
        if isinstance(raw_value, Enum):
            return str(raw_value.value)
        return str(raw_value)

    @staticmethod
    def _normalize_role(raw_role: object) -> UserRole:
        return UserRole(
            SqlAlchemyUserRepository._enum_to_text(raw_role).strip().lower(),
        )

    @staticmethod
    def _normalize_status(raw_status: object) -> UserStatus:
        normalized = SqlAlchemyUserRepository._enum_to_text(raw_status).strip().lower()
        if normalized == "deactivated":
            return UserStatus.INACTIVE
        return UserStatus(normalized)

    @staticmethod
    def _status_filter(status: UserStatus) -> ColumnElement[bool]:
        """
        Build a resilient status predicate across enum schema variants.

        Some environments still use legacy enum labels (e.g. DEACTIVATED)
        while the current domain model uses INACTIVE. For INACTIVE we
        intentionally infer it as "not active/suspended/pending" to avoid
        enum-label coupling.
        """
        if status is UserStatus.INACTIVE:
            return UserModel.status.notin_(
                (
                    UserStatus.ACTIVE,
                    UserStatus.SUSPENDED,
                    UserStatus.PENDING_VERIFICATION,
                ),
            )

        return UserModel.status == status

    async def get_by_id(self, user_id: UUID) -> User | None:
        """Get user by ID."""
        async with self._session() as session:
            stmt = select(UserModel).where(UserModel.id == user_id)
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()
            return self._to_domain(model)

    async def get_by_email(self, email: str) -> User | None:
        """Get user by email address."""
        async with self._session() as session:
            stmt = select(UserModel).where(UserModel.email == email)
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()
            return self._to_domain(model)

    async def get_by_username(self, username: str) -> User | None:
        """Get user by username."""
        async with self._session() as session:
            stmt = select(UserModel).where(UserModel.username == username)
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()
            return self._to_domain(model)

    async def create(self, user: User) -> User:
        """Create a new user."""
        async with self._session() as session:
            now = datetime.now(UTC)
            data = user.model_dump(mode="python")
            data.setdefault("created_at", now)
            data.setdefault("updated_at", now)

            db_user = UserModel(**data)
            session.add(db_user)
            await session.commit()
            await session.refresh(db_user)
            return User.model_validate(db_user)

    async def update(self, user: User) -> User:
        """Update an existing user."""
        async with self._session() as session:
            db_user = await session.get(UserModel, user.id)
            if db_user is None:
                message = f"User with id {user.id} not found"
                raise ValueError(message)

            data = user.model_dump(mode="python")
            data.pop("id", None)
            data.pop("created_at", None)
            data["updated_at"] = datetime.now(UTC)

            for field, value in data.items():
                setattr(db_user, field, value)

            await session.commit()
            await session.refresh(db_user)
            return User.model_validate(db_user)

    async def delete(self, user_id: UUID) -> None:
        """Delete a user by ID."""
        async with self._session() as session:
            stmt = delete(UserModel).where(UserModel.id == user_id)
            await session.execute(stmt)
            await session.commit()

    async def exists_by_email(self, email: str) -> bool:
        """Check if user exists with given email."""
        async with self._session() as session:
            stmt = select(func.count()).where(UserModel.email == email)
            result = await session.execute(stmt)
            count = result.scalar_one()
            return int(count) > 0

    async def exists_by_username(self, username: str) -> bool:
        """Check if user exists with given username."""
        async with self._session() as session:
            stmt = select(func.count()).where(UserModel.username == username)
            result = await session.execute(stmt)
            count = result.scalar_one()
            return int(count) > 0

    async def list_users(
        self,
        skip: int = 0,
        limit: int = 100,
        role: str | None = None,
        status: UserStatus | None = None,
    ) -> list[User]:
        """List users with optional filtering."""
        async with self._session() as session:
            stmt = select(UserModel)

            if role is not None:
                role_enum = UserRole(role)
                stmt = stmt.where(UserModel.role == role_enum)
            if status is not None:
                stmt = stmt.where(self._status_filter(status))

            stmt = stmt.order_by(desc(UserModel.created_at)).offset(skip).limit(limit)
            result = await session.execute(stmt)
            models = list(result.scalars().all())
            return self._to_domain_list(models)

    async def count_users(
        self,
        role: str | None = None,
        status: UserStatus | None = None,
    ) -> int:
        """Count users with optional filtering."""
        async with self._session() as session:
            stmt = select(func.count()).select_from(UserModel)

            if role is not None:
                role_enum = UserRole(role)
                stmt = stmt.where(UserModel.role == role_enum)
            if status is not None:
                stmt = stmt.where(self._status_filter(status))

            result = await session.execute(stmt)
            count = result.scalar_one()
            return int(count)

    async def count_users_by_status(self, status: UserStatus) -> int:
        """Count users by status."""
        async with self._session() as session:
            stmt = (
                select(func.count())
                .select_from(UserModel)
                .where(
                    self._status_filter(status),
                )
            )
            result = await session.execute(stmt)
            count = result.scalar_one()
            return int(count)

    async def update_last_login(self, user_id: UUID) -> None:
        """Update user's last login timestamp."""
        async with self._session() as session:
            now = datetime.now(UTC)
            stmt = (
                update(UserModel)
                .where(UserModel.id == user_id)
                .values(last_login=now, updated_at=now)
            )
            await session.execute(stmt)
            await session.commit()

    async def increment_login_attempts(self, user_id: UUID) -> int:
        """Increment login attempts counter."""
        async with self._session() as session:
            stmt = select(UserModel.login_attempts).where(UserModel.id == user_id)
            result = await session.execute(stmt)
            current_attempts = result.scalar_one_or_none()

            if current_attempts is None:
                return 0

            new_attempts = current_attempts + 1
            now = datetime.now(UTC)

            update_stmt = (
                update(UserModel)
                .where(UserModel.id == user_id)
                .values(login_attempts=new_attempts, updated_at=now)
            )
            await session.execute(update_stmt)
            await session.commit()

            return new_attempts

    async def reset_login_attempts(self, user_id: UUID) -> None:
        """Reset login attempts counter."""
        async with self._session() as session:
            now = datetime.now(UTC)
            stmt = (
                update(UserModel)
                .where(UserModel.id == user_id)
                .values(login_attempts=0, locked_until=None, updated_at=now)
            )
            await session.execute(stmt)
            await session.commit()

    async def lock_account(self, user_id: UUID, locked_until: datetime) -> None:
        """Lock user account until specified time."""
        async with self._session() as session:
            stmt = (
                update(UserModel)
                .where(UserModel.id == user_id)
                .values(
                    locked_until=locked_until,
                    status=UserStatus.SUSPENDED,
                    updated_at=datetime.now(UTC),
                )
            )
            await session.execute(stmt)
            await session.commit()

    async def unlock_account(self, user_id: UUID) -> None:
        """Unlock user account."""
        async with self._session() as session:
            now = datetime.now(UTC)
            stmt = (
                update(UserModel)
                .where(UserModel.id == user_id)
                .values(
                    locked_until=None,
                    status=UserStatus.ACTIVE,
                    login_attempts=0,
                    updated_at=now,
                )
            )
            await session.execute(stmt)
            await session.commit()

    async def get_recent_logins(self, limit: int = 10) -> list[User]:
        """Get users with most recent login activity."""
        async with self._session() as session:
            stmt = (
                select(UserModel)
                .where(
                    and_(
                        UserModel.last_login.is_not(None),
                        self._status_filter(UserStatus.ACTIVE),
                    ),
                )
                .order_by(desc(UserModel.last_login))
                .limit(limit)
            )
            result = await session.execute(stmt)
            models = list(result.scalars().all())
            return self._to_domain_list(models)

    async def get_users_pending_verification(self) -> list[User]:
        """Get users pending email verification."""
        async with self._session() as session:
            stmt = (
                select(UserModel)
                .where(
                    and_(
                        self._status_filter(UserStatus.PENDING_VERIFICATION),
                        UserModel.email_verification_token.is_not(None),
                    ),
                )
                .order_by(UserModel.created_at)
            )
            result = await session.execute(stmt)
            models = list(result.scalars().all())
            return self._to_domain_list(models)

    async def get_users_by_role(self, role: UserRole) -> list[User]:
        """Get all users with specific role."""
        async with self._session() as session:
            stmt = select(UserModel).where(UserModel.role == role)
            result = await session.execute(stmt)
            models = list(result.scalars().all())
            return self._to_domain_list(models)
