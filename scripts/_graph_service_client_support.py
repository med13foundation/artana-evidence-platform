"""Shared graph-service client helpers for operational scripts."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from uuid import UUID

from src.infrastructure.platform_graph.graph_service import (
    GraphServiceClient,
    GraphServiceClientConfig,
)
from src.infrastructure.security.jwt_provider import JWTProvider

if TYPE_CHECKING:
    import argparse

_DEFAULT_GRAPH_SERVICE_URL = "http://127.0.0.1:8090"
_LOCAL_GRAPH_ENVS = frozenset({"development", "local", "test"})
_DEFAULT_GRAPH_SERVICE_JWT_SECRET = (
    "artana-resource-library-dev-jwt-secret-for-development-2026-01"  # noqa: S105
)
_DEFAULT_SCRIPT_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


def add_graph_service_connection_args(parser: argparse.ArgumentParser) -> None:
    """Register shared graph-service connection arguments."""
    parser.add_argument(
        "--graph-service-url",
        type=str,
        default=None,
        help="Base URL for the standalone graph service API.",
    )
    parser.add_argument(
        "--graph-service-bearer-token",
        type=str,
        default=None,
        help="Optional bearer token for graph-service admin APIs.",
    )


def build_graph_service_client(args: argparse.Namespace) -> GraphServiceClient:
    """Build one typed graph-service client from CLI args and environment."""
    return GraphServiceClient(
        GraphServiceClientConfig(
            base_url=_resolve_graph_service_url(args),
            default_headers={
                "Authorization": f"Bearer {_resolve_graph_service_bearer_token(args)}",
            },
        ),
    )


def _resolve_graph_service_url(args: argparse.Namespace) -> str:
    explicit_url = getattr(args, "graph_service_url", None)
    if isinstance(explicit_url, str) and explicit_url.strip():
        return explicit_url.strip().rstrip("/")
    env_url = os.getenv("GRAPH_SERVICE_URL")
    if env_url is not None and env_url.strip():
        return env_url.strip().rstrip("/")
    if os.getenv("TESTING") == "true":
        return _DEFAULT_GRAPH_SERVICE_URL
    environment = os.getenv("ARTANA_ENV", "development").strip().lower()
    if environment in _LOCAL_GRAPH_ENVS:
        return _DEFAULT_GRAPH_SERVICE_URL
    message = (
        "GRAPH_SERVICE_URL is required outside local development for "
        "graph-service scripts"
    )
    raise RuntimeError(message)


def _resolve_graph_service_bearer_token(args: argparse.Namespace) -> str:
    explicit_token = getattr(args, "graph_service_bearer_token", None)
    if isinstance(explicit_token, str) and explicit_token.strip():
        return explicit_token.strip()
    env_token = os.getenv("GRAPH_SERVICE_BEARER_TOKEN")
    if env_token is not None and env_token.strip():
        return env_token.strip()

    secret = os.getenv("GRAPH_JWT_SECRET") or _DEFAULT_GRAPH_SERVICE_JWT_SECRET
    user_id_value = os.getenv("GRAPH_SERVICE_SCRIPT_USER_ID")
    user_id = (
        UUID(user_id_value)
        if isinstance(user_id_value, str) and user_id_value.strip()
        else _DEFAULT_SCRIPT_USER_ID
    )
    provider = JWTProvider(secret_key=secret)
    return provider.create_access_token(
        user_id=user_id,
        role="viewer",
        extra_claims={"graph_admin": True},
    )


__all__ = [
    "add_graph_service_connection_args",
    "build_graph_service_client",
]
