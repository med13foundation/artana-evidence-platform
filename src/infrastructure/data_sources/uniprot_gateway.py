"""UniProt data source gateway for fetching protein records."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

UNIPROT_SOURCE_TYPE = "uniprot"


@dataclass(frozen=True)
class UniProtGatewayFetchResult:
    """Result of a UniProt fetch operation."""

    records: list[dict[str, object]] = field(default_factory=list)
    fetched_records: int = 0
    checkpoint_after: dict[str, object] | None = None
    checkpoint_kind: str = "none"


class UniProtSourceGateway:
    """Gateway for fetching UniProt protein records.

    Uses the UniProtIngestor for real API calls against the
    EBI Proteins API (open access, no authentication required).
    """

    def __init__(self, *, base_url: str | None = None) -> None:
        self._base_url = base_url or "https://www.ebi.ac.uk/proteins/api"

    def fetch_records(
        self,
        *,
        query: str | None = None,
        uniprot_id: str | None = None,
        max_results: int = 100,
    ) -> UniProtGatewayFetchResult:
        """Fetch UniProt protein records for a query or accession.

        Returns raw JSON records suitable for Tier 1 grounding.
        """
        search_query = uniprot_id or query
        if not search_query or not search_query.strip():
            return UniProtGatewayFetchResult()

        from src.infrastructure.ingest.uniprot_ingestor import UniProtIngestor

        ingestor = UniProtIngestor()
        try:
            return asyncio.get_event_loop().run_until_complete(
                self._fetch_async(ingestor, search_query, max_results),
            )
        except RuntimeError:
            return asyncio.run(
                self._fetch_async(ingestor, search_query, max_results),
            )

    @staticmethod
    async def _fetch_async(
        ingestor: object,
        query: str,
        max_results: int,
    ) -> UniProtGatewayFetchResult:
        from src.infrastructure.ingest.uniprot_ingestor import UniProtIngestor

        assert isinstance(ingestor, UniProtIngestor)  # noqa: S101
        async with ingestor:
            raw_records = await ingestor.fetch_data(
                query=query,
                max_results=max_results,
            )
            records: list[dict[str, object]] = [
                {str(k): v for k, v in r.items()} for r in raw_records
            ]
            return UniProtGatewayFetchResult(
                records=records,
                fetched_records=len(records),
            )

    def fetch_records_incremental(
        self,
        *,
        query: str | None = None,
        checkpoint: dict[str, object] | None = None,  # noqa: ARG002
        max_results: int = 100,
    ) -> UniProtGatewayFetchResult:
        """Fetch UniProt records with checkpoint support for incremental ingestion."""
        return self.fetch_records(
            query=query,
            max_results=max_results,
        )


__all__ = ["UniProtGatewayFetchResult", "UniProtSourceGateway"]
