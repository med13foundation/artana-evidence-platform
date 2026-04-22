"""MGI source gateway for fetching mouse gene records.

Adapter on top of :class:`MGIIngestor` that exposes a sync ``fetch_records()``
API consistent with the other structured database connectors.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

MGI_SOURCE_TYPE = "mgi"


@dataclass(frozen=True)
class MGIGatewayFetchResult:
    """Result of an MGI fetch operation."""

    records: list[dict[str, object]] = field(default_factory=list)
    fetched_records: int = 0
    checkpoint_after: dict[str, object] | None = None
    checkpoint_kind: str = "none"


class MGISourceGateway:
    """Gateway for fetching MGI mouse gene records.

    Wraps the async :class:`MGIIngestor` so callers in the research-init
    enrichment helpers and the scheduler can fetch records via a uniform
    sync interface.  No authentication is required — the Alliance of
    Genome Resources REST API is open access.
    """

    def __init__(self, *, base_url: str | None = None) -> None:
        self._base_url = base_url or "https://www.alliancegenome.org/api"

    def fetch_records(
        self,
        *,
        query: str,
        max_results: int = 10,
    ) -> MGIGatewayFetchResult:
        """Fetch MGI gene records matching ``query``.

        Returns flattened records suitable for Tier 1 grounding.  An empty
        query yields an empty result without hitting the network.
        """
        if not query or not query.strip():
            return MGIGatewayFetchResult()

        from src.infrastructure.ingest.mgi_ingestor import MGIIngestor

        ingestor = MGIIngestor()
        return asyncio.run(self._fetch_async(ingestor, query, max_results))

    async def fetch_records_async(
        self,
        *,
        query: str,
        max_results: int = 10,
    ) -> MGIGatewayFetchResult:
        """Fetch MGI records from async callers without nesting loops."""
        if not query or not query.strip():
            return MGIGatewayFetchResult()

        from src.infrastructure.ingest.mgi_ingestor import MGIIngestor

        ingestor = MGIIngestor()
        return await self._fetch_async(ingestor, query, max_results)

    @staticmethod
    async def _fetch_async(
        ingestor: object,
        query: str,
        max_results: int,
    ) -> MGIGatewayFetchResult:
        from src.infrastructure.ingest.mgi_ingestor import MGIIngestor

        assert isinstance(ingestor, MGIIngestor)  # noqa: S101
        async with ingestor:
            page = await ingestor.fetch_gene_records(
                query=query,
                max_results=max_results,
            )
            records: list[dict[str, object]] = [dict(r) for r in page.records]
            return MGIGatewayFetchResult(
                records=records,
                fetched_records=len(records),
            )

    def fetch_records_incremental(
        self,
        *,
        query: str,
        checkpoint: dict[str, object] | None = None,  # noqa: ARG002
        max_results: int = 10,
    ) -> MGIGatewayFetchResult:
        """Fetch MGI records with checkpoint support.

        The Alliance search endpoint is not paginated for our use case;
        we delegate to the non-incremental path for now.
        """
        return self.fetch_records(query=query, max_results=max_results)


__all__ = [
    "MGI_SOURCE_TYPE",
    "MGIGatewayFetchResult",
    "MGISourceGateway",
]
