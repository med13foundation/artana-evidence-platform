"""
UNIFIED Dependency injection container for Artana Resource Library.

Provides centralized dependency management for all application services.
Combines Clean Architecture (auth system) with legacy patterns during transition.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.application import services as app_services
from src.database.engine_config import build_engine_kwargs
from src.infrastructure import observability, storage
from src.infrastructure.dependency_injection.db_utils import (
    SessionLocal,
    resolve_async_database_url,
)
from src.infrastructure.llm.state.shared_postgres_store import (
    get_shared_artana_postgres_store,
)
from src.infrastructure.repositories import (
    SqlAlchemySessionRepository,
    SqlAlchemySystemStatusRepository,
    SqlAlchemyUserRepository,
)
from src.infrastructure.security import JWTProvider, PasswordHasher
from src.infrastructure.security.runtime_env import (
    AUTH_JWT_SECRET_ENV,
    resolve_auth_jwt_secret,
    using_fallback_auth_jwt_secret,
)

from .service_factories import ApplicationServiceFactoryMixin

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from artana.store import PostgresStore

# AsyncSession, async_sessionmaker, and create_async_engine are imported above

logger = logging.getLogger(__name__)
DEFAULT_DEV_JWT_SECRET = resolve_auth_jwt_secret()


class DependencyContainer(ApplicationServiceFactoryMixin):
    """
    UNIFIED Dependency injection container for Artana Resource Library.

    Combines Clean Architecture (async auth system) with legacy sync patterns.
    Provides centralized configuration and lifecycle management for all dependencies.
    """

    def __init__(
        self,
        database_url: str | None = None,
        jwt_secret_key: str | None = None,
        jwt_algorithm: str = "HS256",
    ):
        resolved_db_url = database_url or resolve_async_database_url()
        self.database_url = resolved_db_url
        resolved_secret = jwt_secret_key or DEFAULT_DEV_JWT_SECRET
        self.jwt_secret_key = resolved_secret
        self.jwt_algorithm = jwt_algorithm
        if jwt_secret_key is None and using_fallback_auth_jwt_secret():
            logger.warning(
                "%s is not set. Using fallback development JWT secret; set %s "
                "for stable explicit config.",
                AUTH_JWT_SECRET_ENV,
                AUTH_JWT_SECRET_ENV,
            )

        # Initialize ASYNC database engine (for Clean Architecture - auth)
        engine_kwargs: dict[str, object] = {
            "echo": False,  # Set to True for debugging
            **build_engine_kwargs(resolved_db_url),
        }

        self.engine = create_async_engine(
            resolved_db_url,
            **engine_kwargs,
        )

        # Create async session factory
        self.async_session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        # Initialize security components (Clean Architecture)
        self.password_hasher: PasswordHasher = PasswordHasher()
        self.jwt_provider: JWTProvider = JWTProvider(
            secret_key=resolved_secret,
            algorithm=jwt_algorithm,
        )

        # Initialize Clean Architecture repositories (lazy-loaded, async)
        self._user_repository: SqlAlchemyUserRepository | None = None
        self._session_repository: SqlAlchemySessionRepository | None = None

        # Initialize Clean Architecture services (lazy-loaded, async)
        self._authentication_service: app_services.AuthenticationService | None = None
        self._authentication_service_loop: asyncio.AbstractEventLoop | None = None
        self._authorization_service: app_services.AuthorizationService | None = None
        self._authorization_service_loop: asyncio.AbstractEventLoop | None = None
        self._user_management_service: app_services.UserManagementService | None = None
        self._user_management_service_loop: asyncio.AbstractEventLoop | None = None

        self._storage_plugin_registry = storage.initialize_storage_plugins()
        self._storage_metrics_recorder = (
            observability.logging_metrics_recorder.LoggingStorageMetricsRecorder()
        )
        self._system_status_repository: SqlAlchemySystemStatusRepository | None = None
        self._system_status_service: app_services.SystemStatusService | None = None
        self._entity_recognition_agent = None
        self._extraction_agent = None
        self._mapping_judge_agent = None
        self._graph_connection_agent = None
        self._query_agent = None

    def get_artana_store(self) -> PostgresStore:
        """Return the shared process-local Artana PostgresStore."""
        return get_shared_artana_postgres_store()

    def get_user_repository(self) -> SqlAlchemyUserRepository:
        if self._user_repository is None:
            self._user_repository = SqlAlchemyUserRepository(self.async_session_factory)
        return self._user_repository

    def get_session_repository(self) -> SqlAlchemySessionRepository:
        if self._session_repository is None:
            self._session_repository = SqlAlchemySessionRepository(
                self.async_session_factory,
            )
        return self._session_repository

    def get_system_status_repository(self) -> SqlAlchemySystemStatusRepository:
        if self._system_status_repository is None:
            self._system_status_repository = SqlAlchemySystemStatusRepository(
                SessionLocal,
            )
        return self._system_status_repository

    def get_system_status_service(self) -> app_services.SystemStatusService:
        if self._system_status_service is None:
            repository = self.get_system_status_repository()
            session_revoker = app_services.SessionRevocationContext(SessionLocal)
            self._system_status_service = app_services.SystemStatusService(
                repository=repository,
                session_revoker=session_revoker,
            )
        return self._system_status_service

    async def get_authentication_service(self) -> app_services.AuthenticationService:
        current_loop = asyncio.get_running_loop()
        if (
            self._authentication_service is None
            or self._authentication_service_loop is not current_loop
        ):
            user_repository = self.get_user_repository()
            session_repository = self.get_session_repository()
            self._authentication_service = app_services.AuthenticationService(
                user_repository=user_repository,
                session_repository=session_repository,
                jwt_provider=self.jwt_provider,
                password_hasher=self.password_hasher,
            )
            self._authentication_service_loop = current_loop
        return self._authentication_service

    async def get_authorization_service(self) -> app_services.AuthorizationService:
        current_loop = asyncio.get_running_loop()
        if (
            self._authorization_service is None
            or self._authorization_service_loop is not current_loop
        ):
            user_repository = self.get_user_repository()
            self._authorization_service = app_services.AuthorizationService(
                user_repository=user_repository,
            )
            self._authorization_service_loop = current_loop
        return self._authorization_service

    async def get_user_management_service(self) -> app_services.UserManagementService:
        current_loop = asyncio.get_running_loop()
        if (
            self._user_management_service is None
            or self._user_management_service_loop is not current_loop
        ):
            user_repository = self.get_user_repository()
            self._user_management_service = app_services.UserManagementService(
                user_repository=user_repository,
                password_hasher=self.password_hasher,
            )
            self._user_management_service_loop = current_loop
        return self._user_management_service

    # LEGACY SYSTEM METHODS (Sync SQLAlchemy for backward compatibility)

    # LEGACY APPLICATION SERVICES

    def create_unified_search_service(
        self,
        session: sa.orm.Session,
    ) -> app_services.UnifiedSearchService:
        """Backward-compatible alias for the search service factory."""

        return self.create_search_service(session)

    async def get_db_session(self) -> AsyncGenerator[AsyncSession]:
        async with self.async_session_factory() as session:
            try:
                yield session
            finally:
                await session.close()

    @asynccontextmanager
    async def lifespan_context(self) -> AsyncGenerator[None]:
        # Startup
        try:
            yield
        finally:
            # Shutdown
            await self.engine.dispose()

    async def health_check(self) -> dict[str, bool]:
        health_status_keys = ("database", "jwt_provider", "password_hasher", "services")
        health_status: dict[str, bool] = dict.fromkeys(health_status_keys, False)

        try:
            # Test database connection
            async with self.async_session_factory() as session:
                await session.execute(sa.text("SELECT 1"))
                health_status["database"] = True
        except (sa.exc.SQLAlchemyError, RuntimeError) as exc:
            logger.warning("Database health check failed: %s", exc)

        # Test JWT provider
        try:
            test_token = self.jwt_provider.create_access_token(uuid4(), "viewer")
            decoded = self.jwt_provider.decode_token(test_token)
            health_status["jwt_provider"] = decoded is not None
        except ValueError as exc:
            logger.warning("JWT provider health check failed: %s", exc)

        # Test password hasher
        try:
            test_hash = self.password_hasher.hash_password("test-password")
            is_valid = self.password_hasher.verify_password("test-password", test_hash)
            health_status["password_hasher"] = is_valid
        except ValueError as exc:
            logger.warning("Password hasher health check failed: %s", exc)

        # Test services initialization
        try:
            await self.get_authentication_service()
            await self.get_authorization_service()
            await self.get_user_management_service()
            health_status["services"] = True
        except (sa.exc.SQLAlchemyError, ValueError, RuntimeError) as exc:
            logger.warning("Service initialization health check failed: %s", exc)

        return health_status


# Global container instance (will be configured in main.py)
container = DependencyContainer()
