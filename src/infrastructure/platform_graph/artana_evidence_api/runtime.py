"""Runtime helpers for authenticated Artana Evidence API calls from the platform app."""

from __future__ import annotations

import os

from src.domain.entities.user import User, UserRole
from src.infrastructure.platform_graph.graph_service.runtime import (
    build_graph_service_bearer_token_for_service,
    build_graph_service_bearer_token_for_user,
)

from .client import ArtanaEvidenceApiClient, ArtanaEvidenceApiClientConfig

_DEFAULT_ARTANA_EVIDENCE_API_SERVICE_URL = "http://127.0.0.1:8091"
_LOCAL_ARTANA_EVIDENCE_API_ENVS = frozenset({"development", "local", "test"})


class MissingArtanaEvidenceApiServiceUrlError(RuntimeError):
    """Raised when the standalone Artana Evidence API URL is required but unset."""

    def __init__(self) -> None:
        super().__init__(
            "ARTANA_EVIDENCE_API_SERVICE_URL is required outside local development "
            "for platform-to-harness calls",
        )


def _allow_local_artana_evidence_api_fallback() -> bool:
    if os.getenv("TESTING") == "true":
        return True
    environment = os.getenv("ARTANA_ENV", "development").strip().lower()
    return environment in _LOCAL_ARTANA_EVIDENCE_API_ENVS


def resolve_artana_evidence_api_service_url() -> str:
    """Resolve the standalone Artana Evidence API base URL."""
    explicit_url = os.getenv("ARTANA_EVIDENCE_API_SERVICE_URL")
    if explicit_url is not None and explicit_url.strip():
        return explicit_url.strip().rstrip("/")
    if _allow_local_artana_evidence_api_fallback():
        return _DEFAULT_ARTANA_EVIDENCE_API_SERVICE_URL
    raise MissingArtanaEvidenceApiServiceUrlError


def build_artana_evidence_api_client_for_user(
    user: User,
) -> ArtanaEvidenceApiClient:
    """Build one typed Artana Evidence API client authenticated as the user."""
    return ArtanaEvidenceApiClient(
        ArtanaEvidenceApiClientConfig(
            base_url=resolve_artana_evidence_api_service_url(),
            default_headers={
                "Authorization": (
                    "Bearer " + build_graph_service_bearer_token_for_user(user)
                ),
            },
        ),
    )


def build_artana_evidence_api_client_for_service(
    *,
    role: UserRole = UserRole.VIEWER,
    graph_admin: bool = True,
) -> ArtanaEvidenceApiClient:
    """Build one typed Artana Evidence API client for service-to-service calls."""
    return ArtanaEvidenceApiClient(
        ArtanaEvidenceApiClientConfig(
            base_url=resolve_artana_evidence_api_service_url(),
            default_headers={
                "Authorization": (
                    "Bearer "
                    + build_graph_service_bearer_token_for_service(
                        role=role,
                        graph_admin=graph_admin,
                    )
                ),
            },
        ),
    )


__all__ = [
    "build_artana_evidence_api_client_for_service",
    "build_artana_evidence_api_client_for_user",
    "resolve_artana_evidence_api_service_url",
]
