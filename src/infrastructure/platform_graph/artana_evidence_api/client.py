"""Typed HTTP client for the standalone Artana Evidence API service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar
from uuid import UUID  # noqa: TC003

import httpx
from pydantic import BaseModel, ConfigDict, Field

from src.domain.agents.contracts.graph_connection import (  # noqa: TC001
    GraphConnectionContract,
)
from src.domain.agents.contracts.graph_search import GraphSearchContract  # noqa: TC001

if TYPE_CHECKING:
    from collections.abc import Mapping

ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)


class ArtanaEvidenceApiClientError(RuntimeError):
    """Raised when the Artana Evidence API returns an invalid or failed response."""


@dataclass(frozen=True, slots=True)
class ArtanaEvidenceApiClientConfig:
    """Static configuration for Artana Evidence API HTTP calls."""

    base_url: str
    timeout_seconds: float = 30.0
    default_headers: Mapping[str, str] | None = None


class _GraphSearchRunRequestPayload(BaseModel):
    model_config = ConfigDict(strict=True)

    question: str
    model_id: str | None = None
    max_depth: int = 2
    top_k: int = 25
    curation_statuses: list[str] | None = None
    include_evidence_chains: bool = True


class _GraphConnectionRunRequestPayload(BaseModel):
    model_config = ConfigDict(strict=True)

    seed_entity_ids: list[str] = Field(..., min_length=1, max_length=200)
    source_type: str | None = None
    source_id: str | None = None
    model_id: str | None = None
    relation_types: list[str] | None = None
    max_depth: int = 2
    shadow_mode: bool = True
    pipeline_run_id: str | None = None


class _HarnessRunResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    id: str
    harness_id: str
    status: str


class _GraphSearchRunResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    run: _HarnessRunResponse
    result: GraphSearchContract


class _GraphConnectionRunResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    run: _HarnessRunResponse
    outcomes: list[GraphConnectionContract]


class ArtanaEvidenceApiClient:
    """Typed client for Artana Evidence API search and connection runs."""

    def __init__(
        self,
        config: ArtanaEvidenceApiClientConfig,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self._config = config
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=config.base_url.rstrip("/"),
            timeout=config.timeout_seconds,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def search_graph(  # noqa: PLR0913
        self,
        *,
        space_id: UUID,
        question: str,
        model_id: str | None = None,
        max_depth: int = 2,
        top_k: int = 25,
        curation_statuses: list[str] | None = None,
        include_evidence_chains: bool = True,
        headers: Mapping[str, str] | None = None,
    ) -> GraphSearchContract:
        """Execute one harness-owned graph-search run and return its result."""
        response = self._request_model(
            "POST",
            f"/v1/spaces/{space_id}/agents/graph-search/runs",
            response_model=_GraphSearchRunResponse,
            content=_GraphSearchRunRequestPayload(
                question=question,
                model_id=model_id,
                max_depth=max_depth,
                top_k=top_k,
                curation_statuses=curation_statuses,
                include_evidence_chains=include_evidence_chains,
            ).model_dump_json(),
            headers=headers,
        )
        return response.result

    def discover_entity_connections(  # noqa: PLR0913
        self,
        *,
        space_id: UUID,
        entity_id: UUID,
        source_type: str,
        source_id: str | None = None,
        model_id: str | None = None,
        relation_types: list[str] | None = None,
        max_depth: int = 2,
        shadow_mode: bool | None = None,
        pipeline_run_id: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> GraphConnectionContract:
        """Execute one harness-owned graph-connection run for a single seed."""
        response = self._request_model(
            "POST",
            f"/v1/spaces/{space_id}/agents/graph-connections/runs",
            response_model=_GraphConnectionRunResponse,
            content=_GraphConnectionRunRequestPayload(
                seed_entity_ids=[str(entity_id)],
                source_type=source_type,
                source_id=source_id,
                model_id=model_id,
                relation_types=relation_types,
                max_depth=max_depth,
                shadow_mode=True if shadow_mode is None else shadow_mode,
                pipeline_run_id=pipeline_run_id,
            ).model_dump_json(),
            headers=headers,
        )
        if not response.outcomes:
            error_message = "Artana Evidence API returned no graph-connection outcomes"
            raise ArtanaEvidenceApiClientError(error_message)
        return response.outcomes[0]

    def _request_model(  # noqa: PLR0913
        self,
        method: str,
        path: str,
        *,
        response_model: type[ResponseModelT],
        params: Mapping[str, str] | None = None,
        content: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> ResponseModelT:
        merged_headers = self._merge_headers(headers)
        try:
            response = self._client.request(
                method,
                path,
                params=params,
                content=content,
                headers=merged_headers,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            error_message = (
                "Harness request failed with status "
                f"{exc.response.status_code}: {exc.response.text}"
            )
            raise ArtanaEvidenceApiClientError(error_message) from exc
        except httpx.HTTPError as exc:
            raise ArtanaEvidenceApiClientError(str(exc)) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            error_message = "Harness response was not valid JSON"
            raise ArtanaEvidenceApiClientError(error_message) from exc

        try:
            return response_model.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            error_message = f"Harness response validation failed: {exc}"
            raise ArtanaEvidenceApiClientError(error_message) from exc

    def _merge_headers(
        self,
        headers: Mapping[str, str] | None,
    ) -> dict[str, str]:
        merged_headers: dict[str, str] = {}
        if self._config.default_headers is not None:
            merged_headers.update(self._config.default_headers)
        if headers is not None:
            merged_headers.update(headers)
        if "Content-Type" not in merged_headers:
            merged_headers["Content-Type"] = "application/json"
        return merged_headers


__all__ = [
    "ArtanaEvidenceApiClient",
    "ArtanaEvidenceApiClientConfig",
    "ArtanaEvidenceApiClientError",
]
