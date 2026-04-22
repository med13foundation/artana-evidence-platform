"""Lazy exports for Artana Evidence API platform clients."""

from __future__ import annotations

__all__ = [
    "ArtanaEvidenceApiClient",
    "ArtanaEvidenceApiClientConfig",
    "ArtanaEvidenceApiClientError",
    "ArtanaEvidenceApiGraphSearchAdapter",
    "build_graph_connection_seed_runner_for_service",
    "build_graph_connection_seed_runner_for_user",
    "build_artana_evidence_api_client_for_service",
    "build_artana_evidence_api_client_for_user",
    "build_graph_search_service_for_service",
    "build_graph_search_service_for_user",
    "resolve_artana_evidence_api_service_url",
]


def __getattr__(name: str) -> object:
    if name in {
        "ArtanaEvidenceApiClient",
        "ArtanaEvidenceApiClientConfig",
        "ArtanaEvidenceApiClientError",
    }:
        from .client import (
            ArtanaEvidenceApiClient,
            ArtanaEvidenceApiClientConfig,
            ArtanaEvidenceApiClientError,
        )

        return {
            "ArtanaEvidenceApiClient": ArtanaEvidenceApiClient,
            "ArtanaEvidenceApiClientConfig": ArtanaEvidenceApiClientConfig,
            "ArtanaEvidenceApiClientError": ArtanaEvidenceApiClientError,
        }[name]

    if name in {
        "ArtanaEvidenceApiGraphSearchAdapter",
        "build_graph_connection_seed_runner_for_service",
        "build_graph_connection_seed_runner_for_user",
        "build_graph_search_service_for_service",
        "build_graph_search_service_for_user",
    }:
        from .pipeline import (
            ArtanaEvidenceApiGraphSearchAdapter,
            build_graph_connection_seed_runner_for_service,
            build_graph_connection_seed_runner_for_user,
            build_graph_search_service_for_service,
            build_graph_search_service_for_user,
        )

        return {
            "ArtanaEvidenceApiGraphSearchAdapter": ArtanaEvidenceApiGraphSearchAdapter,
            "build_graph_connection_seed_runner_for_service": (
                build_graph_connection_seed_runner_for_service
            ),
            "build_graph_connection_seed_runner_for_user": (
                build_graph_connection_seed_runner_for_user
            ),
            "build_graph_search_service_for_service": (
                build_graph_search_service_for_service
            ),
            "build_graph_search_service_for_user": build_graph_search_service_for_user,
        }[name]

    if name in {
        "build_artana_evidence_api_client_for_service",
        "build_artana_evidence_api_client_for_user",
        "resolve_artana_evidence_api_service_url",
    }:
        from .runtime import (
            build_artana_evidence_api_client_for_service,
            build_artana_evidence_api_client_for_user,
            resolve_artana_evidence_api_service_url,
        )

        return {
            "build_artana_evidence_api_client_for_service": (
                build_artana_evidence_api_client_for_service
            ),
            "build_artana_evidence_api_client_for_user": build_artana_evidence_api_client_for_user,
            "resolve_artana_evidence_api_service_url": resolve_artana_evidence_api_service_url,
        }[name]

    raise AttributeError(name)
