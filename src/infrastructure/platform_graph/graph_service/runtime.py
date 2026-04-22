"""Runtime helpers for authenticated graph-service calls from the platform app."""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from artana_evidence_db.runtime import resolve_graph_jwt_secret

from src.domain.entities.user import User, UserRole
from src.infrastructure.security.jwt_provider import JWTProvider

if TYPE_CHECKING:
    from .client import GraphServiceClient

_DEFAULT_GRAPH_SERVICE_URL = "http://127.0.0.1:8090"
_DEFAULT_GRAPH_SERVICE_JWT_ISSUER = "graph-biomedical"
_LOCAL_GRAPH_ENVS = frozenset({"development", "local", "test"})
_DEFAULT_GRAPH_SERVICE_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
GraphServiceCapability = Literal["space_sync"]


def _allow_local_graph_service_fallback() -> bool:
    if os.getenv("TESTING") == "true":
        return True
    environment = os.getenv("ARTANA_ENV", "development").strip().lower()
    return environment in _LOCAL_GRAPH_ENVS


def resolve_graph_service_url() -> str:
    """Resolve the standalone graph-service base URL."""
    explicit_url = os.getenv("GRAPH_SERVICE_URL")
    if explicit_url is not None and explicit_url.strip():
        return explicit_url.strip().rstrip("/")
    if _allow_local_graph_service_fallback():
        return _DEFAULT_GRAPH_SERVICE_URL
    raise RuntimeError(
        "GRAPH_SERVICE_URL is required outside local development for platform-to-graph calls",
    )


def resolve_graph_service_jwt_issuer() -> str:
    """Resolve the graph-service JWT issuer expected by the standalone graph API."""
    configured_issuer = os.getenv("GRAPH_JWT_ISSUER")
    if configured_issuer is not None and configured_issuer.strip():
        return configured_issuer.strip()
    return _DEFAULT_GRAPH_SERVICE_JWT_ISSUER


def build_graph_service_bearer_token_for_user(
    user: User,
    *,
    graph_admin: bool = False,
) -> str:
    """Mint one graph-service bearer token for the supplied user."""
    provider = JWTProvider(secret_key=resolve_graph_jwt_secret())
    return provider.create_access_token(
        user.id,
        user.role.value,
        extra_claims={"graph_admin": graph_admin},
        issuer=resolve_graph_service_jwt_issuer(),
    )


def build_graph_service_bearer_token_for_service(
    *,
    role: UserRole = UserRole.VIEWER,
    graph_admin: bool = True,
    graph_service_capabilities: Sequence[GraphServiceCapability] = (),
) -> str:
    """Mint one graph-service bearer token for backend service-to-service calls."""
    user_id_value = os.getenv("GRAPH_SERVICE_SERVICE_USER_ID")
    service_user_id = (
        UUID(user_id_value)
        if isinstance(user_id_value, str) and user_id_value.strip()
        else _DEFAULT_GRAPH_SERVICE_USER_ID
    )
    provider = JWTProvider(secret_key=resolve_graph_jwt_secret())
    extra_claims: dict[str, object] = {"graph_admin": graph_admin}
    normalized_capabilities = [
        capability.strip()
        for capability in graph_service_capabilities
        if capability.strip()
    ]
    if normalized_capabilities:
        extra_claims["graph_service_capabilities"] = normalized_capabilities
    return provider.create_access_token(
        service_user_id,
        role.value,
        extra_claims=extra_claims,
        issuer=resolve_graph_service_jwt_issuer(),
    )


def build_graph_service_client_for_user(
    user: User,
    *,
    graph_admin: bool = False,
) -> GraphServiceClient:
    """Build one typed graph-service client authenticated as the supplied user."""
    from .client import GraphServiceClient, GraphServiceClientConfig

    return GraphServiceClient(
        GraphServiceClientConfig(
            base_url=resolve_graph_service_url(),
            default_headers={
                "Authorization": (
                    "Bearer "
                    + build_graph_service_bearer_token_for_user(
                        user,
                        graph_admin=graph_admin,
                    )
                ),
            },
        ),
    )


def build_graph_service_client_for_service(
    *,
    role: UserRole = UserRole.VIEWER,
    graph_admin: bool = True,
    graph_service_capabilities: Sequence[GraphServiceCapability] = (),
) -> GraphServiceClient:
    """Build one typed graph-service client for backend service-to-service calls."""
    from .client import GraphServiceClient, GraphServiceClientConfig

    return GraphServiceClient(
        GraphServiceClientConfig(
            base_url=resolve_graph_service_url(),
            default_headers={
                "Authorization": (
                    "Bearer "
                    + build_graph_service_bearer_token_for_service(
                        role=role,
                        graph_admin=graph_admin,
                        graph_service_capabilities=graph_service_capabilities,
                    )
                ),
            },
        ),
    )


__all__ = [
    "build_graph_service_bearer_token_for_service",
    "build_graph_service_bearer_token_for_user",
    "build_graph_service_client_for_service",
    "build_graph_service_client_for_user",
    "resolve_graph_service_jwt_issuer",
    "resolve_graph_service_url",
]
