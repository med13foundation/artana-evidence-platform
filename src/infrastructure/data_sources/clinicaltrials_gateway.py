"""ClinicalTrials.gov source gateway for fetching registered clinical trials.

Adapter on top of :class:`ClinicalTrialsIngestor` that exposes a sync
``fetch_records()`` API consistent with the other structured database
connectors (ClinVar, AlphaFold, DrugBank, MARRVEL).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

CLINICAL_TRIALS_SOURCE_TYPE = "clinical_trials"


@dataclass(frozen=True)
class ClinicalTrialsGatewayFetchResult:
    """Result of a ClinicalTrials.gov fetch operation."""

    records: list[dict[str, object]] = field(default_factory=list)
    fetched_records: int = 0
    next_page_token: str | None = None
    checkpoint_after: dict[str, object] | None = None
    checkpoint_kind: str = "none"


class ClinicalTrialsSourceGateway:
    """Gateway for fetching ClinicalTrials.gov registered trials.

    Wraps the async :class:`ClinicalTrialsIngestor` so callers in the
    research-init enrichment helpers and the scheduler can fetch trials
    via a uniform sync interface.  No authentication is required —
    the v2 REST API is open access.
    """

    def __init__(self, *, base_url: str | None = None) -> None:
        self._base_url = base_url or "https://clinicaltrials.gov/api/v2"

    def fetch_records(
        self,
        *,
        query: str,
        max_results: int = 20,
    ) -> ClinicalTrialsGatewayFetchResult:
        """Fetch clinical trial records matching ``query``.

        Returns raw flattened records suitable for Tier 1 grounding.  An
        empty query yields an empty result without hitting the network.
        """
        if not query or not query.strip():
            return ClinicalTrialsGatewayFetchResult()

        from src.infrastructure.ingest.clinicaltrials_ingestor import (
            ClinicalTrialsIngestor,
        )

        ingestor = ClinicalTrialsIngestor()
        return asyncio.run(self._fetch_async(ingestor, query, max_results))

    async def fetch_records_async(
        self,
        *,
        query: str,
        max_results: int = 20,
    ) -> ClinicalTrialsGatewayFetchResult:
        """Fetch clinical trial records from async callers without nesting loops."""
        if not query or not query.strip():
            return ClinicalTrialsGatewayFetchResult()

        from src.infrastructure.ingest.clinicaltrials_ingestor import (
            ClinicalTrialsIngestor,
        )

        ingestor = ClinicalTrialsIngestor()
        return await self._fetch_async(ingestor, query, max_results)

    @staticmethod
    async def _fetch_async(
        ingestor: object,
        query: str,
        max_results: int,
    ) -> ClinicalTrialsGatewayFetchResult:
        from src.infrastructure.ingest.clinicaltrials_ingestor import (
            ClinicalTrialsIngestor,
        )

        assert isinstance(ingestor, ClinicalTrialsIngestor)  # noqa: S101
        async with ingestor:
            page = await ingestor.fetch_studies(
                query=query,
                max_results=max_results,
            )
            records: list[dict[str, object]] = [dict(r) for r in page.records]
            return ClinicalTrialsGatewayFetchResult(
                records=records,
                fetched_records=len(records),
                next_page_token=page.next_page_token,
            )

    def fetch_records_incremental(
        self,
        *,
        query: str,
        checkpoint: dict[str, object] | None = None,  # noqa: ARG002
        max_results: int = 20,
    ) -> ClinicalTrialsGatewayFetchResult:
        """Fetch ClinicalTrials.gov records with checkpoint support.

        ClinicalTrials.gov v2 uses page tokens for pagination; for the
        first cut we don't honor incremental checkpoints and simply
        delegate to the non-incremental path.
        """
        return self.fetch_records(query=query, max_results=max_results)


__all__ = [
    "CLINICAL_TRIALS_SOURCE_TYPE",
    "ClinicalTrialsGatewayFetchResult",
    "ClinicalTrialsSourceGateway",
]
