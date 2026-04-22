"""Lazy exports for the standalone graph-service client package."""

from __future__ import annotations

__all__ = [
    "GraphServiceClient",
    "GraphServiceClientConfig",
    "GraphServiceClientError",
    "GraphServiceHealthResponse",
    "GraphServiceSpaceLifecycleSync",
    "build_graph_service_bearer_token_for_service",
    "build_graph_service_bearer_token_for_user",
    "build_graph_service_client_for_service",
    "build_graph_service_client_for_user",
    "resolve_graph_service_url",
]


def __getattr__(name: str) -> object:
    if name in {
        "GraphServiceClient",
        "GraphServiceClientConfig",
        "GraphServiceClientError",
        "GraphServiceHealthResponse",
    }:
        from .client import (
            GraphServiceClient,
            GraphServiceClientConfig,
            GraphServiceClientError,
            GraphServiceHealthResponse,
        )

        return {
            "GraphServiceClient": GraphServiceClient,
            "GraphServiceClientConfig": GraphServiceClientConfig,
            "GraphServiceClientError": GraphServiceClientError,
            "GraphServiceHealthResponse": GraphServiceHealthResponse,
        }[name]

    if name == "GraphServiceSpaceLifecycleSync":
        from .space_lifecycle_sync import GraphServiceSpaceLifecycleSync

        return GraphServiceSpaceLifecycleSync

    if name in {
        "build_graph_service_bearer_token_for_service",
        "build_graph_service_bearer_token_for_user",
        "build_graph_service_client_for_service",
        "build_graph_service_client_for_user",
        "resolve_graph_service_url",
    }:
        from .runtime import (
            build_graph_service_bearer_token_for_service,
            build_graph_service_bearer_token_for_user,
            build_graph_service_client_for_service,
            build_graph_service_client_for_user,
            resolve_graph_service_url,
        )

        return {
            "build_graph_service_bearer_token_for_service": (
                build_graph_service_bearer_token_for_service
            ),
            "build_graph_service_bearer_token_for_user": (
                build_graph_service_bearer_token_for_user
            ),
            "build_graph_service_client_for_service": (
                build_graph_service_client_for_service
            ),
            "build_graph_service_client_for_user": (
                build_graph_service_client_for_user
            ),
            "resolve_graph_service_url": resolve_graph_service_url,
        }[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
