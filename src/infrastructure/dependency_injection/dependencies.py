"""
FastAPI-facing dependency helpers that wrap the global dependency container.

Keeping these functions in a dedicated module keeps `container.py` focused on
the wiring logic while exposing a clean import surface for routes.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from src.application.services.authentication_service import AuthenticationService
from src.application.services.user_management_service import UserManagementService
from src.database.session import SessionLocal, set_session_rls_context
from src.infrastructure.dependency_injection.container import (
    DependencyContainer,
    container,
)
from src.infrastructure.repositories.sqlalchemy_session_repository import (
    SqlAlchemySessionRepository,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Generator

    from sqlalchemy.orm import Session

    from src.application.services.data_discovery_service import DataDiscoveryService
    from src.application.services.discovery_configuration_service import (
        DiscoveryConfigurationService,
    )
    from src.application.services.pubmed_discovery_service import PubMedDiscoveryService
    from src.infrastructure.repositories.sqlalchemy_user_repository import (
        SqlAlchemyUserRepository,
    )


def initialize_legacy_session(session: Session) -> None:
    """
    Maintain backward-compatible legacy session initialization hook.

    Legacy routes call this to initialize state, but the modern architecture
    does not require any action. Keeping the function avoids import churn.
    """


def get_user_repository_dependency() -> SqlAlchemyUserRepository:
    """Return the active user repository from the global container."""
    return container.get_user_repository()


def _build_authentication_service() -> AuthenticationService:
    """Create an authentication service using the global container wiring."""
    return AuthenticationService(
        user_repository=get_user_repository_dependency(),
        session_repository=SqlAlchemySessionRepository(container.async_session_factory),
        jwt_provider=container.jwt_provider,
        password_hasher=container.password_hasher,
    )


def get_authentication_service_dependency() -> AuthenticationService:
    """
    Resolve AuthenticationService for FastAPI dependencies.

    Attempts to reuse the running event loop when available, falling back to
    synchronous construction when invoked outside of ASGI contexts.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return _build_authentication_service()
        return loop.run_until_complete(container.get_authentication_service())
    except RuntimeError:
        return _build_authentication_service()


def get_user_management_service_dependency() -> UserManagementService:
    """
    Resolve UserManagementService for FastAPI dependencies.

    Mirrors the authentication dependency logic so CLI tooling can reuse the
    synchronous code path.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return UserManagementService(
                user_repository=get_user_repository_dependency(),
                password_hasher=container.password_hasher,
            )
        return loop.run_until_complete(container.get_user_management_service())
    except RuntimeError:
        return UserManagementService(
            user_repository=get_user_repository_dependency(),
            password_hasher=container.password_hasher,
        )


def get_legacy_dependency_container() -> DependencyContainer:
    """Expose the global container for legacy synchronous routes."""
    return container


def get_data_discovery_service_dependency() -> Generator[DataDiscoveryService]:
    """
    Provide a per-request DataDiscoveryService with isolated SQLAlchemy session.

    The generator mirrors FastAPI's dependency pattern to ensure sessions close
    even when downstream code raises.
    """
    session = SessionLocal()
    set_session_rls_context(session, bypass_rls=True)
    try:
        service = container.create_data_discovery_service(session)
        yield service
    finally:
        session.close()


def get_discovery_configuration_service_dependency() -> (
    Generator[DiscoveryConfigurationService]
):
    """Provide a scoped DiscoveryConfigurationService for FastAPI routes."""
    session = SessionLocal()
    set_session_rls_context(session, bypass_rls=True)
    try:
        service = container.create_discovery_configuration_service(session)
        yield service
    finally:
        session.close()


def get_pubmed_discovery_service_dependency() -> Generator[PubMedDiscoveryService]:
    """Provide a scoped PubMedDiscoveryService for FastAPI routes."""
    session = SessionLocal()
    set_session_rls_context(session, bypass_rls=True)
    try:
        service = container.create_pubmed_discovery_service(session)
        yield service
    finally:
        session.close()
