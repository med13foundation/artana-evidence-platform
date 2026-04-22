"""
Domain-level contracts for PubMed search orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.domain.entities.data_discovery_parameters import (
    AdvancedQueryParameters,  # noqa: TC001
)
from src.type_definitions.common import JSONObject  # noqa: TC001


@dataclass(frozen=True)
class PubMedSearchPayload:
    """Result payload returned by PubMed search gateways."""

    article_ids: list[str]
    total_count: int
    preview_records: list[JSONObject]


class PubMedSearchRateLimitError(Exception):
    """Raised when PubMed search is rate limited by the upstream provider."""

    _DEFAULT_MESSAGE = "PubMed search rate limited by NCBI after repeated attempts"

    def __init__(
        self,
        message: str | None = None,
        *,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message or self._DEFAULT_MESSAGE)
        self.retry_after_seconds = retry_after_seconds


class PubMedSearchGateway(Protocol):
    """Protocol for executing advanced PubMed searches."""

    async def run_search(
        self,
        parameters: AdvancedQueryParameters,
    ) -> PubMedSearchPayload:
        """Execute a search and return article metadata."""


class PubMedPdfGateway(Protocol):
    """Protocol for downloading PubMed article PDFs."""

    async def fetch_pdf(self, article_id: str) -> bytes:
        """Return PDF bytes for the requested article."""
